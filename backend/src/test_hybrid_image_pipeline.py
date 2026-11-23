"""Real Flask/auth/CSRF + temporary SQLite + real Pillow; CLIP/provider remain mocked.
Not MySQL, real semantic CLIP, Gemini or production E2E tests.
"""
import io
import json
import sqlite3
import os
import sys
import types
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest
from PIL import Image

os.environ.setdefault("DOCUMENT_TEXT_BACKFILL", "false")
import app
import chat_attachment_service as attachments
import hybrid_image_service as hybrid
import image_index_service as index
import image_embedding_helper as embeddings


class Cursor:
    def __init__(self, db):
        self.cursor = db.cursor()

    def execute(self, sql, params=()):
        params = tuple(value.isoformat(sep=" ") if isinstance(value, datetime) else value for value in params)
        self.cursor.execute(sql.replace("%s", "?").replace(" FOR UPDATE", ""), params)
        return self

    def fetchone(self):
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def fetchall(self):
        return [dict(row) for row in self.cursor.fetchall()]

    def close(self):
        self.cursor.close()

    @property
    def rowcount(self):
        return self.cursor.rowcount

    @property
    def lastrowid(self):
        return self.cursor.lastrowid


class Connection:
    def __init__(self, db):
        self.db = db

    def cursor(self, **kwargs):
        return Cursor(self.db)

    def commit(self):
        self.db.commit()

    def rollback(self):
        self.db.rollback()

    def close(self):
        pass  # Fixture owns the shared in-memory database lifetime.


