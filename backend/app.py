from flask import Flask, jsonify
from flask_cors import CORS
import mysql.connector

# ✅ CREATE APP FIRST
app = Flask(__name__)
CORS(app)

# 🔥 DB CONNECTION FUNCTION
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="jh_app",
        password="JHapp123!",
        database="jungle_house_ai"
    )

# ✅ ARTICLES API (🔥 UPDATED WITH ORDER)
@app.route("/articles")
def get_articles():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 🔥 ORDER BY display_order (IMPORTANT)
    cursor.execute("""
        SELECT *
        FROM wiki_article
        ORDER BY 
            display_order IS NULL,   -- null go bottom
            display_order ASC
    """)

    result = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(result)

# ✅ LINKS API
@app.route("/article-links/<int:article_id>")
def get_article_links(article_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT label, url FROM article_links WHERE article_id = %s",
        (article_id,)
    )
    links = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(links)

# ✅ RUN SERVER
if __name__ == "__main__":
    app.run(debug=True)