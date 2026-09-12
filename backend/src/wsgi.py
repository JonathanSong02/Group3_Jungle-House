"""Production WSGI entrypoint for Railway."""
from app import app, verify_manager_account

# Preserve the startup check that previously only ran under `python app.py`.
# The function handles its own DB errors and will not crash the web server.
verify_manager_account()