@pytest.fixture
def local(monkeypatch, tmp_path):
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.create_function("UTC_TIMESTAMP", 0, lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
    db.executescript("""
        CREATE TABLE roles (role_id INTEGER PRIMARY KEY, role_name TEXT);
        INSERT INTO roles VALUES (1, 'Staff');
        CREATE TABLE users (user_id INTEGER PRIMARY KEY, full_name TEXT, email TEXT,
            password_hash TEXT, status TEXT, created_at TEXT, role_id INTEGER);
        INSERT INTO users VALUES (1, 'Synthetic One', '', 'synthetic', 'active', '', 1);
        INSERT INTO users VALUES (2, 'Synthetic Two', '', 'synthetic', 'active', '', 1);
        CREATE TABLE wiki_article (article_id INTEGER PRIMARY KEY, title TEXT, content TEXT,
            category TEXT, sub_category TEXT, image_files TEXT, attachment_url TEXT, is_deleted INTEGER DEFAULT 0);
        CREATE TABLE image_retrieval (image_id INTEGER PRIMARY KEY AUTOINCREMENT, source_type TEXT,
            source_id INTEGER, question TEXT, answer TEXT, image_url TEXT, image_type TEXT,
            image_caption TEXT, approval_status TEXT DEFAULT 'approved', visual_match_enabled INTEGER DEFAULT 1,
            image_embedding TEXT, embedding_model TEXT, source_hash TEXT, image_hash TEXT,
            indexed_at TEXT, index_error TEXT);
        CREATE TABLE chat_attachments (attachment_id TEXT PRIMARY KEY, owner_id INTEGER, chat_key TEXT,
            storage_name TEXT, mime_type TEXT, image_hash TEXT, observations TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP, expires_at TEXT);
        CREATE TABLE escalation (escalation_id INTEGER, image_url TEXT, is_deleted INTEGER, asked_by INTEGER);
        CREATE TABLE review_queue (review_id INTEGER, escalation_id INTEGER, status TEXT, question TEXT, answer TEXT);
    """)
    connect = lambda: Connection(db)
    for module in (app, attachments, index, hybrid):
        monkeypatch.setattr(module, "get_db_connection", connect)
    folder = tmp_path / "static" / "uploads" / "chat"
    folder.mkdir(parents=True)
    (tmp_path / "static" / "uploads" / "articles").mkdir()
    monkeypatch.setattr(app, "CHAT_UPLOAD_FOLDER", folder)
    monkeypatch.setattr(app, "STATIC_DIR", tmp_path / "static")
    monkeypatch.setattr(index, "STATIC_DIR", tmp_path / "static")
    monkeypatch.setattr(app, "is_chat_request_cancelled", lambda value: False)
    monkeypatch.setattr(app, "analyze_uploaded_image_with_vision", Mock(return_value=None))
    monkeypatch.setattr(app, "log_request", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.ai_provider_service, "vision_identity", lambda: "synthetic-model")
    app.app.config.update(TESTING=True)
    yield db, folder
    db.close()


def client_for(owner):
    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = owner
        session["password_fingerprint"] = app.password_session_fingerprint("synthetic")
        session["csrf_token"] = "synthetic-csrf"
    return client


def png_bytes(color="blue"):
    output = io.BytesIO()
    Image.new("RGB", (24, 30), color).save(output, format="PNG")
    return output.getvalue()


def different_photo(folder):
    path = folder / "different-query.png"
    path.write_bytes(png_bytes("red"))
    return path


def upload(client, question="", chat="main-test", content=None, filename="synthetic.png"):
    return client.post("/api/chat", data={"question": question, "chat_session_id": chat,
        "attachment": (io.BytesIO(content or png_bytes()), filename)},
        headers={"X-CSRF-Token": "synthetic-csrf"})


def add_article(db, folder, article_id=1, title="Staff belongings Area", content="Put bottles in the designated belongings area."):
    path = folder.parent / "articles" / f"synthetic-{article_id}.png"
    path.write_bytes(png_bytes())
    url = f"/static/uploads/articles/{path.name}"
    db.execute("INSERT INTO wiki_article VALUES (?, ?, ?, '', '', ?, NULL, 0)",
               (article_id, title, content, json.dumps([{"url": url}])))
    cursor = Cursor(db)
    index.sync_article(cursor, article_id)
    cursor.close()
    db.execute("UPDATE image_retrieval SET image_embedding = ?, embedding_model = ?, image_hash = ? WHERE source_id = ?",
               ("[1,0,0]", embeddings.MODEL_VERSION, embeddings.image_sha256(path), article_id))
    db.commit()
    return path


def test_image_only_searches_current_articles_without_vision_when_exact(local):
    db, folder = local
    add_article(db, folder)
    response = upload(client_for(1))
    assert response.status_code == 200
    data = response.get_json()
    assert data["source"] == "image_article_match"
    assert data["article_id"] == 1
    assert data["fallback"] is False
    assert len(data["attachment_refs"]) == 1
    assert "/static/uploads/chat/" not in response.get_data(as_text=True)
    app.analyze_uploaded_image_with_vision.assert_not_called()


def test_missing_migration_returns_safe_schema_error_with_stage(local, monkeypatch, caplog):
    import mysql.connector
    def missing(*args, **kwargs):
        raise mysql.connector.ProgrammingError("synthetic-sensitive-db-message", errno=1146)
    monkeypatch.setattr(attachments, "register_attachment", missing)
    response = upload(client_for(1))
    data = response.get_json()
    assert response.status_code == 503
    assert data["code"] == "IMAGE_SCHEMA_NOT_READY"
    assert data["confidence_kind"] == "not_calibrated"
    assert data["source"] == "image_service_unavailable"
    assert data["error_id"] in caplog.text
    assert "attachment_register" in caplog.text
    assert "synthetic-sensitive-db-message" not in caplog.text
    assert "synthetic-sensitive-db-message" not in response.get_data(as_text=True)


@pytest.mark.parametrize("preferred,expected", [("zh", "以下知识库文章"), ("ms", "Artikel Pangkalan")])
def test_image_only_article_match_respects_ui_language(local, preferred, expected):
    db, folder = local
    add_article(db, folder)
    response = client_for(1).post("/api/chat", data={"question": "", "language": preferred,
        "chat_session_id": "main-test", "attachment": (io.BytesIO(png_bytes()), "fixture.png")},
        headers={"X-CSRF-Token": "synthetic-csrf"})
    assert response.status_code == 200
    assert expected in response.get_json()["reply"]


KIOSK_PHOTOS = sorted((Path(__file__).parent.parent / "static/sop_images/kiosk_opening").glob("*.jpg"))


@pytest.mark.parametrize("photo", KIOSK_PHOTOS, ids=lambda path: path.name)
@pytest.mark.parametrize("copy_format", ["original", "clipboard_png", "resized_jpeg"])
def test_every_bundled_kiosk_photo_copy_returns_full_article(local, monkeypatch, photo, copy_format):
    db, folder = local
    full_content = "<h2>Kiosk Opening</h2><p>Opening step one.</p><p>Use the hook to operate the blind.</p><p>Final opening step.</p>"
    article_image = add_article(db, folder, title="Kiosk Opening", content=full_content)
    article_image.write_bytes(photo.read_bytes())
    db.execute("DELETE FROM image_retrieval")  # Existing articles need no vector/backfill.
    if copy_format == "original":
        with Image.open(photo) as image:
            suffix = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[image.format]
        content, filename = photo.read_bytes(), "copied" + suffix
    else:
        output = io.BytesIO()
        with Image.open(photo) as image:
            image = image.convert("RGB")
            if copy_format == "resized_jpeg":
                image.thumbnail((480, 640))
                image.save(output, format="JPEG", quality=85)
            else:
                image.save(output, format="PNG")
        content = output.getvalue()
        filename = "copied.png" if copy_format == "clipboard_png" else "copied.jpg"
    response = upload(client_for(1), content=content, filename=filename)
    data = response.get_json()
    assert response.status_code == 200, data
    assert data["article_id"] == 1, data
    assert data["title"] == "Kiosk Opening"
    assert data["answer"] == full_content
    assert data["article_link"] == "/knowledge/1"
    app.analyze_uploaded_image_with_vision.assert_not_called()


@pytest.mark.parametrize("storage", ["html", "json", "legacy_pipe"])
def test_article_photo_membership_formats_are_all_searchable(local, storage):
    db, folder = local
    path = add_article(db, folder, title="Kiosk Opening")
    url = f"/static/uploads/articles/{path.name}"
    if storage == "html":
        db.execute("UPDATE wiki_article SET image_files=NULL, content=?", (f'<p>Full opening instructions.</p><img src="{url}">',))
    elif storage == "json":
        db.execute("UPDATE wiki_article SET image_files=?", (json.dumps(url),))
    else:
        db.execute("UPDATE wiki_article SET image_files=?", (f"uploads/articles/{path.name}|/static/uploads/articles/missing.png",))
    db.execute("DELETE FROM image_retrieval")
    data = upload(client_for(1)).get_json()
    assert data["article_id"] == 1
    assert data["title"] == "Kiosk Opening"


def test_image_only_vision_aliases_find_bottle_article(local, monkeypatch):
    db, folder = local
    add_article(db, folder)
    monkeypatch.setattr(index, "visual_candidates", lambda path: [])
    app.analyze_uploaded_image_with_vision.return_value = {"detectedObjects": ["sports hydration flask"],
        "possibleAliases": ["bottle", "plastic water container"]}
    data = upload(client_for(1), content=png_bytes("red")).get_json()
    assert data["source"] == "image_related_articles"
    assert data["article_id"] == 1
    assert data["fallback"] is False
    app.analyze_uploaded_image_with_vision.assert_called_once()


def test_image_only_duplicate_matches_offer_article_choices(local):
    db, folder = local
    add_article(db, folder)
    add_article(db, folder, article_id=2, title="Another bottle guide")
    data = upload(client_for(1)).get_json()
    assert data["type"] == "options"
    assert {option["article_id"] for option in data["options"]} == {1, 2}
    assert all(option["link"].startswith("/knowledge/") for option in data["options"])
    app.analyze_uploaded_image_with_vision.assert_not_called()


def test_image_only_similar_photo_returns_article_without_vision(local, monkeypatch):
    db, folder = local
    add_article(db, folder)
    row = dict(db.execute("SELECT * FROM image_retrieval").fetchone())
    monkeypatch.setattr(index, "visual_candidates", lambda path: [
        {**row, "image_similarity": 0.90, "exact_image": False}])
    data = upload(client_for(1), content=png_bytes("red")).get_json()
    assert data["source"] == "image_related_articles"
    assert data["article_id"] == 1
    app.analyze_uploaded_image_with_vision.assert_not_called()


def test_image_only_unknown_does_not_return_an_arbitrary_article(local, monkeypatch):
    db, folder = local
    add_article(db, folder)
    monkeypatch.setattr(index, "visual_candidates", lambda path: [])
    data = upload(client_for(1), content=png_bytes("red")).get_json()
    assert data["source"] == "image_unknown"
    assert not data.get("article_id") and not data.get("options")


@pytest.mark.parametrize("staff_content", [
    "Keep staff water bottles on the belongings shelf.",
    "Keep your own belongings on your shelf and out of sight.",
])
def test_personal_drinking_bottle_storage_does_not_recommend_juice_guides(local, monkeypatch, staff_content):
    db, folder = local
    add_article(db, folder, article_id=1, title="Closing Spring Warehouse",
                content="Record drinking water, juice bottle boxes and bottle caps.")
    add_article(db, folder, article_id=2, title="How to make Honey Juice?",
                content="Put the juice bottle on the counter and add honey.")
    add_article(db, folder, article_id=3, title="Staff belongings Area", content=staff_content)
    monkeypatch.setattr(index, "visual_candidates", lambda path: [])
    data = upload(client_for(1), "where should i put my drinking bottle", content=png_bytes("red")).get_json()
    assert data["article_id"] == 3, data
    assert data["title"] == "Staff belongings Area"
    assert not data.get("options")
    app.analyze_uploaded_image_with_vision.assert_not_called()


def test_personal_storage_without_applicable_rule_does_not_fall_back_to_recipes(local, monkeypatch):
    db, folder = local
    add_article(db, folder, title="How to make Honey Juice?", content="Put the juice bottle on the counter.")
    add_article(db, folder, article_id=2, title="Staff record keeping", content="Staff keep sales records in a cabinet.")
    monkeypatch.setattr(index, "visual_candidates", lambda path: [])
    data = upload(client_for(1), "where should i put my drinking bottle", content=png_bytes("red")).get_json()
    assert data["source"] == "image_unknown"
    assert not data.get("article_id") and not data.get("options")


def test_exact_image_and_text_use_current_quote_without_vision(local):
    db, folder = local
    add_article(db, folder)
    response = upload(client_for(1), "Where should I put this bottle?")
    data = response.get_json()
    assert response.status_code == 200, data
    assert data["article_id"] == 1
    assert data["answer"] == "Put bottles in the designated belongings area."
    assert data["image_similarity"] == 1.0
    assert data["confidence_kind"] == "not_calibrated"
    app.analyze_uploaded_image_with_vision.assert_not_called()


def test_refresh_followup_references_previous_image(local):
    db, folder = local
    add_article(db, folder)
    reference = upload(client_for(1)).get_json()["attachment_refs"][0]
    # New client represents a refresh/relogin; no process-local attachment state.
    response = client_for(1).post("/api/chat", json={"question": "Where should I put it?",
        "chat_session_id": "main-test", "attachment_refs": [reference]}, headers={"X-CSRF-Token": "synthetic-csrf"})
    assert response.status_code == 200
    assert response.get_json()["article_id"] == 1


@pytest.mark.parametrize("photo_color", ["blue", "red"])
@pytest.mark.parametrize("question", ["how to use this hook", "what is the use of this hook"])
def test_hook_usage_returns_both_current_kb_instructions_without_vision(local, monkeypatch, photo_color, question):
    db, folder = local
    instructions = (
        "Use hook to take down the blind next to the storeroom and place it inside the storeroom. "
        "Use hook to attach the blind cord to the pillar."
    )
    add_article(db, folder, title="Kiosk Opening", content=instructions)
    if photo_color == "red":
        monkeypatch.setattr(index, "visual_candidates", lambda path: [])
    response = upload(client_for(1), question, content=png_bytes(photo_color))
    data = response.get_json()
    assert response.status_code == 200, data
    assert data["source"] == "image_kb_evidence"
    assert data["article_id"] == 1
    assert "take down the blind" in data["answer"]
    assert "attach the blind cord" in data["answer"]
    assert data["answer_evidence"] == "current_kb_quote"
    app.analyze_uploaded_image_with_vision.assert_not_called()


def test_conflicting_storage_locations_still_require_clarification():
    article = {"content": "Keep bottles under the shelf. Store bottles inside the cabinet."}
    assert hybrid.extract_evidence("Where should I keep this bottle?", article) is None


@pytest.mark.parametrize("index_state", ["missing", "pending", "old_model", "stale_source"])
def test_exact_staff_bottle_article_request_does_not_require_clip(local, monkeypatch, index_state):
    db, folder = local
    add_article(db, folder, title="Staff belongings Area")
    if index_state == "missing":
        db.execute("DELETE FROM image_retrieval")
    elif index_state == "pending":
        db.execute("UPDATE image_retrieval SET image_embedding=NULL, image_hash=NULL, embedding_model=NULL")
    elif index_state == "old_model":
        db.execute("UPDATE image_retrieval SET embedding_model='old-model'")
    else:
        db.execute("UPDATE image_retrieval SET source_hash=NULL")
    monkeypatch.setattr(index, "create_image_embedding", Mock(side_effect=AssertionError("Exact images need no CLIP")))
    response = upload(client_for(1), "show me relevant article")
    data = response.get_json()
    assert response.status_code == 200, data
    assert data["source"] == "image_article_match"
    assert data["article_id"] == 1
    assert data["title"] == "Staff belongings Area"
    assert data["answer_evidence"] == "current_kb"
    app.analyze_uploaded_image_with_vision.assert_not_called()


def test_exact_lookup_without_index_excludes_deleted_articles(local):
    db, folder = local
    path = add_article(db, folder)
    db.execute("DELETE FROM image_retrieval")
    db.execute("UPDATE wiki_article SET is_deleted=1")
    assert index.visual_candidates(path) == []


def test_exact_duplicate_images_keep_all_current_article_sources(local):
    db, folder = local
    path = add_article(db, folder)
    add_article(db, folder, article_id=2, title="Another bottle guide")
    db.execute("DELETE FROM image_retrieval")
    encode = Mock(side_effect=AssertionError("Exact images need no CLIP"))
    articles = index.current_articles(index.visual_candidates(path, encode=encode))
    assert {article["article_id"] for article in articles} == {1, 2}
    assert all(article["exact_image"] for article in articles)
    encode.assert_not_called()


@pytest.mark.parametrize("owner,chat", [(2, "main-test"), (1, "main-other")])
def test_owner_and_chat_isolation(local, owner, chat):
    ref = upload(client_for(1)).get_json()["attachment_refs"][0]
    response = client_for(owner).post("/api/chat", json={"question": "Where should I put it?",
        "chat_session_id": chat, "attachment_refs": [ref]}, headers={"X-CSRF-Token": "synthetic-csrf"})
    assert response.status_code == 400
    assert client_for(owner).get(f"/api/chat/attachments/{ref}?chat={chat}").status_code == 404


def test_private_file_and_direct_static_access(local):
    db, folder = local
    data = upload(client_for(1)).get_json()
    assert client_for(1).get(data["uploaded_image_url"]).status_code == 200
    assert client_for(2).get(data["uploaded_image_url"]).status_code == 404
    storage = db.execute("SELECT storage_name FROM chat_attachments").fetchone()[0]
    assert client_for(2).get("/static/uploads/chat/" + storage).status_code == 404


def test_unattributed_legacy_files_are_not_shared_with_every_employee(local):
    db, folder = local
    (folder / "legacy.png").write_bytes(png_bytes())
    assert client_for(1).get("/static/uploads/chat/legacy.png").status_code == 404
    db.execute("INSERT INTO escalation VALUES (9,'/static/uploads/chat/legacy.png',0,1)")
    assert client_for(1).get("/static/uploads/chat/legacy.png").status_code == 200
    assert client_for(2).get("/static/uploads/chat/legacy.png").status_code == 404


def test_expired_and_deleted_attachments_fail_closed(local):
    db, folder = local
    ref = upload(client_for(1)).get_json()["attachment_refs"][0]
    db.execute("UPDATE chat_attachments SET expires_at = '2000-01-01'")
    with pytest.raises(attachments.AttachmentError):
        attachments.load_attachment(1, "main-test", ref, folder)
    db.execute("UPDATE chat_attachments SET expires_at = '2099-01-01'")
    (folder / db.execute("SELECT storage_name FROM chat_attachments").fetchone()[0]).unlink()
    with pytest.raises(attachments.AttachmentError):
        attachments.load_attachment(1, "main-test", ref, folder)


def test_multiple_images_ask_which_one(local):
    client = client_for(1)
    refs = [upload(client).get_json()["attachment_refs"][0] for _ in range(2)]
    app.analyze_uploaded_image_with_vision.reset_mock()
    response = client.post("/api/chat", json={"question": "Where should I put it?",
        "chat_session_id": "main-test", "attachment_refs": refs}, headers={"X-CSRF-Token": "synthetic-csrf"})
    assert response.get_json()["source"] == "image_ambiguous"
    app.analyze_uploaded_image_with_vision.assert_not_called()


def test_index_changes_and_deleted_sources_excluded(local):
    db, folder = local
    path = add_article(db, folder)
    candidates = index.visual_candidates(path)
    db.execute("UPDATE wiki_article SET content = 'Updated rule' WHERE article_id = 1")
    assert index.current_articles(candidates) == []
    cursor = Cursor(db)
    index.sync_article(cursor, 1)
    assert index.current_articles(index.visual_candidates(path))[0]["content"] == "Updated rule"
    db.execute("UPDATE wiki_article SET is_deleted = 1")
    index.sync_article(cursor, 1)
    assert db.execute("SELECT COUNT(*) FROM image_retrieval").fetchone()[0] == 0
    cursor.close()


def test_embedding_model_mismatch_excluded(local):
    db, folder = local
    path = add_article(db, folder)
    db.execute("UPDATE image_retrieval SET embedding_model = 'old-model'")
    assert index.visual_candidates(different_photo(folder)) == []


def test_candidates_beyond_200_and_article_duplicates(local):
    db, folder = local
    path = add_article(db, folder)
    db.execute("UPDATE image_retrieval SET image_hash = 'not-an-exact-hash', image_embedding = '[0,1,0]'")
    row = dict(db.execute("SELECT * FROM image_retrieval").fetchone())
    for _ in range(530):
        db.execute("INSERT INTO image_retrieval (source_type,source_id,image_url,image_embedding,embedding_model,source_hash,image_hash) VALUES ('knowledge_base',1,?,?,?,?,?)",
                   (row["image_url"], "[0,1,0]", embeddings.MODEL_VERSION, row["source_hash"], "other"))
    db.execute("UPDATE image_retrieval SET image_embedding = '[1,0,0]' WHERE image_id = (SELECT MAX(image_id) FROM image_retrieval)")
    result = index.visual_candidates(different_photo(folder), encode=lambda path: "[1,0,0]")
    assert len(result) == 1
    assert result[0]["image_similarity"] == 1.0


def test_similar_image_uses_real_cosine_and_groups_articles(local):
    db, folder = local
    path = add_article(db, folder)
    db.execute("UPDATE image_retrieval SET image_hash = 'different-bytes', image_embedding = '[0.9,0.1,0]'")
    result = index.visual_candidates(different_photo(folder), encode=lambda path: "[1,0,0]")
    assert not result[0]["exact_image"]
    assert 0.98 < result[0]["image_similarity"] < 1.0


def test_missing_local_clip_returns_no_fake_match(local):
    db, folder = local
    path = add_article(db, folder)
    db.execute("UPDATE image_retrieval SET image_hash = 'different'")
    assert index.visual_candidates(different_photo(folder), encode=lambda path: None) == []


def test_unknown_object_and_vision_failure_never_invent_policy(local, monkeypatch):
    db, folder = local
    ref = upload(client_for(1)).get_json()["attachment_refs"][0]
    monkeypatch.setattr(index, "visual_candidates", lambda path: [])
    analyze = Mock(return_value=None)
    result, query, refs = hybrid.process(1, "main-test", "Where should I put it?", folder, [ref], analyze=analyze)
    assert result["source"] == "image_unknown"
    assert result["answer_evidence"] == "not_established"
    hybrid.process(1, "main-test", "Where should I put it?", folder, [ref], analyze=analyze)
    analyze.assert_called_once()


def test_reupload_same_image_reuses_persistent_observations_in_same_chat(local, monkeypatch):
    _, folder = local
    monkeypatch.setattr(index, "visual_candidates", lambda path: [])
    analyze = app.analyze_uploaded_image_with_vision
    analyze.return_value = {"isWorkRelated": True, "detectedObjects": ["synthetic-object"], "possibleAliases": []}
    first = upload(client_for(1)).get_json()["attachment_refs"][0]
    hybrid.process(1, "main-test", "Where should I put it?", folder, [first], analyze=analyze,
                   vision_identity=lambda: "synthetic-model")
    second = upload(client_for(1)).get_json()["attachment_refs"][0]
    assert first != second
    hybrid.process(1, "main-test", "Where should I put it?", folder, [second], analyze=analyze,
                   vision_identity=lambda: "synthetic-model")
    analyze.assert_called_once()


def test_named_independent_question_does_not_spend_vision(local, monkeypatch):
    _, folder = local
    ref = upload(client_for(1)).get_json()["attachment_refs"][0]
    analyze = Mock(side_effect=AssertionError("Vision is unnecessary for a named text topic"))
    result, query, _ = hybrid.process(1, "main-test", "Explain attendance policy", folder, [ref], analyze=analyze)
    assert result is None and query == "Explain attendance policy"
    analyze.assert_not_called()


def test_unseen_object_vision_is_search_hint_even_when_work_related_false(local, monkeypatch):
    db, folder = local
    add_article(db, folder)
    ref = upload(client_for(1), content=png_bytes("red")).get_json()["attachment_refs"][0]
    monkeypatch.setattr(index, "visual_candidates", lambda path: [])
    analyze = Mock(return_value={"isWorkRelated": False, "confidence": .99,
        "detectedObjects": ["bottle"], "possibleAliases": []})
    result, query, refs = hybrid.process(1, "main-test", "Where should I put it?", folder, [ref], analyze=analyze)
    assert result["article_id"] == 1
    assert result["answer"] == "Put bottles in the designated belongings area."
    assert "vision_irrelevant_image" not in json.dumps(result)


def test_document_upload_never_enters_image_service(local, monkeypatch):
    process = Mock(side_effect=AssertionError("Document must not enter image pipeline"))
    monkeypatch.setattr(hybrid, "process", process)
    monkeypatch.setattr(app, "process_question", lambda **kwargs: ({"reply": "Document stored", "answer": "Document stored",
        "source": "document_test", "confidence": .8, "fallback": False}, 200))
    monkeypatch.setattr(app, "log_request", lambda *a, **k: None)
    monkeypatch.setattr(app, "save_qa_to_db", lambda *a, **k: None)
    response = upload(client_for(1), "Read this file", content=b"%PDF-1.4\nSynthetic", filename="synthetic.pdf")
    assert response.status_code == 200, response.get_json()
    process.assert_not_called()


def test_decoding_rejects_corruption_and_pixel_limit(local, monkeypatch):
    _, folder = local
    path = folder / "bad.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\ncorrupt")
    with pytest.raises(Exception):
        embeddings.decode_image(path)
    path.write_bytes(png_bytes())
    monkeypatch.setattr(embeddings, "MAX_IMAGE_PIXELS", 10)
    with pytest.raises(ValueError):
        embeddings.decode_image(path)


