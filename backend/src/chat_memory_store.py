"""Owner-scoped personal memory. No startup DDL, provider calls or shared caches.

Transactions lock the owning session before touching requests/messages. Deleted
session tombstones are retained; personal text and request payloads are erased.
"""
import hashlib
import json
import re
import uuid
from contextlib import contextmanager


class MemoryError(Exception):
    def __init__(self, code, status=409):
        self.code, self.status = code, status


def decode(value):
    return json.loads(value) if isinstance(value, (str, bytes)) else (value or {})


def terms(text):
    stop = set('what did i ask about last time previous chat conversation the a an is it its that this and of for to me my you saya apa yang itu dia tadi lepas lalu sebelum tentang pernah'.split())
    text = re.sub(r'上次|之前|以前|问过|问了|什么|聊天|记得|記得|之前|甚麼|問過|問了', ' ', text)
    words = set(re.findall(r'[a-z0-9]+', text.lower())) - stop - {'remember','when','earlier'}
    # CJK bigrams permit deterministic Chinese topic matching without embeddings.
    for run in re.findall(r'[\u3400-\u9fff]+', text):
        words.update(run[i:i+2] for i in range(len(run)-1))
    return words


def is_recall(text):
    return bool(re.search(r'last time|previous chat|earlier chat|what did i ask|remember when|上次|之前.*聊|以前.*问|sembang sebelum|chat lepas|kali lepas|pernah.*tanya', text, re.I))


# Small multilingual lexical aliases, not company facts or object identities.
# Compound equipment names remain atomic: an ice machine is not an ice bin.
_TOPIC_ALIASES = {
    'ice_bin': ('ice bins', 'ice bin', '冰桶', 'tong ais'),
    'ice_machine': ('ice machine', 'ice maker', '制冰机', '製冰機', 'mesin ais'),
    'printer': ('printers', 'printer', '打印机', '打印機', 'pencetak'),
    'membership': ('membership', 'member', 'members', '会员', '會員', 'keahlian', 'ahli'),
    'honey': ('honey', '蜂蜜', 'madu'),
    'stocktake': ('stocktake', 'stocktaking', '盘点', '盤點', 'kiraan stok'),
    'orange': ('orange', '橙色', 'oren'),
    'blue': ('blue', '蓝色', '藍色', 'biru'),
    'red': ('red', '红色', '紅色', 'merah'),
    'green': ('green', '绿色', '綠色', 'hijau'),
}
_TOPIC_STOP = set(('what did i ask about last time previous previously chat conversation the a an is it its that this '
    'and of for to me my you your our we should would could can do does how where when why which on in at '
    'was were am are have has had been with from before after earlier remember please tell show explain '
    'clean cleaning cleaned wash washing store stored storage keep put register registration procedure '
    'process steps step use using daily open close opened closed opening closing need want way question questions properly safely '
    'proper method sanitize sanitise sanitizing sanitising disinfect washing maintain maintenance '
    'price prices pricing benefits benefit cost costs information info help more equipment device object '
    'thing things item items policy guidance topic work product products saya apa yang '
    'itu dia tadi lepas lalu sebelum tentang pernah kali tanya bagaimana cara membersihkan bersihkan '
    'cuci mencuci simpan menyimpan di mana patut perlu nak macam buka tutup untuk dan dengan pendaftaran daftar mendaftar').split())
_TOPIC_CJK_STOP = re.compile('上次|之前|以前|问过|問過|问了|問了|问题|問題|什么|甚麼|聊天|记得|記得|'
    '应该|應該|如何|怎么|怎麼|怎样|怎樣|哪里|哪裡|清洗|清洁|清潔|清理|消毒|存放|储存|儲存|放在|放哪|注册|註冊|'
    '这个|這個|那个|那個|它|是否|需要|请问|請問|的|我|要|在|吗|嗎')
_COLORS = {'orange', 'blue', 'red', 'green'}


def topic_terms(text):
    """Subject signals only; shared question verbs must not retrieve equipment."""
    text = re.sub(r'<[^>]*>|(?:https?://|data:|blob:)\S+', ' ', str(text)[:1000].casefold())
    for canonical, aliases in _TOPIC_ALIASES.items():
        pattern = '|'.join(re.escape(alias) for alias in sorted(aliases, key=len, reverse=True))
        text = re.sub(r'(?<![a-z0-9_])(?:'+pattern+r')(?![a-z0-9_])', ' '+canonical+' ', text)
    text = _TOPIC_CJK_STOP.sub(' ', text)
    result = set(re.findall(r'[a-z][a-z0-9_]*', text)) - _TOPIC_STOP
    for run in re.findall(r'[\u3400-\u9fff]+', text):
        result.update(run[i:i+2] for i in range(len(run)-1))
    return result


