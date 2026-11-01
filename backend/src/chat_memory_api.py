"""Thin integration with existing authenticated Flask chat pipeline."""
from flask import g, jsonify, request
from chat_memory_store import ChatMemoryStore, MemoryError, decode, is_recall, request_fingerprint, select_history


def register_chat_memory(app, connect, owner_id, generate, normalizers=()):
    store = ChatMemoryStore(connect)

    def fail(error):
        if isinstance(error, MemoryError):
            return jsonify(code=error.code, message='Chat unavailable or request already processed. Reload this chat before retrying.', persistence_saved=False), error.status
        # No SQL, history, credentials or provider text in diagnostics.
        app.logger.warning('Personal chat storage unavailable (%s)', type(error).__name__)
        return jsonify(code='CHAT_STORAGE_UNAVAILABLE', message='Chat storage is unavailable. Your response was not confirmed saved. Reload before retrying.', persistence_saved=False), 503

    @app.route('/api/chat/sessions', methods=['GET', 'POST'])
    def personal_chat_sessions():
        try:
            if request.method == 'POST':
                return jsonify(store.create(owner_id())), 201
            offset = max(0, min(int(request.args.get('offset', 0)), 100000))
            return jsonify(store.list(owner_id(), offset))
        except ValueError:
            return jsonify(code='CHAT_INVALID_REQUEST'), 400
        except Exception as error:
            return fail(error)

    @app.route('/api/chat/history', methods=['GET'])
    def personal_chat_history():
        try:
            return jsonify(history=[{**decode(r['metadata_json']),'id':r['message_id'],
                'conversation_id':r['conversation_id'],'question':r['question'],'created_at':r['created_at']}
                for r in store.history(owner_id())])
        except Exception as error:
            return fail(error)

    @app.route('/api/chat/sessions/<cid>', methods=['GET', 'PATCH', 'DELETE'])
    def personal_chat_session(cid):
        try:
            if request.method == 'DELETE':
                store.delete(owner_id(), cid)
                return jsonify(success=True)
            if request.method == 'PATCH':
                title = (request.get_json(silent=True) or {}).get('title')
                if not isinstance(title, str) or not title.strip() or len(title)>160:
                    return jsonify(code='CHAT_INVALID_TITLE'), 400
                store.rename(owner_id(), cid, title.strip())
                return jsonify(success=True)
            before = int(request.args.get('before', 9223372036854775807))
            rows = store.messages(owner_id(), cid, before)
            return jsonify(messages=[dict(id=r['message_id'], role=r['role'], content=r['content'],
                                         sequence=r['sequence_no'], created_at=r['created_at'],
                                         metadata=decode(r['metadata_json']), provenance=r['provenance']) for r in rows],
                           next_before=rows[0]['sequence_no'] if len(rows)==200 else None,
                           pending_requests=store.pending(owner_id(),cid))
        except ValueError:
            return jsonify(code='CHAT_INVALID_REQUEST'), 400
        except Exception as error:
            return fail(error)

    @app.route('/api/chat/sessions/<cid>/requests/<rid>/cancel', methods=['POST'])
    def personal_chat_cancel(cid, rid):
        try:
            # Also releases requests left pending by a crashed worker. The old
            # worker cannot commit an assistant message after this transition.
            store.finish(owner_id(), cid, rid, {}, 'cancelled')
            return jsonify(success=True)
        except Exception as error:
            return fail(error)

    def persistent_chat():
        data = request.get_json(silent=True) if request.is_json else request.form
        data = data or {}
        if not hasattr(data,'get'):
            return jsonify(code='CHAT_INVALID_REQUEST'),400
        cid = data.get('conversation_id')
        # Older clients/escalation callers retain the previous route contract.
        if not cid:
            return generate()
        rid = data.get('request_id', '')
        question = data.get('question', '')
        if not isinstance(question, str) or not isinstance(cid, str):
            return jsonify(code='CHAT_INVALID_REQUEST'), 400
        attachment = request.files.get('attachment') or request.files.get('image')
        image_bytes = attachment.read() if attachment else b''
        if attachment:
            attachment.stream.seek(0)
        begun = False
        try:
            # Claim first, then load history excluding the current request.
            cached = store.begin(owner_id(), cid, rid, question, request_fingerprint(question,data,image_bytes))
            if cached is not None:
                return jsonify(cached)
            begun = True
            rows = store.context(owner_id(), cid, question, rid)
            g.personal_chat = True
            g.personal_chat_id = cid
            g.personal_chat_history = select_history(rows, question)
            g.personal_chat_last = next((decode(r['metadata_json']) for r in reversed(rows) if r['role']=='assistant'), {})
            # Recall is evidence display only: no old AI answer becomes policy,
            # active SOP state, or automatic escalation evidence.
            if is_recall(question) and not data.get('force_escalate'):
                try:
                    evidence = store.recall(owner_id(), cid, question)
                    unavailable = False
                except Exception:
                    evidence, unavailable = [], True
                language = data.get('language', 'en')
                labels = {'en':('Your earlier questions:', 'No reliable matching earlier chat was found.', 'Earlier chats are temporarily unavailable.'),
                          'zh':('你之前问过：', '没有找到可靠匹配的历史聊天。', '暂时无法读取历史聊天。'),
                          'ms':('Soalan anda sebelum ini:', 'Tiada sembang lama yang sepadan ditemui.', 'Sembang lama tidak tersedia buat sementara waktu.')}
                label, empty, failed = labels.get(language, labels['en'])
                text = label+'\n'+'\n'.join(r['content'] for r in evidence) if evidence else (failed if unavailable else empty)
                payload = dict(answer=text, reply=text, source='personal_chat_recall', memory_evidence=evidence,
                               memory_diagnostics={'same_chat_messages':0,'cross_chat_messages':len(evidence)},
                               escalation_ready=False, escalation_required=False, fallback=False)
                response = app.make_response(jsonify(payload))
            else:
                response = app.make_response(generate())
                for normalize in normalizers:
                    response = normalize(response)
                payload = response.get_json(silent=True)
            if not isinstance(payload, dict) or response.status_code>=400 or payload.get('cancelled'):
                store.finish(owner_id(),cid,rid,{},'failed')
                return response
            # Apply existing response normalizers before persisting, so reload
            # has exactly the same attachment/snapshot status as the live reply.
            if getattr(g,'uploaded_chat_image_url',None):
                payload['uploaded_image_url'] = g.uploaded_chat_image_url
                payload['uploaded_image_type'] = getattr(g,'uploaded_chat_image_type',None)
            if getattr(g,'chat_escalation_context_saved',None) is not None:
                payload['escalation_context_saved'] = g.chat_escalation_context_saved
                payload['escalation_context_status'] = g.chat_escalation_context_status
            payload.setdefault('memory_diagnostics', {'same_chat_messages':len(g.personal_chat_history),'cross_chat_messages':0})
            store.finish(owner_id(),cid,rid,payload)
            return jsonify(payload), response.status_code
        except Exception as error:
            if begun:
                try:
                    store.finish(owner_id(),cid,rid,{},'failed')
                except Exception:
                    pass
            return fail(error)

    app.add_url_rule('/api/chat', 'chat', persistent_chat, methods=['POST'])
    app.add_url_rule('/chat', 'chat', persistent_chat, methods=['POST'])

    @app.after_request
    def private_chat_no_cache(response):
        if request.path.startswith('/api/chat') or request.path=='/chat':
            response.headers['Cache-Control'] = 'private, no-store'
            response.vary.add('Cookie')
        return response

    return store