def test_blind_fixture_exists_but_no_claim_of_semantic_match():
    path = Path(__file__).parent.parent / "static/sop_images/kiosk_opening/step3_1.jpg"
    assert path.is_file()
    assert embeddings.decode_image(path).width <= 768


def test_draft_eligibility_and_external_urls():
    assert not index.published({"status": "draft"})
    assert not index.published({"approval_status": "pending"})
    assert index.local_image_url("https://untrusted.invalid/static/uploads/articles/a.jpg") is None
    assert index.local_image_url("/static/uploads/articles/../private.jpg") is None
    assert index.local_image_url("data:image/png;base64,x") is None


def test_index_worker_encodes_outside_database_transaction_and_retries(local, monkeypatch):
    db, folder = local
    add_article(db, folder)
    db.execute("UPDATE image_retrieval SET image_embedding = NULL, image_hash = NULL")
    active = [0]
    class TrackedConnection(Connection):
        def __init__(self, database):
            super().__init__(database)
            active[0] += 1

        def close(self):
            active[0] -= 1

    monkeypatch.setattr(index, "get_db_connection", lambda: TrackedConnection(db))
    def check_closed(path):
        assert active[0] == 0, "Model work must not hold database connections"
        return None
    encode = Mock(side_effect=check_closed)
    monkeypatch.setattr(index, "create_image_embedding", encode)
    assert index.process_pending()["indexed"] == 0
    assert db.execute("SELECT index_error FROM image_retrieval").fetchone()[0] == "encoding_unavailable"
    encode.side_effect = lambda path: "[1,0,0]" if active[0] == 0 else None
    assert index.process_pending()["indexed"] == 1
    assert db.execute("SELECT image_hash FROM image_retrieval").fetchone()[0]


