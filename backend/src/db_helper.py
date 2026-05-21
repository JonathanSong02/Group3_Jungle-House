import os
import mysql.connector


# =========================
# DATABASE CONNECTION
# =========================

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST"),
        port=int(os.getenv("MYSQL_PORT", 3306)),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE"),
    )


# =========================
# TEXT HELPER
# =========================

def normalize_text(text):
    text = str(text or "").lower().strip()
    return " ".join(text.split())

def token_set(text):
    import re
    stop_words = {
        "a", "an", "the", "to", "for", "of", "and", "or", "is", "are", "do", "does",
        "can", "i", "me", "my", "you", "your", "what", "how", "when", "where", "which",
        "show", "tell", "need", "want", "about", "info", "information"
    }
    tokens = re.findall(r"[a-z0-9]+", normalize_text(text))
    return {token for token in tokens if token not in stop_words and len(token) > 1}

def similarity_ratio(a, b):
    a_tokens = token_set(a)
    b_tokens = token_set(b)

    if not a_tokens or not b_tokens:
        return 0.0

    return len(a_tokens & b_tokens) / max(len(a_tokens), len(b_tokens))


def is_low_quality_saved_ai_answer(row):
    """
    Ignore old unapproved Team Lead answers and bad AI fallback rows.
    Only Manager-approved manual answers should be trusted for escalation retrieval.
    """
    row = row or {}
    source = str(row.get("source") or "").lower().strip()
    answer = normalize_text(row.get("answer") or row.get("reply") or "")

    # IMPORTANT:
    # Team Lead answer should NOT be retrieved by AI Chat before Manager approval.
    if source == "team_lead":
        return True

    bad_phrases = [
        "i found a few possible answers",
        "i found more than one possible answer",
        "please select one",
        "please choose one",
        "i could not understand",
        "i m not fully sure",
        "im not fully sure",
        "not fully sure which topic",
        "please ask again using a clearer",
        "please escalate this question",
        "system error",
        "model prediction failed",
        "ai model is not available",
    ]

    if any(phrase in answer for phrase in bad_phrases):
        return True

    return False


# =========================
# QA KNOWLEDGE HELPERS
# =========================

def save_qa_to_db(question, result, source="ai"):
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        answer = result.get("answer") or result.get("reply") or ""
        confidence = float(result.get("confidence", result.get("score", 0.0)) or 0.0)

        cursor.execute("""
            INSERT INTO qa_knowledge (question, answer, source, confidence)
            VALUES (%s, %s, %s, %s)
        """, (
            question,
            answer,
            source,
            confidence
        ))

        conn.commit()
        return True

    except Exception as e:
        print("SAVE QA ERROR:", e)
        if conn:
            conn.rollback()
        return False

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def search_similar_question(question, team_lead_only=False):
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        question = normalize_text(question)

        if team_lead_only:
            cursor.execute("""
                SELECT *
                FROM qa_knowledge
                WHERE source = 'team_lead'
                ORDER BY confidence DESC, created_at DESC
            """)
        else:
            cursor.execute("""
                SELECT *
                FROM qa_knowledge
                ORDER BY 
                    CASE 
                        WHEN source = 'team_lead' THEN 1
                        ELSE 2
                    END,
                    confidence DESC
            """)

        rows = cursor.fetchall()

        best_match = None
        best_score = 0.0

        for row in rows:
            if is_low_quality_saved_ai_answer(row):
                continue

            db_q = normalize_text(row.get("question"))

            # Exact resolved question should always return.
            if question == db_q:
                row["score"] = float(row.get("confidence", 1.0) or 1.0)
                row["confidence"] = float(row.get("confidence", 1.0) or 1.0)
                return row

            ratio = similarity_ratio(question, db_q)

            # Avoid broad words like "product" or "holiday" wrongly overriding training data.
            if ratio >= 0.80 and ratio > best_score:
                best_match = row
                best_score = ratio

        if best_match:
            best_match["score"] = float(best_match.get("confidence", best_score) or best_score)
            best_match["confidence"] = float(best_match.get("confidence", best_score) or best_score)
            return best_match

        return None

    except Exception as e:
        print("SEARCH SIMILAR QUESTION ERROR:", e)
        return None

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def search_similar_questions(question, team_lead_only=False, limit=5):
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        question = normalize_text(question)

        if team_lead_only:
            cursor.execute("""
                SELECT *
                FROM qa_knowledge
                WHERE source = 'manager_approved_review'
                ORDER BY confidence DESC, created_at DESC
            """)
        else:
            cursor.execute("""
                SELECT *
                FROM qa_knowledge
                WHERE COALESCE(source, '') <> 'team_lead'
                ORDER BY 
                    CASE 
                        WHEN source = 'manager_approved_review' THEN 1
                        ELSE 2
                    END,
                    confidence DESC
            """)

        rows = cursor.fetchall()

        matches = []

        for row in rows:
            if is_low_quality_saved_ai_answer(row):
                continue

            db_q = normalize_text(row.get("question"))
            ratio = similarity_ratio(question, db_q)

            if question == db_q:
                ratio = 1.0

            if ratio >= 0.30:
                row["score"] = float(row.get("confidence", ratio) or ratio)
                row["confidence"] = float(row.get("confidence", ratio) or ratio)
                row["match_score"] = ratio
                matches.append(row)

        matches.sort(
            key=lambda item: (
                item.get("match_score", 0.0),
                item.get("confidence", 0.0)
            ),
            reverse=True
        )

        return matches[:limit]

    except Exception as e:
        print("SEARCH SIMILAR QUESTIONS ERROR:", e)
        return []

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =========================
# ESCALATION HELPERS
# =========================

