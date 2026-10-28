"""Isolated chat regression tests. Extract actual functions without importing app,
starting Notion sync, or contacting a database/provider. Not Flask E2E tests.
Run: python -m unittest discover -s backend/src -p test_chat_memory.py
"""

import ast, json, re, types, unittest, base64, hashlib, hmac, time
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import Mock, patch

source = Path(__file__).with_name("app.py").read_text(encoding="utf-8")
compile(source, "app.py", "exec")
tree = ast.parse(source)
names = {"clean_question", "is_nonsense", "normalize_context", "get_chat_memory_key",
         "prepare_chat_context", "remember_chat_context", "get_last_answer_key", "get_chat_session_id",
         "get_ai_fail_key", "is_staff_not_satisfied", "validate_conversation_history",
         "needs_conversation_context", "resolve_conversation_search_query", "is_explicit_answer_rejection",
         "make_clarification_token", "read_clarification_token"}
env = {"re": re, "json": json, "CJK_CHAR_RE": re.compile(r"[\u3400-\u9fff]"),
       "datetime": datetime, "timezone": timezone, "request": types.SimpleNamespace(remote_addr="local", is_json=True),
       "AI_CHAT_MEMORY": {}, "base64": base64, "hashlib": hashlib, "hmac": hmac, "time": time,
       "app": types.SimpleNamespace(secret_key="isolated-test-only")}
nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
for n in tree.body:
    if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in {"_MALAY_GREETINGS", "_PINYIN_GREETINGS"} for t in n.targets):
        nodes.append(n)
exec(compile(ast.Module(body=nodes, type_ignores=[]), "selected_app_helpers.py", "exec"), env)
chat = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "chat")
guard = next(n for n in ast.walk(chat) if isinstance(n, ast.If) and isinstance(n.test, ast.BoolOp) and isinstance(n.test.values[0], ast.Attribute) and n.test.values[0].attr == "is_json")
gate_src = "def run_gate(data, question, question_for_search, malay_expanded_question, uploaded_chat_image=None, chat_request_id='test'):\n"
gate_src += "    conversation_query_was_resolved = False\n"
gate_src += "\n".join("    " + line for line in ast.unparse(guard).splitlines())
gate_src += "\n    return question_for_search, conversation_query_was_resolved\n"
exec(gate_src, env)
env["jsonify"] = lambda obj: obj

class Cursor:
    def __init__(self): self.closed = False
    def close(self): self.closed = True
class Connection:
    def __init__(self, cur): self.cur=cur; self.closed=False
    def cursor(self, **kwargs): return self.cur
    def close(self): self.closed=True

