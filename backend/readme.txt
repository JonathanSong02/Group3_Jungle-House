python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
pip install flask flask-cors mysql-connector-python werkzeug
python training_data.py
python train_model.py
python app_aichat.py

npm install
npm run dev