def test_vision_payload_contains_normalized_bytes_and_actual_usage(local, monkeypatch):
    import base64
    import ai_provider_service as provider
    _, folder = local
    path = folder / "synthetic.gif"
    Image.new("RGB", (12, 16), "green").save(path, format="GIF")
    response = Mock()
    response.json.return_value = {"candidates": [{"content": {"parts": [{"text": '{"detectedObjects": ["item"]}'}]}}],
                                  "usageMetadata": {"promptTokenCount": 123, "candidatesTokenCount": 20}}
    post = Mock(return_value=response)
    monkeypatch.setattr(provider.requests, "post", post)
    result = provider._call_gemini_vision("Describe only", path, "gemini-test", "synthetic-key", 20)
    body = post.call_args.kwargs["json"]
    image = body["contents"][0]["parts"][1]["inline_data"]
    assert image["mime_type"] == "image/jpeg"
    assert base64.b64decode(image["data"]).startswith(b"\xff\xd8")
    assert result["usage"]["promptTokenCount"] == 123


@pytest.mark.parametrize("payload", [
    '{"isWorkRelated":"false","confidence":0.9}',
    '{"isWorkRelated":true,"confidence":2}',
    '{"isWorkRelated":true,"detectedObjects":"bottle"}',
])
def test_invalid_vision_schema_rejected(payload):
    with pytest.raises(ValueError):
        app._parse_vision_json_reply(payload)