class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.history = [{"role":"user", "content":"Golden Passion honey price"},
                        {"role":"assistant", "content":"An earlier answer, not verified policy."}]
        self.cursor=Cursor(); self.conn=Connection(self.cursor)
        self.provider=types.SimpleNamespace(
            get_db_connection=Mock(return_value=self.conn),
            get_active_ai_provider_config=Mock(return_value={"encrypted_api_key":"mock-only", "provider":"mock", "model_name":"mock"}),
            decrypt_api_key=Mock(return_value="mock-only"),
            _call_ai_provider_once=Mock(return_value=json.dumps({"query":"Golden Passion honey benefits", "subject":"Golden Passion honey", "evidence_index":0, "topic_index":0})))
        env["ai_provider_service"]=self.provider
        env["AI_PROVIDER_SERVICE_AVAILABLE"]=True
        env["is_chat_request_cancelled"]=Mock(return_value=False)
        env["request"].is_json=True
    def resolve(self, history=None, question="And its benefits?", search=None):
        return env["resolve_conversation_search_query"](question, search or question, self.history if history is None else history, "mock")
    def test_valid_history(self):
        self.assertEqual(env["validate_conversation_history"](self.history), self.history)
    def test_malformed_history(self):
        for bad in [None, {}, "text", [], [1], [{"role":"system","content":"x"}],
                    [{"role":"user","content":1}], [{"role":"user","content":""}],
                    [{"role":"assistant","content":"x"}],
                    [{"role":"user","content":"<b>html</b>"}],
                    [{"role":"user","content":"data:image/png;base64,x"}]]:
            with self.subTest(bad=bad): self.assertEqual(env["validate_conversation_history"](bad), [])
    def test_history_size_limits(self):
        for bad in [[{"role":"user","content":"x"*1001}],
                    [{"role":"user","content":"x"}]*17,
                    [{"role":"user","content":"x"*1000}]*13]:
            self.assertEqual(env["validate_conversation_history"](bad), [])
    def test_followups_all_languages(self):
        for q in ["And its benefits?", "How about opening?", "那它呢？", "那开店呢？",
                  "Kalau buka kedai?", "Khasiat dia?", "Correction, I mean ST3."]:
            with self.subTest(q=q): self.assertTrue(env["needs_conversation_context"](q,q,q))
    def test_controls_and_standalone_skipped(self):
        for q in ["hi","hello","你好","selamat pagi","asdfgh","Step 4","next","not this",
                  "show me step 4","下一步","kiosk opening","Golden Passion honey price",
                  "What is Golden Passion honey and its benefits?", "Honey shelf life"]:
            with self.subTest(q=q): self.assertFalse(env["needs_conversation_context"](q,q,q))
    def test_product_followup_one_call(self):
        self.assertEqual(self.resolve(), ("Golden Passion honey benefits",False))
        self.provider._call_ai_provider_once.assert_called_once()
        self.assertEqual(self.provider._call_ai_provider_once.call_args.kwargs["timeout"],8)
        self.assertTrue(self.conn.closed and self.cursor.closed)
    def test_closing_to_opening(self):
        h=[{"role":"user","content":"ST3 kiosk closing"}]
        self.provider._call_ai_provider_once.return_value=json.dumps({"query":"ST3 kiosk opening","subject":"ST3","evidence_index":0})
        self.assertEqual(self.resolve(h,"How about opening?"),("ST3 kiosk opening",False))
    def test_current_correction(self):
        h=[{"role":"user","content":"kiosk closing at Spring"}]
        self.provider._call_ai_provider_once.return_value=json.dumps({"query":"ST3 kiosk closing","subject":"ST3","evidence_index":-1,"topic_index":0})
        self.assertEqual(self.resolve(h,"Correction, I mean ST3."),("ST3 kiosk closing",False))
    def test_current_correction_rejects_old_subject(self):
        h=[{"role":"user","content":"kiosk closing at Spring"}]
        self.provider._call_ai_provider_once.return_value=json.dumps({"query":"Spring kiosk closing","subject":"Spring","evidence_index":0,"topic_index":0})
        self.assertEqual(self.resolve(h,"Correction, I mean ST3."),("Correction, I mean ST3.",False))
    def test_later_followup_rejects_superseded_subject(self):
        h=[{"role":"user","content":"kiosk closing at Spring"},{"role":"assistant","content":"old answer"},
           {"role":"user","content":"Correction, I mean ST3."}]
        self.provider._call_ai_provider_once.return_value=json.dumps({"query":"Spring kiosk opening","subject":"Spring","evidence_index":0,"topic_index":0})
        self.assertEqual(self.resolve(h,"How about opening?"),("How about opening?",False))
    def test_later_followup_uses_correction(self):
        h=[{"role":"user","content":"kiosk closing at Spring"},{"role":"assistant","content":"old answer"},
           {"role":"user","content":"Correction, I mean ST3."}]
        self.provider._call_ai_provider_once.return_value=json.dumps({"query":"ST3 kiosk opening","subject":"ST3","evidence_index":2,"topic_index":0})
        self.assertEqual(self.resolve(h,"How about opening?"),("ST3 kiosk opening",False))
    def test_unusable_provider_outputs_fallback(self):
        for raw in ["bad", "[]", "{}", "x"*501, json.dumps({"query":"Invented honey benefits","subject":"Invented honey","evidence_index":0}),
                    json.dumps({"query":"Golden Passion honey benefits","subject":"Golden Passion honey","evidence_index":1}),
                    json.dumps({"query":"Golden Passion honey policy","subject":"Golden Passion honey","evidence_index":0})]:
            with self.subTest(raw=raw):
                self.provider._call_ai_provider_once.return_value=raw
                self.assertEqual(self.resolve(),("And its benefits?",False))
    def test_provider_failure_and_timeout_no_retry(self):
        for error in [TimeoutError("mock"), RuntimeError("mock")]:
            self.provider._call_ai_provider_once.reset_mock()
            self.provider._call_ai_provider_once.side_effect=error
            self.assertEqual(self.resolve(),("And its benefits?",False))
            self.provider._call_ai_provider_once.assert_called_once()
    def test_provider_unavailable(self):
        env["AI_PROVIDER_SERVICE_AVAILABLE"]=False
        self.assertEqual(self.resolve(),("And its benefits?",False))
        self.provider._call_ai_provider_once.assert_not_called()
    def test_provider_unconfigured(self):
        self.provider.get_active_ai_provider_config.return_value=None
        self.assertEqual(self.resolve(),("And its benefits?",False))
        self.provider._call_ai_provider_once.assert_not_called()
    def test_cancel_before_config(self):
        env["is_chat_request_cancelled"].return_value=True
        self.assertEqual(self.resolve(),("And its benefits?",True))
        self.provider.get_db_connection.assert_not_called()
        self.provider._call_ai_provider_once.assert_not_called()
    def test_cancel_before_provider(self):
        env["is_chat_request_cancelled"].side_effect=[False,True]
        self.assertEqual(self.resolve(),("And its benefits?",True))
        self.provider._call_ai_provider_once.assert_not_called()
    def test_cancel_during_provider(self):
        env["is_chat_request_cancelled"].side_effect=[False,False,True]
        self.assertEqual(self.resolve(),("And its benefits?",True))
        self.provider._call_ai_provider_once.assert_called_once()
    def test_cancel_with_provider_failure(self):
        env["is_chat_request_cancelled"].side_effect=[False,False,True]
        self.provider._call_ai_provider_once.side_effect=TimeoutError("mock")
        self.assertEqual(self.resolve(),("And its benefits?",True))
    def test_gate_standalone_no_call(self):
        q="Golden Passion honey price"
        self.assertEqual(env["run_gate"]({"history":self.history},q,q,q),(q,False))
        self.provider._call_ai_provider_once.assert_not_called()
    def test_gate_missing_invalid_history_image_force_no_call(self):
        q="And its benefits?"
        for data,image in [({},None),({"history":"bad"},None),({"history":self.history},object()),
                           ({"history":self.history,"force_escalate":True},None)]:
            env["run_gate"](data,q,q,q,image)
        self.provider._call_ai_provider_once.assert_not_called()
    def test_gate_multipart_no_call(self):
        env["request"].is_json=False
        q="And its benefits?"
        env["run_gate"]({"history":self.history},q,q,q)
        self.provider._call_ai_provider_once.assert_not_called()
    def test_gate_resolved_query(self):
        q="And its benefits?"
        self.assertEqual(env["run_gate"]({"history":self.history},q,q,q),("Golden Passion honey benefits",True))
    def test_gate_cancel_returns_existing_stop_response(self):
        env["is_chat_request_cancelled"].return_value=True
        q="And its benefits?"
        result,status=env["run_gate"]({"history":self.history},q,q,q)
        self.assertEqual(status,200)
        self.assertTrue(result["cancelled"])
        self.provider._call_ai_provider_once.assert_not_called()
    def test_legacy_callers_retain_user_scoped_context(self):
        env["AI_CHAT_MEMORY"].clear()
        first={"user_id":7,"context":{"title":"ST3 kiosk closing","last_step_number":3}}
        env["remember_chat_context"](first,{"context":first["context"]})
        new={"user_id":7,"context":{}}
        self.assertEqual(env["prepare_chat_context"](new)["title"],"ST3 kiosk closing")
        self.assertEqual(env["get_last_answer_key"](first),env["get_last_answer_key"](new))
        self.assertEqual(env["get_ai_fail_key"](first),env["get_ai_fail_key"](new))

    def test_history_unchanged_and_prompt_bounded(self):
        history=[{"role":"user","content":"Golden Passion honey price " + "a"*950}]*12
        before=json.dumps(history)
        self.resolve(history=history)
        self.assertEqual(json.dumps(history),before)
        self.assertLess(len(self.provider._call_ai_provider_once.call_args.args[0]),16000)
    def test_unrelated_topic_after_correction(self):
        h=[{"role":"user","content":"kiosk closing at Spring"},
           {"role":"user","content":"Correction, I mean ST3."},
           {"role":"user","content":"Golden Passion honey price"}]
        self.provider._call_ai_provider_once.return_value=json.dumps({"query":"Golden Passion honey benefits","subject":"Golden Passion honey","evidence_index":2,"topic_index":2})
        self.assertEqual(self.resolve(h),("Golden Passion honey benefits",False))
    def test_decryption_failure_falls_back_without_call(self):
        self.provider.decrypt_api_key.side_effect=RuntimeError("mock")
        self.assertEqual(self.resolve(),("And its benefits?",False))
        self.provider._call_ai_provider_once.assert_not_called()
    def test_gate_preserves_original_question(self):
        q="And its benefits?"
        env["run_gate"]({"history":self.history},q,q,q)
        prompt=self.provider._call_ai_provider_once.call_args.args[0]
        data=json.loads(prompt.split("DATA:\n",1)[1])
        self.assertEqual(data["question"],q)

    def test_cleanup_failure_is_optional(self):
        self.conn.close=Mock(side_effect=RuntimeError("mock"))
        self.assertEqual(self.resolve(),("And its benefits?",False))


