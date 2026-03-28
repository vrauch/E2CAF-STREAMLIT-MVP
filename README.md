# Meridant Matrix

A Streamlit web application for delivering capability maturity assessments. Consultants use it to evaluate client capabilities against configurable frameworks, generate AI-powered findings and recommendations, and track engagements over time.

---

## Features

| Area | What it does |
|---|---|
| **Dashboard** | Interactive domain/subdomain/capability explorer with maturity scores, dependency charts, and drilldown cards |
| **Assessments** | Paginated list of all engagements — filter by framework, status, or client; resume in-progress work |
| **Create Assessment** | Guided 6-step wizard: use case → capability discovery → question generation → response capture → findings + heatmap → roadmap & recommendations |
| **Architecture** | Displays the platform architecture diagram |
| **Admin** | User management (admin-only) |
| **Auth** | Cookie-based login via `streamlit-authenticator`; role-based admin access |
| **AI** | Claude (Anthropic) generates questions, findings narratives, gap recommendations, and transformation roadmaps |

---

## Tech Stack

- **Python 3.12**, Streamlit ≥ 1.45
- **SQLite** (two separate databases — see below)
- **Anthropic Claude** via `anthropic==0.84.0` SDK
- **Bootstrap 5.3** + Chart.js (injected via `st.components.v1.html`)
- **Docker** — the only supported runtime (no local venv)
- **Fly.io** — production hosting (Sydney region, app: `streamlit-mvp`)

---

## Two Databases

| File | Purpose | Direction |
|---|---|---|
| `data/meridant_frameworks.db` | Framework definitions — domains, subdomains, capabilities, use cases, maturity levels | Local → Fly.io (pushed on deploy) |
| `data/meridant.db` | Assessment records — client engagements, scores, findings, recommendations | Fly.io → Local (pulled, never pushed manually) |

> **Rule (ADR-009):** The assessment DB flows **one way**: production → local. It is never committed to git. Use `./db-push.sh --assessments` only for deliberate restores, which requires typing `YES` at the confirmation prompt.

---

## Local Development

> **The app runs exclusively in Docker. There is no local Python environment or virtual environment.**

### Prerequisites

- Docker Desktop running
- `fly` CLI installed (for DB sync and deployment)
- `.env` file at project root (copy from `.env.example`)
- `auth_config.yaml` at project root (obtain from another dev or Fly.io volume)

### Start the app

```bash
# Always use --build — code changes are not picked up by docker compose restart
docker compose up --build

# Detached mode
docker compose up --build -d

# Stop
docker compose down
```

The app runs at `http://localhost:8501`.

### Picking up config file changes (no rebuild needed)

```bash
# After editing auth_config.yaml only — no rebuild required
docker compose restart
```

`docker compose restart` does **not** pick up code changes — always use `docker compose up --build` for those.

### Run scripts inside the container

```bash
docker compose exec app python scripts/seed_v3_assessments.py            # seed test assessments (idempotent)
docker compose exec app python scripts/seed_v3_assessments.py --clean    # remove + re-seed
docker compose exec app python scripts/migrate_multi_framework.py        # idempotent — safe to re-run
```

---

## Environment Variables (`.env`)

Copy `.env.example` to `.env` and fill in your values. The `.env` file is loaded by Docker Compose and is never committed to git.

| Variable | Required | Description |
|---|---|---|
| `MERIDANT_FRAMEWORKS_DB_PATH` | Yes | Path to framework DB inside container (default: `/app/data/meridant_frameworks.db`) |
| `MERIDANT_ASSESSMENTS_DB_PATH` | Yes | Path to assessment DB inside container (default: `/app/data/meridant.db`) |
| `ANTHROPIC_API_KEY` | Yes | Your Anthropic API key |
| `ANTHROPIC_MODEL` | No | Model override (default: `claude-sonnet-4-20250514`) |
| `ANTHROPIC_MAX_RETRIES` | No | Retry attempts on API errors (default: 3) |
| `ANTHROPIC_RETRY_DELAY` | No | Initial retry backoff in seconds (default: 2.0) |
| `ANTHROPIC_RETRY_MAX_DELAY` | No | Max retry backoff cap in seconds (default: 20.0) |
| `ANTHROPIC_RETRY_JITTER` | No | Random jitter added per retry in seconds (default: 0.75) |
| `QUESTION_GEN_CALL_DELAY_SECONDS` | No | Pause between capability question-gen requests (default: 1.5) |
| `QUESTION_GEN_CAPABILITY_ATTEMPTS` | No | Per-capability attempts before skipping (default: 2) |
| `REQUEST_TIMEOUT_SECONDS` | No | HTTP request timeout (default: 30) |

---

## Docker Compose Volume Mounts

`docker-compose.yml` mounts three local paths into the container:

| Local path | Container path | Purpose |
|---|---|---|
| `./data/` | `/app/data/` | SQLite database files (gitignored) |
| `./auth_config.yaml` | `/app/auth_config.yaml` | User credentials (gitignored) |
| `./.streamlit/` | `/app/.streamlit/` | Streamlit config |

---

## Database Scripts

All scripts are bash (`.sh`). There are no PowerShell equivalents.

