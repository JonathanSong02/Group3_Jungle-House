import mysql.connector

def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host="192.168.146.1",
            user="root",
            password="JHapp123!",   # 🔥 change this
            database="jungle_house_ai"
        )
        return conn
    except mysql.connector.Error as err:
        print("Database connection failed:", err)
        return None