import copy
selected=[]
for name in ["chat","answer_question_with_ai_provider","validate_escalation_context","create_chat_escalation","attach_escalation_context_status"]:
    node=copy.deepcopy(next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name))
    node.decorator_list=[]
    selected.append(node)
exec(compile(ast.Module(body=selected,type_ignores=[]),"actual_chat_and_answer_functions.py","exec"),env)
chat=env["chat"]

class ChatRouteTests(unittest.TestCase):
    # Inherit only setup, run the tests declared below.
    def setUp(self):
        MemoryTests.setUp(self)
        self.payload={"question":"And its benefits?","history":self.history,"request_id":"mock","user_id":9999}
        env["request"]=types.SimpleNamespace(content_type="application/json",is_json=True,
            get_json=lambda **kwargs:self.payload,remote_addr="local",form={},files={})
        env["current_auth_user_id"]=Mock(return_value=7)
        env["g"]=types.SimpleNamespace()
        env["AI_CHAT_MEMORY"].clear()
        env["AI_LAST_ANSWER_MEMORY"]={}
        env["AI_FAIL_MEMORY"]={}
        env["CONFIDENCE_DIRECT_ANSWER"]=.72
        env["expand_malay_shorthand"]=Mock(side_effect=lambda q:(q,False))
        env["normalize_staff_query"]=Mock(side_effect=lambda q:(q,False))
        env["correct_chinese_homophones"]=Mock(side_effect=lambda q:q)
        env["detect_question_language"]=Mock(return_value="en")
        env["translate_query_to_english_keywords"]=Mock(side_effect=lambda q,lang:q)
        env["is_broad_topic_question"]=Mock(return_value=False)
        env["search_similar_question"]=Mock(return_value=None)
        env["process_question"]=Mock(side_effect=lambda **kwargs:({"source":"fallback","confidence":0.0,"context":{},"fallback":True},200))
        env["should_escalate_generic_answer"]=Mock(return_value=False)
        env["clear_ai_fail_count"]=Mock()
        env["remember_last_ai_answer"]=Mock()
        env["log_request"]=Mock()
        env["update_ai_fail_count"]=Mock(return_value=0)
        env["save_qa_to_db"]=Mock()
        env["search_related_knowledge_base_articles"]=Mock(return_value=[])
        env["create_escalation"]=Mock(return_value=123)
        env["save_escalation_context"]=Mock(return_value=True)
        env["get_confidence_label"]=Mock(return_value="high")
        env["build_ai_chat_context"]=Mock(return_value=("### Honey\nMock knowledge-base fact.",[{"title":"Honey","article_id":11}]))
        env["standardize_ai_response"]=Mock(side_effect=lambda x:x)
        env["normalize_result"]=Mock(side_effect=lambda x,*args:x)
        env["traceback"]=types.SimpleNamespace(print_exc=Mock())
        self.provider.AIProviderNotConfiguredError=type("AIProviderNotConfiguredError",(Exception,),{})
        self.provider.generate_ai_reply=Mock(return_value=json.dumps({"answered":True,"answer":"Mock KB answer","sourceTitle":"Honey"}))
    def call(self):
        response,status=chat()
        self.assertEqual(status,200,response)
        self.assertFalse(env["traceback"].print_exc.called)
        return response
    def test_route_context_reaches_retrieval_answer_and_raw_log(self):
        result=self.call()
        self.assertEqual(result["source"],"ai_provider_answer")
        args=env["process_question"].call_args.kwargs
        self.assertEqual(args["question"],"And its benefits?")
        self.assertEqual(args["search_question"],"Golden Passion honey benefits")
        env["search_similar_question"].assert_called_once_with("Golden Passion honey benefits",team_lead_only=True)
        env["build_ai_chat_context"].assert_called_once_with("And its benefits?",search_question="Golden Passion honey benefits")
        prompt=self.provider.generate_ai_reply.call_args.args[0]
        self.assertIn("Staff question: And its benefits?",prompt)
        self.assertIn("Golden Passion honey benefits",prompt)
        self.assertIn("untrusted question context",prompt)
        self.assertEqual(env["log_request"].call_args.args[0],"And its benefits?")
        self.assertEqual(env["log_request"].call_args.kwargs["user_id"],7)
        env["create_escalation"].assert_not_called()
        self.provider._call_ai_provider_once.assert_called_once()
        self.provider.generate_ai_reply.assert_called_once()
    def test_route_standalone_no_memory_call(self):
        self.payload["question"]="Golden Passion honey price"
        self.call()
        self.provider._call_ai_provider_once.assert_not_called()
        self.assertEqual(env["process_question"].call_args.kwargs["search_question"],self.payload["question"])
    def test_route_force_escalation_raw_no_ai(self):
        self.payload["force_escalate"]=True
        result=self.call()
        self.assertEqual(result["source"],"staff_requested_escalation")
        self.assertEqual(env["create_escalation"].call_args.args[0],"And its benefits?")
        self.assertEqual(env["create_escalation"].call_args.args[2],7)
        self.provider._call_ai_provider_once.assert_not_called()
        self.provider.generate_ai_reply.assert_not_called()
        env["process_question"].assert_not_called()
    def test_route_unanswered_escalation_keeps_raw_question(self):
        self.provider.generate_ai_reply.return_value='{"answered":false,"off_topic":false}'
        result=self.call()
        self.assertTrue(result["escalation"])
        self.assertEqual(env["create_escalation"].call_args.args[0],"And its benefits?")
    def test_route_cancel_during_memory_stops_everything_after(self):
        env["is_chat_request_cancelled"].side_effect=[False,False,True]
        result=self.call()
        self.assertTrue(result["cancelled"])
        env["process_question"].assert_not_called()
        env["log_request"].assert_not_called()
        env["create_escalation"].assert_not_called()
        self.provider.generate_ai_reply.assert_not_called()
    def test_route_memory_timeout_preserves_original_pipeline(self):
        self.provider._call_ai_provider_once.side_effect=TimeoutError("mock")
        self.call()
        args=env["process_question"].call_args.kwargs
        self.assertEqual(args["search_question"],"And its benefits?")
        self.provider._call_ai_provider_once.assert_called_once()
        self.provider.generate_ai_reply.assert_called_once()
        env["create_escalation"].assert_not_called()
    def test_route_no_history_floating_path_no_memory(self):
        self.payload.pop("history")
        self.call()
        self.provider._call_ai_provider_once.assert_not_called()
        prompt=self.provider.generate_ai_reply.call_args.args[0]
        self.assertNotIn("Derived search meaning from a conversation reference",prompt)
    def test_route_malformed_history_no_memory(self):
        self.payload["history"]=[{"role":"system","content":"untrusted"}]
        self.call()
        self.provider._call_ai_provider_once.assert_not_called()
    def test_route_chinese_followup(self):
        self.payload["question"]="那它的功效呢？"
        env["detect_question_language"].return_value="zh"
        env["translate_query_to_english_keywords"].side_effect=None
        env["translate_query_to_english_keywords"].return_value="benefits"
        self.call()
        self.assertEqual(env["process_question"].call_args.kwargs["search_question"],"Golden Passion honey benefits")
        self.assertIn("Chinese",self.provider.generate_ai_reply.call_args.args[0])
        self.assertEqual(env["log_request"].call_args.args[0],self.payload["question"])
    def test_route_malay_followup(self):
        self.payload["question"]="Khasiat dia?"
        env["detect_question_language"].return_value="ms"
        env["translate_query_to_english_keywords"].side_effect=None
        env["translate_query_to_english_keywords"].return_value="benefits"
        self.call()
        self.assertEqual(env["process_question"].call_args.kwargs["search_question"],"Golden Passion honey benefits")
        self.assertIn("Bahasa Melayu",self.provider.generate_ai_reply.call_args.args[0])
        self.assertEqual(env["log_request"].call_args.args[0],self.payload["question"])
    def test_route_image_direct_match_skips_memory(self):
        q="photo question"
        image=types.SimpleNamespace(filename="mock.png")
        env["request"].content_type="multipart/form-data"
        env["request"].is_json=False
        env["request"].form={"question":q,"context":"{}","request_id":"mock"}
        env["request"].files={"attachment":image}
        env["save_chat_image"]=Mock(return_value=("/mock-image","image/png"))
        env["search_visual_image_match"]=Mock(return_value={"answer":"mock visual answer","confidence":.9,"source":"image_retrieval"})
        result=self.call()
        self.assertEqual(result["served_by"],"image_embedding_retrieval")
        self.provider._call_ai_provider_once.assert_not_called()
        self.provider.generate_ai_reply.assert_not_called()
    def test_route_image_text_fallback_still_skips_memory(self):
        image=types.SimpleNamespace(filename="mock.png")
        env["request"].content_type="multipart/form-data"
        env["request"].is_json=False
        env["request"].form={"question":"Golden Passion honey price","context":"{}","request_id":"mock"}
        env["request"].files={"attachment":image}
        env["save_chat_image"]=Mock(return_value=(None,None))
        self.call()
        self.provider._call_ai_provider_once.assert_not_called()
    def test_route_greeting_skips_memory_and_answer(self):
        self.payload["question"]="hello"
        result=self.call()
        self.assertEqual(result["source"],"greeting")
        self.provider._call_ai_provider_once.assert_not_called()
        self.provider.generate_ai_reply.assert_not_called()
    def test_route_step_control_skips_memory(self):
        self.payload["question"]="Step 4"
        env["process_question"]=Mock(return_value=({"source":"context_step","confidence":.95,"answer":"A mock step","context":{}},200))
        self.call()
        self.provider._call_ai_provider_once.assert_not_called()
    def test_route_next_control_skips_memory(self):
        self.payload["question"]="next"
        self.call()
        self.provider._call_ai_provider_once.assert_not_called()

    def image_request(self, question, vision=None):
        env["request"].content_type="multipart/form-data"
        env["request"].is_json=False
        env["request"].form={"question":question,"context":"{}","request_id":"mock"}
        env["request"].files={"attachment":types.SimpleNamespace(filename="mock.png")}
        env["save_chat_image"]=Mock(return_value=("/mock-image","image/png"))
        env["search_visual_image_match"]=Mock(return_value=None)
        env["get_local_image_path_from_url"]=Mock(return_value="nonexistent-isolated-test-image")
        env["analyze_uploaded_image_with_vision"]=Mock(return_value=vision)
        env["extract_image_search_text"]=Mock(return_value=question)
    def test_route_successful_image_upload_text_fallback(self):
        self.image_request("Golden Passion honey price")
        self.call()
        self.provider._call_ai_provider_once.assert_not_called()
        self.assertEqual(env["process_question"].call_args.kwargs["question"],"Golden Passion honey price")
    def test_route_image_only_clarification(self):
        self.image_request("")
        env["build_image_only_clarification_response"]=Mock(return_value={"source":"image_only_clarification","answer":"Mock clarification"})
        result=self.call()
        self.assertEqual(result["source"],"image_only_clarification")
        self.provider._call_ai_provider_once.assert_not_called()
        self.provider.generate_ai_reply.assert_not_called()
        env["create_escalation"].assert_not_called()
    def test_route_unrelated_image_rejection(self):
        self.image_request("photo",{"isWorkRelated":False,"confidence":.9})
        env["build_image_irrelevant_response"]=Mock(return_value={"source":"irrelevant_image","answer":"Mock rejection"})
        result=self.call()
        self.assertEqual(result["source"],"irrelevant_image")
        self.provider._call_ai_provider_once.assert_not_called()
        self.provider.generate_ai_reply.assert_not_called()
        env["create_escalation"].assert_not_called()
    def test_route_related_image_plus_text(self):
        self.image_request("price",{"isWorkRelated":True,"confidence":.9})
        env["build_vision_augmented_question"]=Mock(return_value="Golden Passion honey price")
        self.call()
        self.provider._call_ai_provider_once.assert_not_called()
        self.assertEqual(env["process_question"].call_args.kwargs["question"],"Golden Passion honey price")
    def test_route_not_this_keeps_existing_escalation(self):
        self.payload["question"]="not this"
        env["AI_LAST_ANSWER_MEMORY"]["user:7:last_answer"]={"question":"Golden Passion honey price","result":{"answer":"Mock prior answer"}}
        result=self.call()
        self.assertEqual(result["source"],"staff_not_satisfied_escalated")
        self.assertEqual(env["create_escalation"].call_args.args[0],"Golden Passion honey price")
        self.provider._call_ai_provider_once.assert_not_called()
        self.provider.generate_ai_reply.assert_not_called()
    def test_route_typo_keeps_log_wording(self):
        self.payload["question"]="its benfits?"
        env["normalize_staff_query"]=Mock(return_value=("its benefits?",True))
        self.call()
        self.assertEqual(env["process_question"].call_args.kwargs["search_question"],"Golden Passion honey benefits")
        self.assertEqual(env["log_request"].call_args.args[0],"its benfits?")
    def test_route_standalone_topic_change_no_memory(self):
        self.payload["question"]="ST3 kiosk opening"
        self.call()
        self.provider._call_ai_provider_once.assert_not_called()
        self.assertEqual(env["process_question"].call_args.kwargs["search_question"],"ST3 kiosk opening")
    def test_route_correction_preserves_raw_and_uses_new_location(self):
        self.payload["question"]="Correction, I mean ST3."
        self.payload["history"]=[{"role":"user","content":"kiosk closing at Spring"}]
        self.provider._call_ai_provider_once.return_value=json.dumps({"query":"ST3 kiosk closing","subject":"ST3","evidence_index":-1,"topic_index":0})
        self.call()
        self.assertEqual(env["process_question"].call_args.kwargs["search_question"],"ST3 kiosk closing")
        self.assertEqual(env["log_request"].call_args.args[0],"Correction, I mean ST3.")

    def test_route_force_escalation_saves_valid_client_snapshot_with_authenticated_owner(self):
        self.payload.update(force_escalate=True, chat_session_id="main-a", escalation_context={
            "conversation_id":"main-a", "issue_id":"1", "description":"Golden Passion honey benefits",
            "messages":[{"role":"user","content":"Golden Passion honey price","timestamp":None,"attachments":[]}]})
        self.call()
        args=env["save_escalation_context"].call_args.args
        self.assertEqual(args[:2],(123,7))
        self.assertEqual(args[2]["trigger_question"],"And its benefits?")
        self.assertEqual(args[2]["provenance"],"client_supplied_unverified")
        self.assertEqual(env["create_escalation"].call_args.args[0],"And its benefits?")

    def test_route_new_main_session_does_not_read_legacy_previous_answer(self):
        self.payload.update(question="not this", chat_session_id="main-new")
        env["AI_LAST_ANSWER_MEMORY"]["user:7:last_answer"]={"question":"old floating question","result":{}}
        self.call()
        for call in env["create_escalation"].call_args_list:
            self.assertNotEqual(call.args[0],"old floating question")

    def rejection_context(self):
        self.payload.update(question="I think this is not what I want", chat_session_id="main-a", escalation_context={
            "conversation_id":"main-a", "issue_id":"1", "description":"Ice delivery payment",
            "messages":[{"role":"user","content":"Ice delivery payment how much?","timestamp":None,"attachments":[]},
                        {"role":"assistant","content":"A prior answer","timestamp":None,"attachments":[]},
                        {"role":"user","content":"I think this is not what I want","timestamp":None,"attachments":[]}]})
        env["AI_LAST_ANSWER_MEMORY"]["user:7:chat:main-a:last_answer"]={"question":"Ice delivery payment how much?","result":{"answer":"A prior answer"}}

    def test_route_first_main_rejection_asks_once_without_escalation_or_provider(self):
        self.rejection_context()
        result=self.call()
        self.assertTrue(result["clarification_requested"])
        self.assertFalse(result["escalation_required"])
        env["create_escalation"].assert_not_called()
        self.provider._call_ai_provider_once.assert_not_called()
        self.provider.generate_ai_reply.assert_not_called()
        self.assertEqual(env["log_request"].call_args.kwargs["result"]["question"],self.payload["question"])

    def test_route_cancelled_rejection_does_not_ask_or_escalate(self):
        self.rejection_context()
        env["is_chat_request_cancelled"].return_value=True
        result=self.call()
        self.assertTrue(result["cancelled"])
        self.assertFalse(result.get("clarification_requested",False))
        env["create_escalation"].assert_not_called()

    def test_route_second_rejection_escalates_with_signed_state_on_another_worker(self):
        self.rejection_context()
        first=self.call()
        self.payload.update(question="not this", clarification_token=first["clarification_token"])
        env["AI_LAST_ANSWER_MEMORY"].clear()
        result=self.call()
        self.assertTrue(result["escalation_required"])
        self.assertEqual(env["create_escalation"].call_args.args[0],"Ice delivery payment how much?")

    def test_route_clarified_reply_can_receive_an_answer(self):
        self.rejection_context()
        first=self.call()
        self.payload.update(question="I need the payment amount for ice delivery", clarification_token=first["clarification_token"], history=None)
        result=self.call()
        self.assertEqual(result["source"],"ai_provider_answer")
        env["create_escalation"].assert_not_called()

    def test_route_direct_escalation_button_does_not_ask_again(self):
        self.rejection_context()
        first=self.call()
        self.payload.update(force_escalate=True, question=first["question"])
        result=self.call()
        self.assertEqual(result["source"],"staff_requested_escalation")
        env["create_escalation"].assert_called_once()

    def test_route_rejection_does_not_use_stale_unrelated_server_answer(self):
        self.rejection_context()
        self.payload["escalation_context"]["messages"][0]["content"]="Daily Jungle Heart information"
        result=self.call()
        self.assertEqual(result["question"],"Daily Jungle Heart information")
        env["create_escalation"].assert_not_called()

    def test_route_uncertainty_inside_a_question_is_not_a_rejection(self):
        self.payload.update(question="I do not know how much ice costs",chat_session_id="main-a")
        result=self.call()
        self.assertNotEqual(result.get("source"),"answer_clarification_requested")

    def test_business_condition_is_not_mistaken_for_answer_rejection(self):
        for question in ["The ice temperature is not correct", "冰箱温度不对", "suhu peti ais tak betul"]:
            self.assertFalse(env["is_explicit_answer_rejection"](question))



