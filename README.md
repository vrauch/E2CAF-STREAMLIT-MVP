# Meridant Matrix

A Streamlit web application for delivering **Transformation Maturity Model (TMM)** assessments. Consultants use it to evaluate client capabilities against configurable frameworks, generate AI-powered findings and recommendations, and track engagements over time.

---

## Features

| Area | What it does |
|---|---|
| **Dashboard** | Interactive domain/subdomain/capability explorer with maturity scores, dependency charts, and drilldown cards |
| **Assessments** | Paginated list of all engagements — filter by framework, status, or client; resume in-progress work |
| **Create Assessment** | Guided wizard: pick a use case → score capabilities → AI-generated questions → findings narrative → roadmap & recommendations |
| **Architecture** | Displays the platform architecture diagram (`assets/architecture.png`) |
| **Admin** | User management (admin-only) |
| **Auth** | Cookie-based login via `streamlit-authenticator`; role-based admin access |
| **AI** | Claude (Anthropic) generates intent statements, assessment questions, findings narratives, gap recommendations |
| **Multi-framework** | Supports multiple named frameworks (MMTF, NIST CSF 2, etc.) selectable at assessment time |

---

## Tech Stack

- **Python 3.11+**, Streamlit ≥ 1.45
- **SQLite** (two separate databases — see below)
- **Anthropic Claude** via `anthropic` SDK
- **Bootstrap 5.3** + Chart.js (injected into `st.components.v1.html`)
- **Fly.io** — production hosting (Sydney region, `streamlit-mvp.fly.dev`)
- **Docker** — local dev and production image

---

## Two Databases

| File | Purpose | Flow |
|---|---|---|
| `data/meridant_frameworks.db` | Framework definitions — domains, subdomains, capabilities, use cases, maturity levels | Local → Fly.io (pushed on deploy) |
| `data/meridant.db` | Assessment records — client engagements, scores, findings, recommendations | Fly.io → Local (pulled, never pushed manually) |

> **Rule (ADR-009):** The assessment DB flows **one way**: production → local. It is never committed to git and never pushed via `deploy.sh`. Use `db-push.sh --assessments` only for deliberate restores.

---

## Local Development

### macOS / Linux

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # set ANTHROPIC_API_KEY, db paths, etc.
cp auth_config.yaml.example auth_config.yaml   # or use your existing file

streamlit run app.py
```

### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy .env.example .env
copy auth_config.yaml.example auth_config.yaml

streamlit run app.py
```

### Environment Variables (`.env`)

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `MERIDANT_FRAMEWORKS_DB_PATH` | Path to framework DB (default: `data/meridant_frameworks.db`) |
| `MERIDANT_ASSESSMENTS_DB_PATH` | Path to assessment DB (default: `data/meridant.db`) |
| `AUTH_CONFIG_PATH` | Path to auth config YAML (default: `auth_config.yaml`) |

---

## Database Scripts

All scripts live in the project root and have both **bash** (`.sh`) and **PowerShell** (`.ps1`) versions.

### Sync from production → local

```bash
./db-pull.sh                  # pull both DBs from Fly.io
./db-pull.sh --frameworks     # framework DB only
./db-pull.sh --assessments    # assessment DB only
./db-pull.sh --dry-run        # preview without downloading
```

```powershell
.\db-pull.ps1                 # same options: -Frameworks, -Assessments, -DryRun
```

### Deploy code + framework DB → production

```bash
./deploy.sh                          # git commit + fly deploy + upload framework DB
./deploy.sh "Release v1.3"           # custom commit message
./deploy.sh --skip-db                # code only, skip DB upload
./deploy.sh --skip-code              # DB upload only, skip git + fly deploy
```

```powershell
.\deploy.ps1                         # same options: -SkipDb, -SkipCode, -Message
```

### Push a DB to production (deliberate override)

```bash
./db-push.sh --frameworks            # push framework DB (safe)
./db-push.sh --assessments           # push assessment DB (DESTRUCTIVE — overwrites prod data)
./db-push.sh --both                  # push both
./db-push.sh --dry-run               # preview without uploading
```

```powershell
.\db-push.ps1 -Frameworks            # same options: -Assessments, -Both, -DryRun
```

> Pushing the assessment DB requires typing `YES` at the confirmation prompt.

---

## Multi-Machine Dev Workflow

```
Machine A (made framework changes)  →  ./deploy.sh
Machine B (needs to sync)           →  ./db-pull.sh
```

Both machines always use Fly.io as the single source of truth for the assessment DB.

---

## Deploy to Fly.io

### One-time setup

```bash
fly auth login
fly launch          # only for a brand new app — existing app uses fly.toml
```

### Routine deploy

```bash
./deploy.sh "your message"
```

This does three things in sequence:
1. `git commit` + `git push` → GitHub
2. `fly deploy` → rebuilds the Docker image and restarts the app
3. SFTP upload → pushes the framework DB to the `/data` persistent volume

### First-time volume setup (new Fly machine)

```bash
fly machine start --app streamlit-mvp
fly ssh sftp shell --app streamlit-mvp
put auth_config.yaml /data/auth_config.yaml
exit
./deploy.sh
```

---

## Project Structure

```
streamlit-mvp/
├── app.py                      # entry point — auth, sidebar nav, page routing
├── auth_config.yaml            # user credentials (not committed)
├── fly.toml                    # Fly.io config
├── Dockerfile
├── requirements.txt
│
├── src/
│   ├── pages/
│   │   ├── dashboard.py        # interactive framework explorer
│   │   ├── assessments.py      # assessment list + filters + pagination
│   │   ├── create_assessment.py# assessment wizard
│   │   ├── architecture.py     # architecture diagram page
│   │   └── admin_users.py      # user management (admin only)
│   ├── assessment_builder.py   # use-case → capability resolution logic
│   ├── assessment_store.py     # CRUD for assessments, findings, recommendations
│   ├── recommendation_engine.py# AI-powered gap recommendations
│   ├── question_generator.py   # AI-generated assessment questions
│   ├── ai_client.py            # Anthropic Claude wrapper
│   ├── meridant_client.py      # SQLite client (frameworks + assessments DBs)
│   ├── sql_templates.py        # reusable query helpers
│   ├── heatmap.py              # maturity heatmap rendering
│   └── roadmap.py              # roadmap chart rendering
│
├── scripts/                    # one-off DB seeding and migration scripts
├── data/                       # local SQLite files (gitignored)
├── assets/                     # static files (architecture.png, etc.)
│
├── deploy.sh / deploy.ps1      # deploy code + framework DB to production
├── db-pull.sh / db-pull.ps1    # pull DBs from production to local
└── db-push.sh / db-push.ps1    # push DBs to production (use with care)
```

---

## Authentication

Users are defined in `auth_config.yaml` (stored on the Fly.io `/data` volume in production, in the project root locally).

```yaml
credentials:
  usernames:
    alice:
      name: Alice Smith
      password: <bcrypt hash>
admins:
  - alice
cookie:
  name: meridant_auth
  key: <secret>
  expiry_days: 30
```

Admin users get an additional **Admin** nav item for user management.

---

## Windows 11 Setup (one-time)

```powershell
# Install fly CLI
winget install Fly-io.flyctl

# Allow local PowerShell scripts to run
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Log in
fly auth login
```

Then use the `.ps1` scripts in place of the `.sh` scripts for all database and deploy operations.
