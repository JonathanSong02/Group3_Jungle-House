"""Authenticated persistent chat API; register after the existing app helpers."""
import hashlib
from flask import request, jsonify

from chat_memory import ChatStore, ChatEngine, ChatError, loads, dumps


def register_chat_routes(app, backend):
    store = ChatStore(lambda: backend.get_db_connection())

    def run(action):
        try:
            return jsonify(action()), 200
        except ChatError as error:
            return jsonify(message=str(error), code=error.code), error.status
        except Exception:
            app.logger.exception("Persistent chat request failed")
            return jsonify(message="Chat could not be saved or processed. Retry the same message.",
                           code="CHAT_UNAVAILABLE"), 503

    @app.route('/api/chat/sessions', methods=['GET', 'POST'])
    def persistent_chat_sessions():
        owner = backend.current_auth_user_id()
        if request.method == 'POST':
            return run(lambda: store.create(owner, (request.get_json(silent=True) or {}).get('chat_id')))
        return run(lambda: store.list(owner))

    @app.route('/api/chat/sessions/<chat_id>', methods=['GET', 'DELETE'])
    def persistent_chat_detail(chat_id):
        owner = backend.current_auth_user_id()
        if request.method == 'DELETE':
            return run(lambda: store.hide(owner, chat_id) or {"success": True})

        def read():
            chat, turns = store.read(owner, chat_id)
            return dict(chat_id=chat_id, title=chat['title'], latest_message_id=chat['latest_message_id'], turns=[
                dict(message_id=t['message_id'], request_id=t['request_id'], question=t['original_question'],
                     sequence_no=t['sequence_no'], attachment=loads(t['attachment_json']),
                     response=loads(t['response_json']), status=t['status'])
                for t in turns])
        return run(read)

    @app.route('/api/chat/sessions/<chat_id>/messages', methods=['POST'])
    def persistent_chat_send(chat_id):
        owner = backend.current_auth_user_id()

        def send():
            # Check ownership before upload or provider/config access.
            store.read(owner, chat_id)
            data = request.form.to_dict() if request.mimetype == 'multipart/form-data' else (request.get_json(silent=True) or {})
            attachment = None
            uploaded = request.files.get('attachment') or request.files.get('image')
            existing = store.find_request(owner, chat_id, data.get('request_id'))
            if not uploaded and existing:
                attachment = loads(existing.get('attachment_json'))
            if uploaded:
                digest = hashlib.sha256(uploaded.read()).hexdigest()
                uploaded.seek(0)
                old = loads(existing.get('attachment_json')) if existing else None
                if old:
                    if old.get('sha256') != digest:
                        raise ChatError('Request ID was already used for a different attachment.')
                    attachment = old
                else:
                    url, kind = backend.save_chat_image(uploaded)
                    if not url:
                        raise ChatError('Attachment could not be saved.', 400)
                    attachment = dict(url=url, type=kind, sha256=digest)
            # Resolve one provider snapshot for BOTH calls. Budget is tied to this
            # actual provider/model, not whichever config becomes active later.
            def knowledge(query):
                text, articles = backend.build_ai_chat_context(query, max_chars=12000, search_question=query)
                approved = backend.search_similar_question(query, team_lead_only=True)
                if approved:
                    title = 'Manager-approved answer ' + str(approved.get('id') or approved.get('qa_id') or '')
                    text = '### ' + title + '\n' + str(approved.get('answer') or '') + '\n' + text
                    articles = [dict(title=title, article_id=None)] + articles
                return text, articles

            def describe(attachment):
                path = backend.get_local_image_path_from_url(attachment['url'])
                if not path or not str(attachment.get('type') or '').startswith('image/'):
                    return 'Attached file. Ask the employee which item and operation they mean if not explicit.'
                detected = backend.analyze_uploaded_image_with_vision(path, file_hash=attachment['sha256'])
                return dumps(detected) if detected else 'Image could not be identified reliably; clarify if needed.'

            engine = ChatEngine(store, None, knowledge, configure=backend.ai_provider_service.chat_generator,
                                describe_attachment=describe)
            result = engine.send(owner, chat_id, data, attachment)
            if attachment:
                result['uploaded_image_url'] = attachment['url']
            return result
        return run(send)

    @app.route('/api/chat/sessions/<chat_id>/cancel', methods=['POST'])
    def persistent_chat_cancel(chat_id):
        data = request.get_json(silent=True) or {}
        return run(lambda: store.cancel(backend.current_auth_user_id(), chat_id, data.get('request_id')))

    @app.route('/api/chat/sessions/<chat_id>/import', methods=['POST'])
    def persistent_chat_import(chat_id):
        data = request.get_json(silent=True) or {}
        return run(lambda: store.import_local(backend.current_auth_user_id(), chat_id,
                                              data.get('messages') or [], data.get('title')))

    return store