class SessionAndEscalationContextTests(unittest.TestCase):
    def setUp(self):
        MemoryTests.setUp(self)
        env["AI_CHAT_MEMORY"].clear()
        env["g"]=types.SimpleNamespace()
        self.data={"user_id":7,"chat_session_id":"main-a","original_staff_question":"The iPad cabinet is locked"}
        self.context={"version":1,"conversation_id":"main-a","issue_id":"1","description":"iPad closing; cabinet locked",
            "messages":[{"role":"user","content":"Where to store iPad?","timestamp":None,"attachments":[]},
                        {"role":"assistant","content":"Cabinet","timestamp":"2026-10-26T01:00:00Z","attachments":[]},
                        {"role":"user","content":"The iPad cabinet is locked","timestamp":None,"attachments":[]}],
            "omitted_messages":0}
        self.data["escalation_context"]=self.context
        env["create_escalation"]=Mock(return_value=123)
        env["save_escalation_context"]=Mock(return_value=True)
    def validate(self,value=None):
        return env["validate_escalation_context"](self.context if value is None else value,self.data,"server trigger","server reason")
    def test_new_chat_old_step_last_answer_and_fail_count_are_separate(self):
        a={"user_id":7,"chat_session_id":"main-a"}
        b={"user_id":7,"chat_session_id":"main-b"}
        env["remember_chat_context"](a,{"context":{"title":"iPad closing","last_step_number":4}})
        self.assertEqual(env["prepare_chat_context"](a)["title"],"iPad closing")
        self.assertEqual(env["prepare_chat_context"](b)["title"],"")
        self.assertNotEqual(env["get_last_answer_key"](a),env["get_last_answer_key"](b))
        self.assertNotEqual(env["get_ai_fail_key"](a),env["get_ai_fail_key"](b))
    def test_users_cannot_share_session_memory(self):
        self.assertNotEqual(env["get_chat_memory_key"]({"user_id":7,"chat_session_id":"main-a"}),
                            env["get_chat_memory_key"]({"user_id":8,"chat_session_id":"main-a"}))
    def test_legacy_floating_keys_are_unchanged(self):
        self.assertEqual(env["get_chat_memory_key"]({"user_id":7}),"user:7")
        self.assertEqual(env["get_last_answer_key"]({"user_id":7}),"user:7:last_answer")
        self.assertEqual(env["get_ai_fail_key"]({"user_id":7}),"user:7:ai_fail_count")
    def test_invalid_session_id_not_used_as_namespace(self):
        for value in ["../bad","x"*97,"abc:admin"]:
            self.assertEqual(env["get_chat_session_id"]({"chat_session_id":value}),"")
    def test_context_is_unverified_with_server_trigger_reason_and_unknown_time(self):
        result=self.validate()
        self.assertEqual(result["provenance"],"client_supplied_unverified")
        self.assertEqual(result["trigger_question"],"server trigger")
        self.assertEqual(result["reason"],"server reason")
        self.assertIsNone(result["messages"][0]["timestamp"])
        self.assertTrue(result["received_at"].endswith("Z"))
    def test_context_rejects_other_session_and_invalid_roles(self):
        bad=copy.deepcopy(self.context);bad["conversation_id"]="main-b"
        self.assertIsNone(self.validate(bad))
        bad=copy.deepcopy(self.context);bad["messages"][0]["role"]="system"
        self.assertIsNone(self.validate(bad))
    def test_context_size_limits(self):
        for mutate in [lambda b:b.update(messages=b["messages"]*14),
                       lambda b:b["messages"][0].update(content="x"*2001),
                       lambda b:b.update(description="x"*1001),
                       lambda b:b.update(messages=[{"role":"user","content":"x"*2000}]*21)]:
            bad=copy.deepcopy(self.context);mutate(bad)
            self.assertIsNone(self.validate(bad))
    def test_context_rejects_markup_image_data_and_external_attachments(self):
        for path in ["https://example.invalid/a.png","data:image/png,x","/static/uploads/chat/../secret","/static/secret.png"]:
            bad=copy.deepcopy(self.context);bad["messages"][0]["attachments"]=[path]
            self.assertIsNone(self.validate(bad))
        bad=copy.deepcopy(self.context);bad["messages"][0]["content"]="<script>bad</script>"
        self.assertIsNone(self.validate(bad))
    def test_context_rejects_invalid_time_instead_of_inventing_one(self):
        for value in ["yesterday","2026-10-26T01:00:00",1]:
            bad=copy.deepcopy(self.context);bad["messages"][0]["timestamp"]=value
            self.assertIsNone(self.validate(bad))
    def test_current_saved_attachment_added_to_user_message(self):
        result=env["validate_escalation_context"](self.context,self.data,"q","reason","/static/uploads/chat/123_ipad.png")
        self.assertEqual(result["messages"][-1]["attachments"],["/static/uploads/chat/123_ipad.png"])
        self.assertEqual(self.context["messages"][-1]["attachments"],[])
    def test_context_saves_separately_without_changing_question_answer(self):
        result={"answer":"original AI answer","source":"fallback"}
        self.assertEqual(env["create_chat_escalation"]("ticket question",result,self.data),123)
        args=env["create_escalation"].call_args
        self.assertEqual(args.args[:3],("ticket question",result,7))
        context=args.kwargs["conversation_context"]
        self.assertEqual(context["trigger_question"],"The iPad cabinet is locked")
        self.assertEqual(env["save_escalation_context"].call_args.args,(123,7,context))
        self.assertTrue(env["g"].chat_escalation_context_saved)
    def test_context_store_failure_keeps_ticket_and_warns(self):
        env["save_escalation_context"].side_effect=RuntimeError("mock missing table")
        self.assertEqual(env["create_chat_escalation"]("q",{"source":"fallback"},self.data),123)
        env["create_escalation"].assert_called_once()
        self.assertFalse(env["g"].chat_escalation_context_saved)
    def test_invalid_client_context_keeps_original_ticket(self):
        self.data["escalation_context"]={"messages":"bad"}
        self.assertEqual(env["create_chat_escalation"]("q",{},self.data),123)
        self.assertEqual(env["create_escalation"].call_args.kwargs,{})
        env["save_escalation_context"].assert_not_called()
        self.assertFalse(env["g"].chat_escalation_context_saved)
    def test_no_context_keeps_legacy_signature(self):
        self.data.pop("escalation_context")
        env["create_chat_escalation"]("q",{},self.data)
        self.assertEqual(env["create_escalation"].call_args.kwargs,{})
        self.assertFalse(hasattr(env["g"],"chat_escalation_context_saved"))

    def test_context_failure_response_warns_without_hiding_ticket(self):
        env["g"].chat_escalation_context_saved=False
        payload={"escalation_id":123,"answer":"original answer"}
        response=types.SimpleNamespace(is_json=True, get_json=lambda **kwargs:payload, set_data=Mock())
        env["attach_escalation_context_status"](response)
        saved=json.loads(response.set_data.call_args.args[0])
        self.assertEqual(saved["escalation_id"],123)
        self.assertEqual(saved["answer"],"original answer")
        self.assertFalse(saved["escalation_context_saved"])
        self.assertIn("discussion context",saved["escalation_context_warning"])

    def test_clarification_token_is_bound_to_user_chat_and_issue(self):
        token=env["make_clarification_token"](self.data,"1","Original question")
        self.assertIsNotNone(env["read_clarification_token"](token,self.data,"1"))
        for field,value in [("user_id",8),("chat_session_id","main-b")]:
            other={**self.data,field:value}
            self.assertIsNone(env["read_clarification_token"](token,other,"1"))
        self.assertIsNone(env["read_clarification_token"](token,self.data,"another-issue"))

    def test_clarification_token_tampering_and_expiry_are_rejected(self):
        with patch.object(time,"time",return_value=1000):
            token=env["make_clarification_token"](self.data,"1","Original question")
        self.assertIsNone(env["read_clarification_token"](token+"bad",self.data,"1"))
        with patch.object(time,"time",return_value=2801):
            self.assertIsNone(env["read_clarification_token"](token,self.data,"1"))