def has_topic(tokens):
    subjects = tokens - _COLORS
    return (len(subjects) >= 2 or any(t in _TOPIC_ALIASES or len(t) >= 4
            or re.fullmatch(r'[\u3400-\u9fff]{2}', t) for t in subjects))


def select_cross_history(candidates, question):
    """Only one unambiguous subject group; never merge it into active SOP state."""
    if any(r.get('ambiguous_topic') for r in candidates):
        return []
    query = topic_terms(question)
    eligible = [r for r in candidates if query <= topic_terms(r['content'])]
    groups = {tuple(sorted(topic_terms(r['content']) - query)) for r in eligible}
    if len(groups) != 1:
        return []
    return eligible[:3]  # each original message is already limited to 1000 chars


def select_history(rows, question, budget=10000):
    """Recent continuity plus older relevant evidence, in original sequence order."""
    rows = [r for r in rows if decode(r.get('metadata_json')).get('source') != 'personal_chat_recall'
            and not decode(r.get('metadata_json')).get('memory_context_used')]
    q = terms(question)
    recent = rows[-8:]
    older = sorted(rows[:-8], key=lambda r: (-len(q & terms(r['content'])), -r['sequence_no']))
    chosen = {r['sequence_no']: r for r in recent}
    for row in older:
        if len(chosen) >= 16:
            break
        if q & terms(row['content']):
            chosen[row['sequence_no']] = row
    result = []
    for row in sorted(chosen.values(), key=lambda r: r['sequence_no']):
        content = row['content'][:1000]
        if len(content) > budget:
            break
        result.append({'role': row['role'], 'content': content})
        budget -= len(content)
    while result and result[0]['role'] != 'user':
        result.pop(0)
    return result