def test_source_quote_must_be_current_and_answer_question(local):
    db, folder = local
    add_article(db, folder)
    assert hybrid.verify_text_result("What is the attendance policy?", "attendance policy", {"article_id": 1}, []) is None
    db.execute("UPDATE wiki_article SET is_deleted = 1")
    assert hybrid.verify_text_result("Where should I put the bottle?", "bottle", {"article_id": 1}, []) is None


@pytest.mark.parametrize("valid_quote", [False, True])
def test_image_provider_cannot_return_invented_english_policy(local, monkeypatch, valid_quote):
    from flask import g
    db, folder = local
    add_article(db, folder)
    quote = "Put bottles in the designated belongings area."
    monkeypatch.setattr(app, "build_ai_chat_context", lambda *a, **k:
        ("### Staff belongings Area\n" + quote, [{"article_id": 1, "title": "Staff belongings Area"}]))
    monkeypatch.setattr(app.ai_provider_service, "generate_ai_reply", lambda *a, **k: json.dumps({
        "answered": True, "answer": "INVENTED INSTRUCTION", "sourceTitle": "Staff belongings Area",
        "evidenceQuote": quote if valid_quote else "A rule that does not exist in the KB."}))
    with app.app.test_request_context("/api/chat", json={}):
        g.image_request = True
        result = app.answer_question_with_ai_provider("Where should I put this bottle?")
    if valid_quote:
        assert result["answer"] == quote
        assert "INVENTED" not in result["answer"]
    else:
        assert result is None