### Pull from production → local

```bash
./db-pull.sh                   # pull both DBs from Fly.io
./db-pull.sh --frameworks      # framework DB only
./db-pull.sh --assessments     # assessment DB only
./db-pull.sh --dry-run         # preview without downloading
```

### Push framework DB to production (normal workflow)

```bash
./db-push.sh --frameworks      # push framework DB (safe)
./db-push.sh --dry-run         # preview without uploading
```

### Push assessment DB (deliberate override only)

```bash
./db-push.sh --assessments     # DESTRUCTIVE — overwrites production data, requires YES confirmation
./db-push.sh --both            # push both DBs (DESTRUCTIVE)
```

---

## Deploy to Fly.io

### One-time setup

```bash
fly auth login
# For a brand new app only:
fly launch           # existing app: fly.toml already configured
```

### Routine deploy

```bash
./deploy.sh                          # git commit + fly deploy + upload framework DB
./deploy.sh "Release v1.3"           # custom commit message
./deploy.sh --skip-db                # code only, skip framework DB upload
./deploy.sh --skip-code              # framework DB upload only, skip git + fly deploy
```

This does three things in sequence:
1. `git add` / `git commit` / `git push` → GitHub
2. `fly deploy` → rebuilds Docker image from latest code
3. SFTP upload → pushes `data/meridant_frameworks.db` to the Fly.io `/data` volume

### Fly.io configuration

- App: `streamlit-mvp`
- Region: `syd` (Sydney)
- Volume: `tmm_data` mounted at `/data`
- VM: 1 shared CPU, 512 MB RAM
- DB paths on volume: `/data/meridant_frameworks.db`, `/data/meridant.db`
- Auth config on volume: `/data/auth_config.yaml`

### First-time volume setup (new Fly machine)

```bash
fly machine start --app streamlit-mvp
fly ssh sftp shell --app streamlit-mvp
put auth_config.yaml /data/auth_config.yaml
exit
./deploy.sh
```

---

## Multi-Machine Dev Workflow

```
Machine A (made framework changes)  →  ./deploy.sh
Machine B (needs to sync)           →  ./db-pull.sh
```

Both machines use Fly.io as the single source of truth for assessment data.

---

## Authentication

Users are defined in `auth_config.yaml` (on the Fly.io `/data` volume in production; in the project root for local dev via Docker Compose volume mount).

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

Admin users get an additional **Admin** nav item for user management. Passwords are bcrypt-hashed in-app via the Admin page — no manual hashing required.

---

## Project Structure

```
streamlit-mvp/
├── app.py                        # entry point — auth, sidebar nav, page routing
├── auth_config.yaml              # user credentials (gitignored, volume-mounted)
├── fly.toml                      # Fly.io config
├── Dockerfile                    # Python 3.12-slim image
├── docker-compose.yml            # local dev: mounts data/, auth_config.yaml, .streamlit/
├── requirements.txt
├── .env                          # local env vars (gitignored)
├── .env.example                  # committed template for all env vars
│
├── src/
│   ├── pages/
│   │   ├── dashboard.py          # interactive framework explorer
│   │   ├── assessments.py        # assessment list + filters + pagination
│   │   ├── create_assessment.py  # 6-step assessment wizard
│   │   ├── architecture.py       # architecture diagram page
│   │   ├── admin_users.py        # user management (admin only)
│   │   ├── simulation.py         # scenario impact simulation (partial)
│   │   └── usecase_workspace.py  # use case management
│   ├── assessment_builder.py     # use-case → capability resolution logic
│   ├── assessment_store.py       # CRUD for assessments, findings, recommendations
│   ├── recommendation_engine.py  # AI-powered gap recommendations
│   ├── question_generator.py     # AI-generated assessment questions
│   ├── ai_client.py              # Anthropic Claude wrapper (all AI calls centralised here)
│   ├── meridant_client.py        # SQLite client (attaches both DBs)
│   ├── sql_templates.py          # reusable query helpers
│   ├── heatmap.py                # maturity heatmap rendering + Excel export
│   └── roadmap.py                # roadmap Gantt rendering + Excel export
│
├── scripts/                      # DB seeding and migration scripts
│   ├── seed_v3_assessments.py    # current seed script — 6 test assessments, idempotent
│   ├── migrate_multi_framework.py# adds Next_Framework registry + framework_id FKs
│   ├── migrate_split_db.py       # one-time migration to split DB (already done)
│   ├── seed_nist_csf2.py         # NIST CSF 2 seed (in development)
│   └── repair_wal.py             # SQLite WAL repair utility
│
├── data/                         # local SQLite files (gitignored)
│   ├── meridant_frameworks.db    # framework IP (local master)
│   └── meridant.db               # assessment data (Fly.io master)
│
├── assets/                       # static files (architecture.png, etc.)
│
├── deploy.sh                     # deploy code + framework DB to production
├── db-pull.sh                    # pull DBs from production to local
├── db-push.sh                    # push DBs to production (use with care)
├── start.sh                      # container startup — materialises .env + auth_config.yaml from secrets
└── setup.sh                      # one-time setup: installs sqlite3, runs seed SQL files
```