class ChatMemoryStore:
    def __init__(self, connect):
        self.connect = connect

    @contextmanager
    def transaction(self):
        conn = self.connect()
        cur = None
        try:
            cur = conn.cursor(dictionary=True)
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            if cur:
                cur.close()
            conn.close()

    def owned(self, cur, owner, cid, lock=False):
        cur.execute('SELECT * FROM staff_chat_session WHERE conversation_id=%s AND owner_id=%s AND deleted_at IS NULL' + (' FOR UPDATE' if lock else ''), (cid, owner))
        row = cur.fetchone()
        if not row:
            raise MemoryError('CHAT_NOT_FOUND', 404)
        return row

    def create(self, owner, title='New Chat'):
        cid = str(uuid.uuid4())
        with self.transaction() as cur:
            cur.execute('INSERT INTO staff_chat_session (conversation_id,owner_id,title) VALUES (%s,%s,%s)', (cid, owner, title[:160]))
        return {'id': cid, 'title': title[:160], 'messages': []}

    def list(self, owner, offset=0):
        with self.transaction() as cur:
            cur.execute('SELECT conversation_id AS id,title,updated_at FROM staff_chat_session WHERE owner_id=%s AND deleted_at IS NULL ORDER BY updated_at DESC,conversation_id DESC LIMIT 51 OFFSET %s', (owner, offset))
            rows = cur.fetchall()
        return {'sessions': rows[:50], 'next_offset': offset+50 if len(rows)>50 else None}

    def messages(self, owner, cid, before=None, limit=200):
        with self.transaction() as cur:
            self.owned(cur, owner, cid)
            cur.execute('SELECT * FROM staff_chat_message WHERE conversation_id=%s AND sequence_no < %s ORDER BY sequence_no DESC LIMIT %s', (cid, before or 9223372036854775807, limit))
            return list(reversed(cur.fetchall()))

    def context(self, owner, cid, question, rid):
        recent = [r for r in self.messages(owner,cid,limit=80) if r['request_id'] != rid]
        tokens = sorted(terms(question), key=lambda word:(-len(word),word))[:6]
        older = []
        if tokens and recent:
            with self.transaction() as cur:
                self.owned(cur,owner,cid)
                # Search the active indexed conversation, never all staff data.
                clauses = ' OR '.join('content LIKE %s' for _ in tokens)
                cur.execute('SELECT * FROM staff_chat_message WHERE conversation_id=%s AND sequence_no<%s AND ('+clauses+') ORDER BY sequence_no DESC LIMIT 48', (cid,recent[0]['sequence_no'], *['%'+t+'%' for t in tokens]))
                older = list(reversed(cur.fetchall()))
        return older+recent

    def rename(self, owner, cid, title):
        with self.transaction() as cur:
            self.owned(cur, owner, cid, True)
            cur.execute('UPDATE staff_chat_session SET title=%s,updated_at=UTC_TIMESTAMP(6) WHERE conversation_id=%s', (title[:160], cid))

    def pending(self, owner, cid):
        with self.transaction() as cur:
            self.owned(cur,owner,cid)
            cur.execute("SELECT request_id FROM staff_chat_request WHERE conversation_id=%s AND status='pending'", (cid,))
            return [r['request_id'] for r in cur.fetchall()]

    def history(self, owner):
        with self.transaction() as cur:
            cur.execute("SELECT a.message_id,a.conversation_id,a.content,a.metadata_json,a.created_at,u.content AS question FROM staff_chat_message a JOIN staff_chat_session s ON s.conversation_id=a.conversation_id JOIN staff_chat_message u ON u.conversation_id=a.conversation_id AND u.request_id=a.request_id AND u.role='user' WHERE s.owner_id=%s AND s.deleted_at IS NULL AND a.role='assistant' ORDER BY a.created_at DESC,a.conversation_id DESC,a.sequence_no DESC LIMIT 100", (owner,))
            return cur.fetchall()

    def delete(self, owner, cid):
        with self.transaction() as cur:
            self.owned(cur, owner, cid, True)
            # Recall replies are derived personal evidence. Erase their copied
            # text and idempotent replay payload when any source is deleted.
            cur.execute("SELECT m.conversation_id,m.request_id FROM staff_chat_message m JOIN staff_chat_session s ON s.conversation_id=m.conversation_id WHERE s.owner_id=%s AND JSON_SEARCH(m.metadata_json,'one',%s,NULL,'$.memory_evidence[*].conversation_id') IS NOT NULL", (owner,cid))
            for linked in cur.fetchall():
                cur.execute("DELETE FROM staff_chat_message WHERE conversation_id=%s AND request_id=%s AND role='assistant'", (linked['conversation_id'],linked['request_id']))
                cur.execute("UPDATE staff_chat_request SET status='invalidated',response_json=NULL WHERE conversation_id=%s AND request_id=%s", (linked['conversation_id'],linked['request_id']))
            cur.execute('UPDATE staff_chat_session SET deleted_at=UTC_TIMESTAMP(6),title=%s WHERE conversation_id=%s', ('Deleted', cid))
            cur.execute('DELETE FROM staff_chat_message WHERE conversation_id=%s', (cid,))
            cur.execute('DELETE FROM staff_chat_request WHERE conversation_id=%s', (cid,))

    def begin(self, owner, cid, rid, question, fingerprint):
        if not isinstance(rid,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,96}', rid) or len(question)>20000:
            raise MemoryError('CHAT_INVALID_REQUEST', 400)
        with self.transaction() as cur:
            session = self.owned(cur, owner, cid, True)
            cur.execute('SELECT * FROM staff_chat_request WHERE conversation_id=%s AND request_id=%s', (cid, rid))
            existing = cur.fetchone()
            if existing:
                if existing['fingerprint'] != fingerprint:
                    raise MemoryError('CHAT_REQUEST_CONFLICT')
                if existing['status'] == 'complete':
                    return decode(existing['response_json'])
                # Never replay uncertain side effects after a crash/timeout.
                raise MemoryError('CHAT_REQUEST_' + existing['status'].upper())
            cur.execute("SELECT request_id FROM staff_chat_request WHERE conversation_id=%s AND status='pending' LIMIT 1", (cid,))
            if cur.fetchone():
                raise MemoryError('CHAT_BUSY')
            cur.execute("INSERT INTO staff_chat_request (conversation_id,request_id,fingerprint,status) VALUES (%s,%s,%s,'pending')", (cid,rid,fingerprint))
            cur.execute("INSERT INTO staff_chat_message (message_id,conversation_id,sequence_no,request_id,role,content) VALUES (%s,%s,%s,%s,'user',%s)", (str(uuid.uuid4()),cid,session['next_sequence'],rid,question))
            cur.execute("UPDATE staff_chat_session SET next_sequence=next_sequence+1,updated_at=UTC_TIMESTAMP(6),title=IF(title='New Chat',%s,title) WHERE conversation_id=%s", (question[:80] or 'Image',cid))
        return None

    def finish(self, owner, cid, rid, payload, status='complete'):
        with self.transaction() as cur:
            session = self.owned(cur, owner, cid, True)
            cur.execute('SELECT status FROM staff_chat_request WHERE conversation_id=%s AND request_id=%s FOR UPDATE', (cid,rid))
            row = cur.fetchone()
            if not row or row['status'] != 'pending':
                raise MemoryError('CHAT_REQUEST_CONFLICT')
            if status == 'complete':
                for source_cid in sorted({e['conversation_id'] for e in payload.get('memory_evidence', [])}):
                    self.owned(cur,owner,source_cid,True)
                mid = str(uuid.uuid4())
                payload.update(conversation_id=cid, message_id=mid, persistence_saved=True)
                text = str(payload.get('answer') or payload.get('reply') or payload.get('message') or '')
                cur.execute("INSERT INTO staff_chat_message (message_id,conversation_id,sequence_no,request_id,role,content,metadata_json) VALUES (%s,%s,%s,%s,'assistant',%s,%s)", (mid,cid,session['next_sequence'],rid,text,json.dumps(payload,ensure_ascii=False)))
                cur.execute('UPDATE staff_chat_session SET next_sequence=next_sequence+1,updated_at=UTC_TIMESTAMP(6) WHERE conversation_id=%s', (cid,))
                image = payload.get('uploaded_image_url')
                if image:
                    cur.execute("UPDATE staff_chat_message SET metadata_json=%s WHERE conversation_id=%s AND request_id=%s AND role='user'", (json.dumps({'image_files':[image]}),cid,rid))
            cur.execute('UPDATE staff_chat_request SET status=%s,response_json=%s,updated_at=UTC_TIMESTAMP(6) WHERE conversation_id=%s AND request_id=%s', (status,json.dumps(payload,ensure_ascii=False) if status=='complete' else None,cid,rid))

    def recall(self, owner, cid, question):
        q = topic_terms(question)
        if not has_topic(q):
            return []
        # Fixed 60-session, 80-message/session ceiling; all indexed owner joins.
        with self.transaction() as cur:
            self.owned(cur, owner, cid)
            cur.execute('SELECT conversation_id FROM staff_chat_session WHERE owner_id=%s AND deleted_at IS NULL AND conversation_id<>%s ORDER BY updated_at DESC,conversation_id DESC LIMIT 60', (owner,cid))
            sessions = cur.fetchall()
            if not sessions:
                return []
            # One round trip for bounded per-session indexed reads, rather than
            # 60 serial queries on every ordinary topic-bearing question.
            queries, params = [], []
            for i, session in enumerate(sessions):
                queries.append("SELECT * FROM (SELECT m.message_id,LEFT(m.content,1000) AS content,m.sequence_no,m.conversation_id FROM staff_chat_message m JOIN staff_chat_session s ON s.conversation_id=m.conversation_id WHERE s.owner_id=%s AND s.deleted_at IS NULL AND s.conversation_id=%s AND m.role='user' ORDER BY m.sequence_no DESC LIMIT 80) AS memory_candidates_"+str(i))
                params.extend((owner,session['conversation_id']))
            cur.execute(' UNION ALL '.join(queries), tuple(params))
            candidates = cur.fetchall()
        # A named current object/qualifier must be present in the old question;
        # a generic shared verb or one word of different equipment is not enough.
        matched = [(r,topic_terms(r['content'])) for r in candidates]
        matched = [(r,topics) for r,topics in matched if q <= topics]
        matched.sort(key=lambda pair: (pair[0]['conversation_id'],-pair[0]['sequence_no']))
        # Detect competing qualifiers before the top-3 cap, so several turns
        # about orange equipment cannot hide a fourth turn about blue equipment.
        ambiguous = len({tuple(sorted(topics-q)) for _,topics in matched}) > 1
        return [dict(r,content=r['content'][:1000],ambiguous_topic=ambiguous) for r,_ in matched[:3]]

    def attach(self, owner, cid, path):
        with self.transaction() as cur:
            self.owned(cur,owner,cid,True)
            cur.execute('INSERT INTO staff_chat_attachment (path,conversation_id) VALUES (%s,%s)', (path,cid))

    def attachment_allowed(self, owner, path, approver=False):
        with self.transaction() as cur:
            cur.execute('SELECT a.path FROM staff_chat_attachment a JOIN staff_chat_session s ON s.conversation_id=a.conversation_id WHERE a.path=%s AND s.owner_id=%s AND s.deleted_at IS NULL', (path,owner))
            if cur.fetchone():
                return True
            # Tickets independently retain necessary attachment evidence.
            exact_json_path = path.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
            cur.execute("SELECT e.escalation_id FROM escalation e WHERE (e.image_url=%s OR EXISTS (SELECT 1 FROM escalation_context ec WHERE ec.escalation_id=e.escalation_id AND JSON_SEARCH(ec.context_json,'one',%s) IS NOT NULL)) AND (e.asked_by=%s OR %s=1) LIMIT 1", (path,exact_json_path,owner,1 if approver else 0))
            return bool(cur.fetchone())


def request_fingerprint(question, data, attachment=b''):
    # Hash relevant inputs, never store attachment bytes or client history/context.
    body = json.dumps({'question':question,'force_escalate':bool(data.get('force_escalate')),
                       'clarification_token':data.get('clarification_token','')},sort_keys=True)
    return hashlib.sha256(body.encode()+attachment).hexdigest()