def test_vision_model_metadata_is_checked_and_cached(local, monkeypatch):
    import ai_provider_service as provider
    monkeypatch.setattr(provider, "_vision_models", {})
    response = Mock()
    response.json.return_value = {"supportedGenerationMethods": ["generateContent"]}
    get = Mock(return_value=response)
    monkeypatch.setattr(provider.requests, "get", get)
    provider.validate_vision_model("gemini-synthetic", "synthetic-key", 20)
    provider.validate_vision_model("gemini-synthetic", "synthetic-key", 20)
    get.assert_called_once()
    with pytest.raises(provider.AIProviderVisionUnsupportedError):
        provider.validate_vision_model("text-embedding", "synthetic-key", 20)


def test_authentication_and_csrf_required(local):
    assert upload(app.app.test_client()).status_code == 401
    response = client_for(1).post("/api/chat", json={"question": "hello"})
    assert response.status_code == 403


def test_model_initialization_is_singleton_under_concurrency(monkeypatch):
    constructor = Mock(return_value=object())
    monkeypatch.setattr(embeddings, "_model", None)
    monkeypatch.setattr(embeddings, "_model_failure_until", 0)
    monkeypatch.delenv("DISABLE_IMAGE_EMBEDDING", raising=False)
    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(set_num_threads=lambda value: None))
    monkeypatch.setitem(sys.modules, "sentence_transformers", types.SimpleNamespace(SentenceTransformer=constructor))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: embeddings.get_image_model(), range(8)))
    constructor.assert_called_once()
    assert all(result is results[0] for result in results)
    assert constructor.call_args.kwargs["device"] == "cpu"
    assert constructor.call_args.kwargs["revision"] == embeddings.MODEL_REVISION


