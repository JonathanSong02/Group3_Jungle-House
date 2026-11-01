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


def select_history(rows, question, budget=10000):
    """Recent continuity plus older relevant evidence, in original sequence order."""
    rows = [r for r in rows if decode(r.get('metadata_json')).get('source') != 'personal_chat_recall']
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
        if not is_recall(question):
            return []
        q = terms(question)
        if not q:
            return []
        # Fixed 60-session, 80-message/session ceiling; all indexed owner joins.
        with self.transaction() as cur:
            self.owned(cur, owner, cid)
            cur.execute('SELECT conversation_id FROM staff_chat_session WHERE owner_id=%s AND deleted_at IS NULL AND conversation_id<>%s ORDER BY updated_at DESC,conversation_id DESC LIMIT 60', (owner,cid))
            sessions = cur.fetchall()
            candidates = []
            for session in sessions:
                cur.execute("SELECT m.message_id,LEFT(m.content,1000) AS content,m.sequence_no,m.conversation_id FROM staff_chat_message m JOIN staff_chat_session s ON s.conversation_id=m.conversation_id WHERE s.owner_id=%s AND s.deleted_at IS NULL AND s.conversation_id=%s AND m.role='user' ORDER BY m.sequence_no DESC LIMIT 80", (owner,session['conversation_id']))
                candidates.extend(cur.fetchall())
        scored = [(len(q & terms(r['content'])), r) for r in candidates]
        scored = [(score,r) for score,r in scored if score >= min(2,len(q))]
        scored.sort(key=lambda pair: (-pair[0],pair[1]['conversation_id'],-pair[1]['sequence_no']))
        return [dict(r,content=r['content'][:1000]) for _,r in scored[:3]]

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
