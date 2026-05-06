import mysql.connector


# =========================
# DATABASE CONNECTION
# =========================

def get_db_connection():
    return mysql.connector.connect(
        host="shuttle.proxy.rlwy.net",
        port=26909,
        user="root",
        password="zzUtzEvBsOnHpeUqaHCIJOdilqfoHxHI",
        database="railway",
    )


# =========================
# TEXT HELPER
# =========================

def normalize_text(text):
    return str(text or "").lower().strip()


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


def search_similar_question(question):
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        question = normalize_text(question)

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

        for row in rows:
            db_q = normalize_text(row.get("question"))

            if question == db_q:
                return row

            if question in db_q or db_q in question:
                best_match = row
                break

        return best_match

    except Exception as e:
        print("SEARCH SIMILAR QUESTION ERROR:", e)
        return None

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =========================
# ESCALATION HELPERS
# =========================

def create_escalation(question, result, user_id=None):
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        answer = result.get("answer") or result.get("reply") or ""
        confidence = float(result.get("confidence", result.get("score", 0.0)) or 0.0)
        source = result.get("source") or "unknown"

        cursor.execute("""
            INSERT INTO escalation
            (
                question,
                ai_answer,
                ai_score,
                ai_source,
                asked_by
            )
            VALUES (%s, %s, %s, %s, %s)
        """, (
            question,
            answer,
            confidence,
            source,
            user_id
        ))

        conn.commit()

        return cursor.lastrowid

    except Exception as e:
        print("CREATE ESCALATION ERROR:", e)
        if conn:
            conn.rollback()
        return None

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def resolve_escalation(escalation_id, answer, user_id=None):
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Get original escalation
        cursor.execute("""
            SELECT *
            FROM escalation
            WHERE escalation_id = %s
            LIMIT 1
        """, (escalation_id,))

        ticket = cursor.fetchone()

        if not ticket:
            return False

        # Update escalation table
        cursor.execute("""
            UPDATE escalation
            SET 
                manual_answer = %s,
                status = 'resolved',
                handled_by = %s,
                resolved_at = NOW()
            WHERE escalation_id = %s
        """, (
            answer,
            user_id,
            escalation_id
        ))

        # Save manual answer into AI knowledge
        cursor.execute("""
            INSERT INTO qa_knowledge
            (
                question,
                answer,
                source,
                confidence
            )
            VALUES (%s, %s, 'team_lead', 1.0)
        """, (
            ticket["question"],
            answer
        ))

        conn.commit()
        return True

    except Exception as e:
        print("RESOLVE ESCALATION ERROR:", e)
        if conn:
            conn.rollback()
        return False

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()