def test_clip_failure_is_attempted_once_for_many_candidates(local):
    db, folder = local
    path = add_article(db, folder)
    db.execute("UPDATE image_retrieval SET image_hash = 'different'")
    row = dict(db.execute("SELECT * FROM image_retrieval").fetchone())
    for _ in range(5):
        db.execute("INSERT INTO image_retrieval (source_type,source_id,image_url,image_embedding,embedding_model,source_hash,image_hash) VALUES ('knowledge_base',1,?,?,?,?,?)",
                   (row["image_url"], "[0,1,0]", embeddings.MODEL_VERSION, row["source_hash"], "other"))
    encode = Mock(return_value=None)
    assert index.visual_candidates(different_photo(folder), encode=encode) == []
    encode.assert_called_once()


def test_approved_escalation_images_use_current_review_and_rejection_excludes(local):
    db, folder = local
    path = folder / "private_synthetic.png"
    path.write_bytes(png_bytes())
    url = "/static/uploads/chat/" + path.name
    db.execute("INSERT INTO escalation (escalation_id,image_url,is_deleted) VALUES (99, ?, 0)", (url,))
    db.execute("INSERT INTO review_queue VALUES (1,99,'approved','Synthetic item storage','Keep the item inside the designated area.')")
    db.execute("INSERT INTO image_retrieval (source_type,source_id,answer,image_url,image_embedding,embedding_model,image_hash) VALUES ('approved_escalation',99,'STALE COPY',?,?,?,?)",
        (url, '[1,0,0]', embeddings.MODEL_VERSION, embeddings.image_sha256(path)))
    candidates = index.visual_candidates(path)
    articles = index.current_articles(candidates)
    result = hybrid.grounded_result("Where should I put it?", articles, [])
    assert result["source"] == "image_approved_review_evidence"
    assert result["answer"] == "Keep the item inside the designated area."
    assert result["article_id"] is None
    db.execute("INSERT INTO review_queue VALUES (2,99,'rejected','','')")
    assert index.visual_candidates(path) == []
    assert index.current_articles(candidates) == []


@pytest.mark.skipif(os.getenv("RUN_REAL_CLIP_TESTS") != "1", reason="Requires downloaded CLIP/Torch; no model download in CI")
def test_real_clip_bundled_blind_fixture(local):
    db, folder = local
    path = add_article(db, folder, title="Synthetic blind test guide", content="Test fixture only.")
    fixture = Path(__file__).parent.parent / "static/sop_images/kiosk_opening/step3_1.jpg"
    path.write_bytes(fixture.read_bytes())
    cursor = Cursor(db)
    index.sync_article(cursor, 1)
    db.execute("UPDATE image_retrieval SET image_embedding = NULL")
    assert index.process_pending()["indexed"] == 1
    original = json.loads(db.execute("SELECT image_embedding FROM image_retrieval").fetchone()[0])
    assert len(original) == 512
    variation = folder / "variation.jpg"
    embeddings.decode_image(fixture).resize((500, 650)).save(variation, quality=70)
    candidates = index.visual_candidates(variation)
    assert candidates and candidates[0]["source_id"] == 1
    assert not candidates[0]["exact_image"]
    assert index.current_articles(candidates)[0]["article_id"] == 1
