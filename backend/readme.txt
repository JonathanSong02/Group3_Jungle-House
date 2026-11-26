How to install and run the backend on a computer:
see docs/handover/HANDOVER_GUIDE.md, Part 2 (Steps 9-13).

Short version (Windows PowerShell, Python 3.12):
  cd backend\src
  py -3.12 -m venv venv
  .\venv\Scripts\Activate.ps1
  pip install -r ..\requirements.txt
  . .\.env.local.ps1      (your local settings file; see the guide, Step 12.2)
  python app.py

Website (second window):
  cd jungle-house-wiki-ai
  npm ci
  npm run dev
