"""Phone / browser push notifications when the AI is done (2026-11-26, step 2).

The encryption is checked against the worked example in RFC 8291 Appendix A
(the official Web Push standard), byte for byte. Sending, VAPID signing and
the database are faked. Run:
python -m unittest discover -s backend/src -p test_web_push.py
"""

import base64
import json
import unittest
from unittest import mock

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

import web_push


def b64(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# RFC 8291, Appendix A
RFC_PLAINTEXT = b"When I grow up, I want to be a watermelon"
RFC_AS_PRIVATE = "yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"
RFC_AS_PUBLIC = "BP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A8"
RFC_UA_PUBLIC = "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4"
RFC_UA_PRIVATE = "q1dXpw3UpT5VOmu_cf_v6ih07Aems3njxI-JWgLcM94"
RFC_AUTH = "BTBZMqHH6r4Tts7J_aSIgg"
RFC_SALT = "DGv6ra1nlYgDCS1FRnbzlw"
RFC_BODY = ("DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3"
            "jl7A_yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN")


def private_key_from(raw_b64):
    return ec.derive_private_key(int.from_bytes(b64(raw_b64), "big"), ec.SECP256R1())


class EncryptionTests(unittest.TestCase):
    def test_matches_the_rfc_8291_example_exactly(self):
        body = web_push.encrypt(RFC_PLAINTEXT, RFC_UA_PUBLIC, RFC_AUTH,
                                server_private_key=private_key_from(RFC_AS_PRIVATE), salt=b64(RFC_SALT))
        self.assertEqual(body, b64(RFC_BODY))

    def test_the_rfc_example_keys_are_consistent(self):
        public = private_key_from(RFC_AS_PRIVATE).public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        self.assertEqual(public, b64(RFC_AS_PUBLIC))

    def test_fresh_keys_and_salt_every_time(self):
        first = web_push.encrypt(b"x", RFC_UA_PUBLIC, RFC_AUTH)
        second = web_push.encrypt(b"x", RFC_UA_PUBLIC, RFC_AUTH)
        self.assertNotEqual(first[:16], second[:16])          # salt
        self.assertEqual(first[16:20], (4096).to_bytes(4, "big"))  # record size
        self.assertEqual(first[20], 65)                       # key id length

    def test_bad_subscription_keys_are_refused(self):
        with self.assertRaises(ValueError):
            web_push.encrypt(b"x", "AAAA", RFC_AUTH)
        with self.assertRaises(ValueError):
            web_push.encrypt(b"x", RFC_UA_PUBLIC, "AAAA")


class VapidTests(unittest.TestCase):
    def test_token_is_a_valid_es256_signature_for_the_push_service(self):
        key = ec.generate_private_key(ec.SECP256R1())
        token = web_push.vapid_token(key, "https://fcm.googleapis.com/fcm/send/abc123", "https://jh.example", now=1_000)
        header, claims, signature = token.split(".")
        self.assertEqual(json.loads(b64(header)), {"typ": "JWT", "alg": "ES256"})
        self.assertEqual(json.loads(b64(claims)), {"aud": "https://fcm.googleapis.com", "exp": 1_000 + 12 * 3600,
                                                   "sub": "https://jh.example"})
        raw = b64(signature)
        self.assertEqual(len(raw), 64)
        der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
        key.public_key().verify(der, f"{header}.{claims}".encode(), ec.ECDSA(hashes.SHA256()))  # raises if wrong

    def test_subject_falls_back_to_a_mailto(self):
        key = ec.generate_private_key(ec.SECP256R1())
        claims = json.loads(b64(web_push.vapid_token(key, "https://web.push.apple.com/x", "", now=0).split(".")[1]))
        self.assertTrue(claims["sub"].startswith("mailto:"))

    def test_key_round_trip(self):
        private_text, public_text = web_push.new_key_pair()
        key = web_push.load_private_key(private_text)
        public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        self.assertEqual(web_push.b64url(public), public_text)
        self.assertEqual(len(b64(public_text)), 65)


class FakeResponse:
    def __init__(self, status):
        self.status_code = status


class SendTests(unittest.TestCase):
    def subscription(self, endpoint="https://fcm.googleapis.com/fcm/send/abc"):
        return {"endpoint": endpoint, "p256dh": RFC_UA_PUBLIC, "auth": RFC_AUTH, "subject": "https://jh.example"}

    def test_request_has_the_standard_headers(self):
        key = ec.generate_private_key(ec.SECP256R1())
        calls = []
        post = lambda url, data, headers, timeout: calls.append((url, data, headers, timeout)) or FakeResponse(201)
        outcome = web_push.send(self.subscription(), {"title": "AI answer is ready"}, key, "PUBKEY", post=post)
        self.assertEqual(outcome, "sent")
        url, data, headers, timeout = calls[0]
        self.assertEqual(url, "https://fcm.googleapis.com/fcm/send/abc")
        self.assertEqual(headers["Content-Encoding"], "aes128gcm")
        self.assertTrue(headers["Authorization"].startswith("vapid t="))
        self.assertTrue(headers["Authorization"].endswith(", k=PUBKEY"))
        self.assertEqual(headers["TTL"], str(web_push.TTL_SECONDS))
        self.assertEqual(headers["Urgency"], "high")
        self.assertLessEqual(timeout, 10)
        self.assertGreater(len(data), 86)

    def test_gone_subscription_is_reported(self):
        key = ec.generate_private_key(ec.SECP256R1())
        for status in (404, 410):
            self.assertEqual(web_push.send(self.subscription(), {}, key, "K", post=lambda *a, **k: FakeResponse(status)), "gone")
        self.assertEqual(web_push.send(self.subscription(), {}, key, "K", post=lambda *a, **k: FakeResponse(500)), "failed")

    def test_network_error_is_reported_not_raised(self):
        def boom(*args, **kwargs):
            raise OSError("no route")
        key = ec.generate_private_key(ec.SECP256R1())
        self.assertEqual(web_push.send(self.subscription(), {}, key, "K", post=boom), "failed")

    def test_only_https_push_services_are_used(self):
        key = ec.generate_private_key(ec.SECP256R1())
        posted = []
        for endpoint in ("http://fcm.googleapis.com/x", "https://127.0.0.1/x", "https://localhost/x", "file:///etc",
                         "https://evil.example/x", "https://fcm.googleapis.com.evil.example/x",
                         "https://user@fcm.googleapis.com:8443/x"):
            self.assertEqual(web_push.send(self.subscription(endpoint), {}, key, "K",
                                           post=lambda *a, **k: posted.append(a) or FakeResponse(201)), "refused")
        self.assertEqual(posted, [])

    def test_the_real_push_services_are_allowed(self):
        for endpoint in ("https://fcm.googleapis.com/fcm/send/a", "https://updates.push.services.mozilla.com/wpush/v2/a",
                         "https://web.push.apple.com/a", "https://wns2-par02p.notify.windows.com/w/?token=a"):
            self.assertTrue(web_push.allowed_endpoint(endpoint), endpoint)


class SeenTests(unittest.TestCase):
    def test_seen_marks_expire(self):
        web_push.mark_seen(7, "abc", now=100)
        self.assertTrue(web_push.was_seen(7, "abc", now=150))
        self.assertFalse(web_push.was_seen(8, "abc", now=150))
        self.assertFalse(web_push.was_seen(7, "abc", now=100 + web_push.SEEN_KEEP_SECONDS + 1))


if __name__ == "__main__":
    unittest.main()


# ------------------------------------------------------------- app.py wiring
import os  # noqa: E402

os.environ.setdefault("FLASK_SECRET_KEY", "dummy-test-only-key-not-a-secret-0123456789")
os.environ.setdefault("NOTION_AUTO_SYNC_ENABLED", "false")
os.environ.setdefault("IMAGE_INDEX_WORKER_ENABLED", "false")
os.environ.setdefault("DOCUMENT_TEXT_BACKFILL", "false")

import app as app_module  # noqa: E402

flask_app = app_module.app


def run_save_hook(path, body, endpoint, status=200):
    """The real after_request hook; returns the background jobs it started."""
    jobs = []
    with flask_app.test_request_context(path, method="POST", json=body):
        from flask import g, request
        request.url_rule = mock.Mock(endpoint=endpoint)
        g.auth_user = {"user_id": 7}
        with mock.patch.object(app_module, "current_auth_user_id", return_value=7), \
                mock.patch.object(app_module, "run_in_background", side_effect=lambda fn, *a: jobs.append((fn, a))):
            reply = flask_app.response_class(json.dumps({"reply": "x"}), status=status, mimetype="application/json")
            app_module.save_ai_task_result_copy(reply)
    return jobs


class PushAfterReplyTests(unittest.TestCase):
    def test_chat_reply_schedules_a_push_for_that_chat(self):
        jobs = run_save_hook("/api/chat", {"request_id": "r1", "chat_session_id": "main-1764000000000"}, "chat")
        push = [args for fn, args in jobs if fn is web_push.notify_user]
        self.assertEqual(len(push), 1)
        self.assertEqual(push[0][1:], (7, "r1", "chat", "1764000000000", app_module.PUSH_WAIT_SECONDS))
        self.assertEqual(app_module.PUSH_WAIT_SECONDS, 4)

    def test_floating_or_odd_session_ids_are_not_passed_on(self):
        jobs = run_save_hook("/api/chat", {"request_id": "r1", "chat_session_id": "floating-<script>"}, "chat")
        push = [args for fn, args in jobs if fn is web_push.notify_user]
        self.assertIsNone(push[0][4])

    def test_successful_quiz_pushes_but_a_failed_one_does_not(self):
        ok = run_save_hook("/api/admin/quizzes/ai-generate", {"request_id": "q1"}, "ai_generate_quiz")
        failed = run_save_hook("/api/admin/quizzes/ai-generate", {"request_id": "q2"}, "ai_generate_quiz", status=502)
        self.assertEqual(sum(fn is web_push.notify_user for fn, _ in ok), 1)
        self.assertEqual(sum(fn is web_push.notify_user for fn, _ in failed), 0)

    def test_no_request_id_no_push(self):
        self.assertEqual(run_save_hook("/api/chat", {"question": "x"}, "chat"), [])


class NotifyUserTests(unittest.TestCase):
    def test_no_push_when_the_page_already_showed_it(self):
        web_push.mark_seen(7, "seen-1")
        with mock.patch.object(web_push, "subscriptions_for") as subs:
            web_push.notify_user(None, 7, "seen-1", "chat", "1", 4, sleep=lambda s: None)
        subs.assert_not_called()

    def test_push_goes_to_every_device_and_gone_ones_are_removed(self):
        rows = [{"endpoint": "https://fcm.googleapis.com/a", "labels": '{"chat": "AI 回答好了", "view": "点这里查看"}'},
                {"endpoint": "https://web.push.apple.com/b", "labels": "{}"}]
        sent = []
        with mock.patch.object(web_push, "subscriptions_for", return_value=rows), \
                mock.patch.object(web_push, "server_keys", return_value=("KEY", "PUB")), \
                mock.patch.object(web_push, "send", side_effect=lambda row, payload, *a: sent.append(payload) or
                                  ("gone" if "apple" in row["endpoint"] else "sent")), \
                mock.patch.object(web_push, "delete_subscription") as delete:
            web_push.notify_user("conn", 7, "new-1", "chat", "42", 4, sleep=lambda s: None)
        self.assertEqual(sent[0], {"title": "AI 回答好了", "body": "点这里查看", "url": "/chat?aiSession=42",
                                   "kind": "chat", "sessionId": "42", "tag": "jh-ai-chat-42"})
        self.assertEqual(sent[1]["title"], "AI answer is ready")   # no saved words: English
        delete.assert_called_once_with("conn", "https://web.push.apple.com/b")

    def test_quiz_notification_opens_the_quiz_page(self):
        self.assertEqual(web_push.notification_for("quiz", None, "{}")["url"], "/admin/quiz-management")


class PushRouteTests(unittest.TestCase):
    def call(self, view, path, body=None, method="POST", **patches):
        with flask_app.test_request_context(path, method=method, json=body,
                                            headers={"Origin": "https://jh.example"}), \
                mock.patch.object(app_module, "current_auth_user_id", return_value=7):
            stack = [mock.patch.object(web_push, name, **spec) for name, spec in patches.items()]
            mocks = [p.start() for p in stack]
            try:
                reply = view()
            finally:
                for p in stack:
                    p.stop()
            reply = flask_app.make_response(reply)
            return reply, mocks

    def test_public_key(self):
        reply, _ = self.call(app_module.get_push_public_key, "/api/push/public-key", method="GET",
                             server_keys={"return_value": ("KEY", "PUBLIC")})
        self.assertEqual(reply.get_json(), {"publicKey": "PUBLIC"})

    def test_subscribe_saves_for_the_signed_in_user_with_the_site_address(self):
        body = {"subscription": {"endpoint": "https://fcm.googleapis.com/a", "keys": {"p256dh": "P", "auth": "A"}},
                "labels": {"chat": "x"}}
        reply, (save,) = self.call(app_module.subscribe_push, "/api/push/subscribe", body,
                                   save_subscription={"return_value": True})
        self.assertEqual(reply.status_code, 200)
        self.assertEqual(save.call_args.args[1:], (7, body["subscription"], body["labels"], "https://jh.example"))

    def test_unusable_subscription_is_400(self):
        reply, _ = self.call(app_module.subscribe_push, "/api/push/subscribe", {"subscription": {}},
                             save_subscription={"return_value": False})
        self.assertEqual(reply.status_code, 400)

    def test_unsubscribe_only_touches_own_rows(self):
        reply, (delete,) = self.call(app_module.unsubscribe_push, "/api/push/unsubscribe", {"endpoint": "https://x"},
                                     delete_subscription={})
        self.assertEqual(reply.status_code, 200)
        self.assertEqual(delete.call_args.args[1:], ("https://x",))
        self.assertEqual(delete.call_args.kwargs, {"user_id": 7})

    def test_seen_mark(self):
        with flask_app.test_request_context("/api/ai-tasks/r9/seen", method="POST"), \
                mock.patch.object(app_module, "current_auth_user_id", return_value=7):
            reply = flask_app.make_response(app_module.mark_ai_task_seen("r9"))
        self.assertEqual(reply.status_code, 200)
        self.assertTrue(web_push.was_seen(7, "r9"))

    def test_routes_are_for_every_signed_in_role(self):
        for name in ("get_push_public_key", "subscribe_push", "unsubscribe_push", "mark_ai_task_seen"):
            self.assertNotIn(name, app_module._MANAGER_ENDPOINTS)
            self.assertNotIn(name, app_module._APPROVER_ENDPOINTS)