db_source=Path(__file__).with_name("db_helper.py").read_text(encoding="utf-8")
compile(db_source,"db_helper.py","exec")
db_tree=ast.parse(db_source)
db_names={"normalize_text","has_recent_similar_escalation","_close_context_resources","save_escalation_context","load_escalation_contexts"}
db_env={"json":json}
exec(compile(ast.Module(body=[n for n in db_tree.body if isinstance(n,ast.FunctionDef) and n.name in db_names],type_ignores=[]),"db_context_functions.py","exec"),db_env)

class EscalationContextStorageTests(unittest.TestCase):
    def setUp(self):
        self.cursor=Mock()
        self.conn=Mock()
        self.conn.cursor.return_value=self.cursor
        db_env["get_db_connection"]=Mock(return_value=self.conn)
        self.context={"conversation_id":"main-a","issue_id":"1","messages":[]}
    def test_save_checks_ticket_owner(self):
        self.cursor.fetchone.return_value={"asked_by":8}
        self.assertFalse(db_env["save_escalation_context"](123,7,self.context))
        self.assertEqual(self.cursor.execute.call_count,1)
        self.conn.commit.assert_not_called()
    def test_save_separate_metadata_table(self):
        self.cursor.fetchone.side_effect=[{"asked_by":7},None]
        self.assertTrue(db_env["save_escalation_context"](123,7,self.context))
        sql,params=self.cursor.execute.call_args.args
        self.assertIn("INSERT INTO escalation_context",sql)
        self.assertEqual(json.loads(params[3]),self.context)
        self.conn.commit.assert_called_once()
    def test_retry_retains_original_snapshot(self):
        self.cursor.fetchone.side_effect=[{"asked_by":7},{"conversation_id":"main-a","issue_id":"1"}]
        self.assertTrue(db_env["save_escalation_context"](123,7,self.context))
        self.assertEqual(self.cursor.execute.call_count,2)
    def test_retry_does_not_replace_another_issue(self):
        self.cursor.fetchone.side_effect=[{"asked_by":7},{"conversation_id":"main-b","issue_id":"2"}]
        self.assertFalse(db_env["save_escalation_context"](123,7,self.context))
    def test_missing_table_is_optional(self):
        self.cursor.execute.side_effect=RuntimeError("mock missing table")
        self.assertFalse(db_env["save_escalation_context"](123,7,self.context))
        self.assertEqual(db_env["load_escalation_contexts"]([123]),{})

    def test_missing_table_diagnostic_has_no_connection_details(self):
        error=RuntimeError("details must not be exposed")
        error.errno=1146
        self.cursor.execute.side_effect=error
        diagnostic={}
        self.assertFalse(db_env["save_escalation_context"](123,7,self.context,diagnostic))
        self.assertEqual(diagnostic,{"code":"schema_missing"})
    def test_list_loads_json_contexts(self):
        self.cursor.fetchall.return_value=[{"escalation_id":123,"context_json":json.dumps(self.context)}]
        self.assertEqual(db_env["load_escalation_contexts"]([123]),{123:self.context})
    def test_dedup_is_scoped_to_owner_session_and_issue(self):
        self.cursor.fetchall.return_value=[]
        db_env["has_recent_similar_escalation"]("raw question",asked_by=7,conversation_context=self.context)
        sql,params=self.cursor.execute.call_args.args
        self.assertIn("e.asked_by = %s",sql)
        self.assertIn("ec.issue_id = %s",sql)
        self.assertEqual(params,(15,7,"main-a","1"))
    def test_cleanup_failures_do_not_break_optional_reads(self):
        self.cursor.fetchall.return_value=[]
        self.conn.close.side_effect=RuntimeError("mock")
        self.assertEqual(db_env["load_escalation_contexts"]([123]),{})


