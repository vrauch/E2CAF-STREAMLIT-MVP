# Meridant Matrix — Copilot Instructions

> Streamlit + SQLite capability maturity assessment platform for Meridant consultants.
> Full context lives in [CLAUDE.md](../CLAUDE.md). This file distils what an agent needs for day-to-day coding.

---

## Build & Run

```bash
# ONLY supported runtime — no local venv exists
docker compose up --build          # always --build; restart does NOT pick up code changes
docker compose up --build -d       # detached
docker compose down

# Run a script inside the container
docker compose exec app python scripts/seed_v3_assessments.py

# Pick up auth_config.yaml changes without rebuild
docker compose restart
```

**Never** run `pip install`, `python`, or `streamlit` directly in the host shell.

---

## Architecture

```
app.py                      ← Entry point: auth guard, sidebar nav, page dispatch
src/
  meridant_client.py        ← MeridantClient (SQLite; split-DB via ATTACH DATABASE)
  sql_templates.py          ← ALL reusable SQL helpers (q_* = SELECT, w_* = writes)
  ai_client.py              ← ALL Anthropic API calls (_call_with_retry, DEFAULT_MODEL)
  assessment_store.py       ← Persistence: save/load assessments, findings, recs, narrative
  recommendation_engine.py  ← build_recommendations(): per-capability AI orchestration
  heatmap.py                ← Bootstrap HTML heatmap + Excel export
  roadmap.py                ← Bootstrap HTML Gantt + Excel export
  pages/
    dashboard.py            ← Framework overview
    assessments.py          ← Assessment list (Resume / View / Archive)
    create_assessment.py    ← 6-step assessment wizard (primary workflow)
    admin_users.py          ← User management (admin-only)
    usecase_workspace.py    ← Use case management
data/
  meridant_frameworks.db    ← Framework IP (Next_* tables); local master → Fly.io
  meridant.db               ← Assessment data (Assessment*, Client); Fly.io master
```

Two SQLite databases connected via `ATTACH DATABASE` inside `MeridantClient`.  
Framework tables: `Next_*` prefix. Assessment tables: `Assessment*`, `Client`.

---

## Database Conventions

```python
db = get_client()                          # reads env vars; returns MeridantClient singleton
result = db.query("SELECT ...", [params])  # {"rows": [...], "count": N}
rows = result.get("rows", [])
db.write("INSERT ...", [params])           # {"lastrowid": N, "rowcount": N}
db.write_many("INSERT ...", list_of_tuples)
```

- **Parameterised queries only** — never f-string SQL with any user-supplied value
- SQL helpers belong in `sql_templates.py` (prefix `q_` for reads, `w_` for writes)
- Always filter `Next_CapabilityLevel` with `WHERE level_name IS NOT NULL` (has duplicate rows)
- `Next_UseCaseCapabilityImpact.impact_weight` has `CHECK BETWEEN 1 AND 5`
- **Never touch** legacy tables: `Domain`, `SubDomain`, `Capability`, `CapabilityLevel`, `UseCaseCapabilities`
- Schema migration via inline `ALTER TABLE ... ADD COLUMN` (memoized guard pattern); no migration scripts

---

## AI Call Convention

```python
# All AI calls live in src/ai_client.py — NEVER add `import anthropic` elsewhere
from src.ai_client import get_ai_client, _call_with_retry, DEFAULT_MODEL

client = get_ai_client()
response = _call_with_retry(client, model=DEFAULT_MODEL, max_tokens=N,
                             messages=[{"role": "user", "content": prompt}])
raw = response.content[0].text.strip()
# Strip markdown fences before JSON parsing:
import re, json
raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
data = json.loads(raw)
```

All prompts that return structured data must instruct: *"Return ONLY a JSON …, no preamble, no markdown"*.

---

## UI Convention

- **Bootstrap 5.3 dark** (`data-bs-theme="dark"`) + Chart.js 4.4.3 loaded via CDN
- Fonts: JetBrains Mono + Inter via Google Fonts CDN
- Rich UI components rendered via `st.components.v1.html(html, height=N, scrolling=True)`
- Data injected via `json.dumps()` into `const DATA = {...}` in the HTML blob
- **Never** put `st.button()` / `st.form()` / any Streamlit widget inside an HTML component
- **Never** use `localStorage` or `sessionStorage` inside HTML components

### Brand Palette (key tokens)
| Token | Hex | Usage |
|---|---|---|
| Navy | `#0F2744` | Sidebar bg, dark headers |
| Accent Blue | `#2563EB` | CTAs, links |
| White | `#F9FAFB` | Body bg, text on dark |
| Neutral Dark | `#111827` | Body text |
| Index | `#6366F1` | AI features |
| Insight | `#0EA5E9` | Charts |
| Benchmarks | `#0D9488` | Framework/positive |
| Studio | `#7C3AED` | Config/admin |

---

## Streamlit Conventions

- Use `st.session_state.setdefault("key", default)` before reading any session state key
- Each page module exports a single `render()` function; `app.py` dispatches to it
- Routing is a sidebar `st.radio()` — NOT Streamlit's native multi-page mechanism
- Avoid `st.experimental_*` APIs; use current stable API

---

## Naming & File Conventions

| Do | Don't |
|---|---|
| `meridant_client.py`, `MeridantClient` | `tmm_client.py`, `TMMClient` |
| `MERIDANT_FRAMEWORKS_DB_PATH` env var | `TMM_DB_PATH` |
| "Meridant Matrix" in UI text | any legacy platform name |
| Export: `Meridant_{SubBrand}_{Client}_{Date}.ext` | any legacy filename convention |

Sub-brands: **Meridant Matrix** (platform), **Meridant Index** (assessment engine), **Meridant Insight** (reporting), **Meridant Benchmarks** (framework library), **Meridant Studio** (config).

---

## Guardrails

- No ORM — raw SQL only; no SQLAlchemy, Peewee, etc.
- All Anthropic calls in `ai_client.py`; all SQL helpers in `sql_templates.py`
- Roadmap is NOT persisted to DB (session state only — see ADR-006 in CLAUDE.md)
- `AssessmentRecommendation` is self-creating via `CREATE TABLE IF NOT EXISTS` in `recommendation_engine.py` — do not add it to a migration script
- Auth is `streamlit-authenticator==0.3.3`; admin check via `_auth_config.get("admins", [])`
- Never commit `.env`, `data/*.db`, or `auth_config.yaml`

---

## Environment Variables

```bash
MERIDANT_FRAMEWORKS_DB_PATH=/data/meridant_frameworks.db
MERIDANT_ASSESSMENTS_DB_PATH=/data/meridant.db
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-20250514   # optional override
```
