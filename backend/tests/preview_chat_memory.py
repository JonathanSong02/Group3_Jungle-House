"""Local UI fixture ONLY. Never imports app.py/.env or connects to MySQL.
Run with Flask/flask-cors available and open Vite configured for port 5001.
"""
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from flask import Flask, g, jsonify, request
from flask_cors import CORS
from chat_memory_api import register_chat_memory
import test_persistent_chat as fixtures

fixture = fixtures.PersistenceTests()
fixture.setUp()
app = Flask(__name__)
CORS(app,origins=['http://127.0.0.1:5173','http://127.0.0.1:5174'],supports_credentials=True)

@app.before_request
def synthetic_identity():
    g.owner = 1

@app.route('/api/auth/me')
@app.route('/api/auth/csrf')
def auth_fixture():
    return jsonify(user={'id':1,'full_name':'Synthetic Staff','role':'staff','status':'active'},csrf_token='synthetic-local-csrf')

@app.route('/api/notifications/<int:uid>')
@app.route('/api/notifications')
def notifications_fixture(uid=1):
    return jsonify([])

def generate():
    question = request.get_json()['question']
    if 'delay' in question.lower(): time.sleep(3)
    return jsonify(answer='[Synthetic KB] '+question,reply='[Synthetic KB] '+question,
                   question=question,source='knowledge_base',confidence=.9,
                   escalation_ready=False,context={'unclear_count':0})

store = register_chat_memory(app,lambda:fixtures.Connection(fixture.path),lambda:g.owner,generate)

if __name__=='__main__':
    try: app.run(host='127.0.0.1',port=5001,debug=False,use_reloader=False)
    finally: fixture.doCleanups()
