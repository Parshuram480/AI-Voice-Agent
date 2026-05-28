# Developer Setup

## Prerequisites
- Python 3.11+
- PostgreSQL (optional)
- Twilio credentials (optional for local testing)

## Install
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## Configure
```bash
copy .env.example .env
```
Fill in GROQ_API_KEY and optional Twilio/PostgreSQL settings.

Optional settings:
- SESSION_TTL_SECONDS, SESSION_MAX_TURNS, SESSION_MAX_RETRIES
- LLM_REPHRASE, LLM_REPHRASE_MAX_TOKENS, LLM_REPHRASE_TEMPERATURE

## Database (Optional)
```bash
createdb voice_agent
psql -U postgres -d voice_agent -f sql/init.sql
```

## Run
```bash
uvicorn app.main:app --reload --port 8000
```

## Tests
```bash
pytest
```