def create_escalation(question, ai_result, asked_by=None, image_url=None, image_type=None):
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        ai_answer = ""
        ai_score = 0.0
        ai_source = "unknown"

        if isinstance(ai_result, dict):
            ai_answer = ai_result.get("answer") or ai_result.get("reply") or ""
            ai_score = ai_result.get("score") or ai_result.get("confidence") or 0.0
            ai_source = ai_result.get("source") or "unknown"
        else:
            ai_answer = str(ai_result)

        cursor.execute("""
            INSERT INTO escalation
            (
                question,
                ai_answer,
                ai_score,
                ai_source,
                asked_by,
                status,
                image_url,
                image_type
            )
            VALUES (%s, %s, %s, %s, %s, 'pending', %s, %s)
        """, (
            question,
            ai_answer,
            ai_score,
            ai_source,
            asked_by,
            image_url,
            image_type
        ))

        conn.commit()
        return cursor.lastrowid

    except Exception as error:
        print("CREATE ESCALATION ERROR:", error)

        if conn:
            conn.rollback()

        return None

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def resolve_escalation(escalation_id, answer, user_id=None, answer_image_url=None, answer_image_type=None):
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT question, image_url, image_type
            FROM escalation
            WHERE escalation_id = %s
        """, (escalation_id,))

        escalation = cursor.fetchone()

        if not escalation:
            conn.rollback()
            return False

        question = escalation.get("question") or ""

        final_image_url = answer_image_url or escalation.get("image_url")
        final_image_type = answer_image_type or escalation.get("image_type")

        # Team Lead answer only updates escalation status.
        # Do NOT save into qa_knowledge here.
        cursor.execute("""
            UPDATE escalation
            SET 
                manual_answer = %s,
                handled_by = %s,
                status = 'resolved',
                resolved_at = NOW(),
                image_url = COALESCE(%s, image_url),
                image_type = COALESCE(%s, image_type)
            WHERE escalation_id = %s
        """, (
            answer,
            user_id,
            final_image_url,
            final_image_type,
            escalation_id
        ))

        cursor.execute("""
            SELECT review_id
            FROM review_queue
            WHERE escalation_id = %s
            ORDER BY review_id DESC
            LIMIT 1
        """, (escalation_id,))

        review = cursor.fetchone()

        if review:
            cursor.execute("""
                UPDATE review_queue
                SET
                    question = %s,
                    answer = %s,
                    submitted_by = %s,
                    reviewed_by = NULL,
                    reviewer_comment = '',
                    status = 'pending',
                    reviewed_at = NULL,
                    published_at = NULL
                WHERE review_id = %s
            """, (
                question,
                answer,
                user_id,
                review["review_id"]
            ))
        else:
            cursor.execute("""
                INSERT INTO review_queue
                (escalation_id, question, answer, submitted_by, status, created_at)
                VALUES (%s, %s, %s, %s, 'pending', NOW())
            """, (
                escalation_id,
                question,
                answer,
                user_id
            ))

        # Remove old trusted answer for this same question while waiting for Manager approval.
        cursor.execute("""
            DELETE FROM qa_knowledge
            WHERE question = %s
        """, (question,))

        conn.commit()
        return True

    except Exception as error:
        print("RESOLVE ESCALATION ERROR:", error)

        if conn:
            conn.rollback()

        return False

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()