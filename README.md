# TMM Streamlit MVP

Streamlit web UI for the Transformation Maturity Model (TMM).

## Run locally
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# edit .env (set TMM_DB_PATH, ANTHROPIC_API_KEY, etc.)
streamlit run app.py
```
