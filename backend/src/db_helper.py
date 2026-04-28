import mysql.connector

def get_db_connection():
    return mysql.connector.connect(
        host="shuttle.proxy.rlwy.net",
        port=26909,
        user="root",
        password="zzUtzEvBsOnHpeUqaHCIJOdilqfoHxHI",
        database="railway",
    )

def save_qa_to_db(question, result, source="ai"):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO qa_knowledge (question, answer, source, confidence)
        VALUES (%s, %s, %s, %s)
    """, (
        question,
        result.get("answer"),
        source,
        float(result.get("confidence", 0.0))
    ))

    conn.commit()
    cursor.close()
    conn.close()


def search_similar_question(question):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT * FROM qa_knowledge
        WHERE question LIKE %s
        ORDER BY created_at DESC
        LIMIT 1
    """, ("%" + question + "%",))

    result = cursor.fetchone()

    cursor.close()
    conn.close()

    return result


def create_escalation(question, result, user_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO escalation (question, ai_answer, ai_score, ai_source, asked_by)
        VALUES (%s, %s, %s, %s, %s)
    """, (
        question,
        result.get("answer"),
        float(result.get("confidence", 0.0)),
        result.get("source"),
        user_id
    ))

    conn.commit()
    escalation_id = cursor.lastrowid

    cursor.close()
    conn.close()

    return escalation_id


def resolve_escalation(escalation_id, answer, user_id=None):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # get original question
    cursor.execute("SELECT * FROM escalation WHERE escalation_id=%s", (escalation_id,))
    ticket = cursor.fetchone()

    # update escalation table
    cursor.execute("""
        UPDATE escalation
        SET manual_answer=%s,
            status='resolved',
            handled_by=%s,
            resolved_at=NOW()
        WHERE escalation_id=%s
    """, (answer, user_id, escalation_id))

    # save into AI knowledge
    cursor.execute("""
        INSERT INTO qa_knowledge (question, answer, source, confidence)
        VALUES (%s, %s, 'team_lead', 1.0)
    """, (ticket["question"], answer))

    conn.commit()
    cursor.close()
    conn.close()