cd backend/src
python -m venv venv
.\venv\Scripts\Activate.ps1
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
pip install flask flask-cors mysql-connector-python werkzeug pandas torch scikit-learn

npm install
npm run dev