title_functions=[]
for name in ["validate_standard_question", "submit_escalation_answer", "approve_escalation_answer", "approve_review", "publish_review"]:
    node=copy.deepcopy(next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name))
    node.decorator_list=[]
    title_functions.append(node)
exec(compile(ast.Module(body=title_functions,type_ignores=[]),"actual_title_workflow.py","exec"),env)


class StandardQuestionWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.title="How much should staff pay when receiving two packs of ice?"
        self.raw="i mean ice receiving for two packs how much?"
        self.answer="A separately reviewed answer."
        self.payload={"standard_question":self.title,"standard_question_confirmed":True,"manual_answer":self.answer}
        env["request"]=types.SimpleNamespace(content_type="application/json",get_json=lambda **kwargs:self.payload,files={},form={})
        self.cursor=Mock()
        self.cursor.rowcount=1
        self.conn=Mock()
        self.conn.cursor.return_value=self.cursor
        env["get_db_connection"]=Mock(return_value=self.conn)
        env["current_auth_user_id"]=Mock(return_value=7)
        env["add_audit_log"]=Mock()
        env["save_qa_to_db"]=Mock()
        env["_save_approved_escalation_to_qa_knowledge"]=Mock()
        env["_save_approved_escalation_to_image_retrieval"]=Mock()
    def test_standard_question_requires_explicit_confirmation(self):
        for confirmation in [False,None,1,"false"]:
            question,error=env["validate_standard_question"]({"standard_question":self.title,"standard_question_confirmed":confirmation})
            self.assertIsNone(question)
            self.assertIsNotNone(error)
    def test_fragment_or_vague_title_is_rejected_even_if_confirmed(self):
        for title in ["i mean ice receiving for two packs how much?","how much?","not this","我是说两个冰块","maksud saya dua pek ais","?????","x"*256,"<b>Ice payment</b>"]:
            question,error=env["validate_standard_question"]({"standard_question":title,"standard_question_confirmed":True})
            self.assertIsNone(question,title)
            self.assertIsNotNone(error)
    def test_complete_titles_in_three_languages_are_accepted(self):
        for title in [self.title,"收到两包冰时，员工应支付多少费用？","Berapakah bayaran apabila menerima dua pek ais?"]:
            question,error=env["validate_standard_question"]({"standard_question":title,"standard_question_confirmed":True})
            self.assertEqual(question,title)
            self.assertIsNone(error)
    def test_missing_title_blocks_all_write_paths_before_database_access(self):
        self.payload={"manual_answer":self.answer}
        for name in ["submit_escalation_answer","approve_escalation_answer","approve_review","publish_review"]:
            response,status=env[name](1)
            self.assertEqual(status,400,name)
        env["get_db_connection"].assert_not_called()
    def test_team_lead_saves_reviewed_question_but_keeps_raw_escalation(self):
        escalation={"escalation_id":1,"question":self.raw,"image_url":None,"image_type":None}
        self.cursor.fetchone.side_effect=[escalation,None]
        response,status=env["submit_escalation_answer"](1)
        self.assertEqual(status,200,response)
        writes=[call.args for call in self.cursor.execute.call_args_list]
        review_insert=next((sql,params) for sql,params in writes if "INSERT INTO review_queue" in sql)
        self.assertEqual(review_insert[1],(1,self.title,self.answer,7))
        ticket_update=next(sql for sql,params in writes if "UPDATE escalation" in sql)
        self.assertNotIn("question =",ticket_update)
        self.assertEqual(escalation["question"],self.raw)
        env["save_qa_to_db"].assert_not_called()
    def test_multipart_answer_accepts_string_confirmation(self):
        env["request"].content_type="multipart/form-data"
        env["request"].form={**self.payload,"standard_question_confirmed":"true"}
        self.cursor.fetchone.side_effect=[{"question":self.raw},None]
        response,status=env["submit_escalation_answer"](1)
        self.assertEqual(status,200,response)
    def test_approval_uses_standard_question_for_trusted_knowledge(self):
        escalation={"question":self.raw,"manual_answer":self.answer,"asked_by":1,"handled_by":2,"image_url":None,"image_type":None}
        self.cursor.fetchone.side_effect=[escalation,{"review_id":5,"question":self.raw}]
        response,status=env["approve_escalation_answer"](1)
        self.assertEqual(status,200,response)
        self.assertEqual(env["_save_approved_escalation_to_qa_knowledge"].call_args.args[1:3],(self.title,self.answer))
        self.assertEqual(escalation["question"],self.raw)
    def test_review_approval_persists_confirmed_question(self):
        response,status=env["approve_review"](5)
        self.assertEqual(status,200,response)
        sql,params=self.cursor.execute.call_args.args
        self.assertIn("question = %s",sql)
        self.assertEqual(params,(self.title,7,"",5))
    def test_article_contains_only_standard_title_and_approved_answer(self):
        review={"review_id":5,"question":self.raw,"answer":self.answer,"status":"approved"}
        self.cursor.fetchone.return_value=review
        response,status=env["publish_review"](5)
        self.assertEqual(status,200,response)
        writes=[call.args for call in self.cursor.execute.call_args_list]
        article=next((sql,params) for sql,params in writes if "INSERT INTO wiki_article" in sql)
        self.assertEqual(article[1][:2],(self.title,self.answer))
        self.assertFalse(any("escalation_context" in sql for sql,params in writes))
        self.assertEqual(env["save_qa_to_db"].call_args.args[0],self.title)
        self.assertEqual(env["save_qa_to_db"].call_args.args[1]["answer"],self.answer)
    def test_unapproved_review_cannot_be_published_with_a_clear_title(self):
        self.cursor.fetchone.return_value={"review_id":5,"question":self.title,"answer":self.answer,"status":"pending"}
        response,status=env["publish_review"](5)
        self.assertEqual(status,400)
        self.assertFalse(any("INSERT INTO wiki_article" in call.args[0] for call in self.cursor.execute.call_args_list))


if __name__ == "__main__":
    unittest.main()
