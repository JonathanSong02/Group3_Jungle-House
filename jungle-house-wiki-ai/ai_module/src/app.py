from flask_cors import CORS
from flask import Flask, request, jsonify
import mysql.connector

# ✅ CREATE APP FIRST
app = Flask(__name__)
CORS(app)

# 🔥 CONNECT TO MYSQL
db = mysql.connector.connect(
    host="localhost",
    user="jh_app",
    password="JHapp123!",
    database="jungle_house_ai"
)

cursor = db.cursor(dictionary=True)

# ✅ HOME ROUTE
@app.route("/")
def home():
    return "Flask backend running"

# ✅ USERS ROUTE
@app.route("/users")
def get_users():
    cursor.execute("SELECT * FROM users")
    result = cursor.fetchall()
    return jsonify(result)

# ✅ ASK ROUTE (YOUR NEW ONE)
@app.route("/ask", methods=["POST"])
def ask():
    data = request.json
    question = data.get("question")

    return jsonify({
        "answer": f"You asked: {question}",
        "category": "General",
        "title": "Demo Answer",
        "score": 0.9
    })

# ✅ RUN SERVER
if __name__ == "__main__":
    app.run(debug=True)