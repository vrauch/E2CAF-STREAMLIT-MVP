# CLAUDE.md — Meridant Matrix

> Project briefing for Claude Code. Read this at the start of every session.
> Maintained by: Vernon Rauch | Last updated: 2026-03-25

---

## What This Project Is

**Meridant Matrix** is a Streamlit web application backed by a local SQLite database. It is the core platform product of the **Meridant** brand — a multi-framework capability maturity assessment platform built for HPE consultants and designed for future commercial licensing.

The platform currently supports **MMTF** (Meridant Matrix Transformation Framework) as its first loaded framework (rebranded from E2CAF), with the architecture evolving toward pluggable framework support (NIST CSF, CSA CCM, ISO 27001, CMMI and others). MMTF uses three-level terminology: **Pillar / Domain / Capability** (mapped to the DB's `Next_Domain` / `Next_SubDomain` / `Next_Capability` tables respectively, which retain the `Next_*` prefix for now).

The platform supports:
- Predefined and custom use-case-driven assessments
- AI-generated capability discovery, question generation, and findings narrative
- AI-generated transformation roadmap with Gantt visualisation and Excel export
- Per-capability and per-domain gap analysis with maturity heatmap
- Full framework management (capabilities, maturity levels, interdependencies, versioning)

> **Note:** The DB tables still use `Next_*` prefixes and legacy column names internally. The `Next_*` → `Framework_*` table rename and remaining codebase cleanup are still pending (Priority 8.3). The DB split (Priority 8.1), client rename (Priority 8.2 partial), and sync scripts (Priority 8.4) are complete.

---

## Tech Stack

| Layer | Technology |
|---|---|
| UI | Streamlit (multi-page app) |
| Database | SQLite — **split into two files**: `data/meridant_frameworks.db` (framework IP) + `data/meridant.db` (assessment/client data). Paths set via `MERIDANT_FRAMEWORKS_DB_PATH` + `MERIDANT_ASSESSMENTS_DB_PATH` in `.env`. Connected via SQLite `ATTACH DATABASE`. |
| AI | Anthropic API (`claude-sonnet-4-20250514`) via `src/ai_client.py` |
| DB client | `MeridantClient` in `src/meridant_client.py` — no ORM. `get_client()` singleton. Supports split mode (preferred) and legacy single-DB fallback. |
| Environment | `.env` file with `MERIDANT_FRAMEWORKS_DB_PATH`, `MERIDANT_ASSESSMENTS_DB_PATH`, and `ANTHROPIC_API_KEY` |
| Auth | `streamlit-authenticator==0.3.3` — YAML-based credential store (`auth_config.yaml`, bcrypt-hashed passwords, volume-mounted) |
| Python | 3.12 |

---

## Brand Palette

Applied consistently across all UI modules (`dashboard.py`, `roadmap.py`, `heatmap.py`, `app.py`).

| Token | Hex | Usage |
|---|---|---|
| Navy | `#0F2744` | Sidebar bg, primary dark headers |
| Accent Blue | `#2563EB` | CTAs, links, highlights |
| White | `#F9FAFB` | Body bg, text on dark |
| Neutral Dark | `#111827` | Body text |
| Neutral Mid | `#374151` | Secondary text, borders |
| Neutral Light | `#6B7280` | Muted text, metadata |
| Border | `#D1D5DB` | Dividers, table borders |
| Surface | `#F3F4F6` | Alternate row bg |
| Index (sub-brand) | `#6366F1` | AI/Index features |
| Insight (sub-brand) | `#0EA5E9` | Charts, visualisations |
| Benchmarks (sub-brand) | `#0D9488` | Framework/green positive |
| Studio (sub-brand) | `#7C3AED` | Config/admin |

**Domain colours (12 domains, same order in Python `DOMAIN_COLORS` dict and JS arrays):**
`#0F2744`, `#DC2626`, `#7C3AED`, `#2563EB`, `#0D9488`, `#6366F1`, `#0EA5E9`, `#374151`, `#5B21B6`, `#0369A1`, `#047857`, `#9333EA`

---

## Repository Structure

```
/
├── CLAUDE.md                        ← this file
├── app.py                           ← Streamlit entry point (sidebar nav: Dashboard / Assessments / Create Assessment / Architecture / Admin)
├── .env                             ← MERIDANT_FRAMEWORKS_DB_PATH, MERIDANT_ASSESSMENTS_DB_PATH, ANTHROPIC_API_KEY (never commit)
├── .env.example                     ← Committed template for all env vars
├── auth_config.yaml                 ← User credentials (bcrypt hashes) + admins list. Never commit. Volume-mounted into container.
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── fly.toml                         ← Fly.io deployment config
├── deploy.sh                        ← Full deploy: git push + fly deploy + framework DB upload
├── db-push.sh                       ← Upload framework or assessment DB to Fly.io
├── db-pull.sh                       ← Download DBs from Fly.io to local
├── start.sh                         ← Container startup: materialises .env + auth_config.yaml from secrets
├── setup.sh                         ← One-time setup: installs sqlite3, runs seed.sql + seed_frameworks.sql
├── seed.sql                         ← Raw SQL seed for assessment DB
├── seed_frameworks.sql              ← Raw SQL seed for framework DB
├── data/
│   ├── meridant_frameworks.db       ← Framework IP: all Next_* tables (local master → pushed to Fly.io)
│   └── meridant.db                  ← Assessment + client data (Fly.io master → pulled locally for review)
├── assets/
│   └── architecture.png
├── scripts/
│   ├── seed_v3_assessments.py           ← Current seed script — 6 comprehensive assessments, no AI needed
│   ├── seed_v2_assessments.py           ← Earlier seed script (superseded by v3)
│   ├── seed_test_assessments.py         ← Original seed script (legacy, uses AI — do not use)
│   ├── seed_upload_test.py              ← Upload/SFTP test seed
│   ├── seed_nist_csf2.py                ← NIST CSF 2 framework seed script (in development)
│   ├── migrate_multi_framework.py       ← Adds Next_Framework registry table + framework_id FKs + MMTF seed ✅ done
│   ├── migrate_split_db.py              ← One-time migration: e2caf.db → meridant_frameworks.db + meridant.db ✅ done
│   ├── migrate_remove_legacy_branding.py← Removes remaining E2CAF/TMM legacy branding references
│   ├── generate_mmtf_descriptions.py    ← Generates AI descriptions for MMTF capabilities
│   └── repair_wal.py                    ← SQLite WAL repair utility
└── src/
    ├── meridant_client.py           ← SQLite client: MeridantClient (query, write, write_many). get_client() reads env vars.
    │                                   Split mode: opens meridant_frameworks.db, ATTACHes meridant.db as 'assessments'.
    ├── sql_templates.py             ← SQL query/write helper functions (includes get_frameworks())
    ├── ai_client.py                 ← All Anthropic API calls
    ├── assessment_builder.py        ← CapabilityResult dataclass + analyze_use_case_readonly()
    ├── assessment_store.py          ← Persistence: save_assessment, save_findings, save_narrative,
    │                                   save_recommendations, load_recommendations,
    │                                   list_assessments, load_assessment
    ├── question_generator.py        ← generate_questions_for_capability()
    ├── heatmap.py                   ← Maturity heatmap HTML + Excel export
    ├── roadmap.py                   ← Roadmap Gantt HTML + Excel export
    ├── recommendation_engine.py     ← build_recommendations(): DB context assembly + AI orchestration
    ├── report_writer.py             ← Word document export (python-docx): 6-section .docx report ✅ done
    ├── report_presenter.py          ← PowerPoint export (python-pptx): 6-slide .pptx deck ✅ done
    └── pages/
        ├── dashboard.py             ← Framework overview dashboard + version history/change log (Bootstrap 5 light) ✅ 5.1 done
        ├── assessments.py           ← Assessment list: table view with View/Resume/Archive buttons, filters, pagination ✅ done
        ├── assessment_detail.py     ← Assessment detail/view mode: 4 tabs (Exec Summary, Domain Findings, Recs, Export) ✅ done
        ├── create_assessment.py     ← 6-step assessment wizard (primary workflow)
        ├── simulation.py            ← Scenario impact simulation (partial)
        ├── usecase_workspace.py     ← Use case management
        ├── admin_users.py           ← Administration UI: Users tab (add/remove/password) + Clients tab (add/edit/merge) ✅ done
        └── architecture.py          ← Architecture page stub
```

---

## Database

**Files:** Split across two SQLite databases:
- `data/meridant_frameworks.db` — all `Next_*` tables (framework IP, local master). Path via `MERIDANT_FRAMEWORKS_DB_PATH`.
- `data/meridant.db` — all `Assessment*` + `Client` tables (client data, Fly.io master). Path via `MERIDANT_ASSESSMENTS_DB_PATH`.

**Engine:** SQLite with `ATTACH DATABASE` (see `MeridantClient._connect()`)

### Schema Naming Convention
- `Next_*` tables — the MMTF framework model, lives in `meridant_frameworks.db` (active)
- `Assessment*` tables — client assessment data, lives in `meridant.db`
- Legacy tables (`Domain`, `SubDomain`, `Capability`, etc.) — old schema in `meridant_frameworks.db`, do not use
- In split mode, `meridant.db` is attached as schema `assessments` — qualifying with `assessments.Assessment` is valid but not required since table names are unique across both DBs

### Key Framework Tables

| Table | Purpose |
|---|---|
| `Next_Framework` | Framework registry. MMTF is framework_id=1 (framework_key='MMTF', label_level1='Pillar', label_level2='Domain', label_level3='Capability'). Added by `migrate_multi_framework.py`. |
| `Next_Domain` | 12 domains (maps to MMTF "Pillars") |
| `Next_SubDomain` | 59 subdomains (maps to MMTF "Domains") |
| `Next_Capability` | 308 capabilities (IDs 1–319, sparse) |
| `Next_CapabilityLevel` | L1–L5 maturity descriptors per capability. **Always filter `WHERE level_name IS NOT NULL`** — has duplicate rows |
| `Next_MaturityAssessment` | Baseline maturity scores (4 dimensions per capability) |
| `Next_MaturityDimension` | 1=Process, 2=People, 3=Technology, 4=Governance |
| `Next_CapabilityInterdependency` | 482 dependency edges. Types: Foundational/Complementary/Amplifying/Substitutive |
| `Next_CapabilityInteractionType` | 1=Foundational, 2=Complementary, 3=Amplifying, 4=Substitutive |
| `Next_UseCase` | 26 predefined use cases |
| `Next_UseCaseCapabilityImpact` | impact_weight 1–5 (CHECK constraint), maturity_target, feasibility_score |
| `Next_TargetMaturity` | Per-dimension target scores per use case + capability |
| `Next_RoadmapStep` | Framework phase guidance per use case + capability (phase 1–4) |
| `Next_CapabilityInvestmentCost` | Estimated implementation cost per capability |
| `Next_FrameworkVersion` | Version registry (v1.0–v1.3 published) |
| `Next_ChangeRecord` | Audit trail of all framework changes |
| `Next_CapabilityTag` / `Next_CapabilityTagMap` | Tags (cloud, data, security, etc.) |
| `Next_CapabilityCluster` / `Next_CapabilityClusterMap` | 12 clusters |

### Key Assessment Tables

| Table | Purpose |
|---|---|
| `Assessment` | Header: client_id, engagement_name, use_case_name, intent_text, usecase_id, assessment_mode, overall_score, status, created_at, completed_at, **findings_narrative** |
| `AssessmentCapability` | Capabilities selected for assessment with ai_score, rationale, capability_role, target_maturity |
| `AssessmentResponse` | Individual question responses (response_type, score, answer, notes) |
| `AssessmentFinding` | Per-capability and per-domain gap findings (finding_type='capability'\|'domain', avg_score, target_maturity, gap, risk_level, subdomain) |
| `AssessmentRecommendation` | AI-generated gap recommendations. Created via `CREATE TABLE IF NOT EXISTS` on first engine run. **See exact column list below.** |
| `Client` | Client master: client_name, industry, sector, country |

### AssessmentRecommendation — Exact Column List
**Critical:** the live DB schema differs from what you might expect. Always use these exact names:
```
id, assessment_id, capability_id, capability_name, domain, capability_role,
current_score, target_maturity, gap,
priority_tier, effort_estimate,
recommended_actions (JSON TEXT), enabling_dependencies (JSON TEXT), success_indicators (JSON TEXT),
hpe_relevance, narrative, created_at
```
**Not present:** `subdomain`, `recommendation_headline`, `target_score`, `current_state_narrative`, `generated_at`, `model_used`

### Important DB Notes
- `Next_CapabilityLevel` has duplicate rows — **always filter `WHERE level_name IS NOT NULL`**
- `Next_UseCaseCapabilityImpact.impact_weight` has `CHECK BETWEEN 1 AND 5`
- `Next_CapabilityTagMap` and `Next_CapabilityClusterMap` require explicit `id` on INSERT
- `Assessment.usecase_id`, `assessment_mode`, and `findings_narrative` were added via ALTER TABLE; `_ensure_narrative_column()` in `assessment_store.py` handles the migration inline
- `Assessment.framework_id` was added via `migrate_multi_framework.py` (DEFAULT 1 = MMTF)
- `Assessment.consultant_name` was added via `_ensure_consultant_column()` in `assessment_store.py`
- `Next_Framework` content tables (`Next_Domain`, `Next_SubDomain`, etc.) now have a `framework_id` column (DEFAULT 1) added by `migrate_multi_framework.py`
- `AssessmentRecommendation` is created inline (`CREATE TABLE IF NOT EXISTS`) by `recommendation_engine.py` on first run — no manual migration needed
- Roadmap is NOT persisted to the DB — held in session state only (`roadmap_data`)
- WAL mode is intentionally disabled (not supported on Windows Docker bind mounts)

---

## Framework State (v1.3 — current)

**319 capability IDs, 308 populated** across 12 domains and 59 subdomains.

| Domain | ID | Caps | Notes |
|---|---|---|---|
| Strategy & Governance | 1 | 29 | |
| Security | 2 | 56 | Includes AI Security (307), ZTNA (306), Supply Chain Security (305) |
| People | 3 | 24 | |
| Applications | 4 | 36 | Includes Technical Debt Management (308) |
| Data | 5 | 37 | |
| DevOps | 6 | 30 | |
| Innovation | 7 | 36 | Includes Digital Twin (310) |
| Operations | 8 | 37 | |
| AI & Cognitive Systems | 9 | 14 | Expanded in v1.3 — 5 subdomains |
| Intelligent Automation & Operations | 10 | 3 | |
| Sustainability & Responsible Technology | 11 | 3 | |
| Experience & Ecosystem Enablement | 12 | 3 | |

**Version history:**
- v1.0 (2026-01-23) — E2CAF Next Baseline, 303 capabilities
- v1.1 (2026-03-07) — FinOps & Cloud Economics (cap 304)
- v1.2 (2026-03-07) — 6 gap capabilities added (305–310)
- v1.3 (2026-03-07) — AI & Cognitive Systems expanded (311–319, new subdomain id=59)

---

## Application Architecture

### Multi-Page Streamlit App
All pages live in `src/pages/`. Routing is a sidebar radio in `app.py` (not Streamlit's native multi-page mechanism).

**Sidebar nav order:** Dashboard → Assessments → Create Assessment → Architecture → Admin (admin-only)

**Cross-page navigation:** When `assessments.py` resumes an assessment it sets `st.session_state["_navigate_to"] = "Create Assessment"` and calls `st.rerun()`. `app.py` pops `_navigate_to` before the radio renders and presets `_sidebar_nav` to the target page.

**`AUTH_CONFIG_PATH` env var:** `app.py` reads auth config from this path if set (used on Fly.io to point to `/data/auth_config.yaml` on the persistent volume). Falls back to project root for local Docker dev.

### UI Convention
- **Bootstrap 5.3 dark** (`data-bs-theme="dark"`) loaded via CDN
- **Fonts:** JetBrains Mono + Inter via Google Fonts CDN
- **Charts:** Chart.js 4.4.3 via CDN
- All rich HTML components rendered via `st.components.v1.html(html, height=N, scrolling=True)`
- Data injected into HTML via `json.dumps()` into `const DATA = {...}` inside the HTML blob
- **Never** put Streamlit widgets inside HTML components — only `st.button()` / `st.form()` outside

### AI Call Pattern (`src/ai_client.py`)
```python
# All AI functions follow this pattern:
client = get_ai_client()           # singleton Anthropic client
response = _call_with_retry(       # exponential backoff on 529 overload
    client,
    model=DEFAULT_MODEL,           # claude-sonnet-4-20250514 (set via ANTHROPIC_MODEL env)
    max_tokens=N,
    messages=[{"role": "user", "content": prompt}],
)
raw = response.content[0].text.strip()
# Strip markdown fences before JSON parsing
```

All AI functions that return structured data:
- Prompt explicitly instructs "Return ONLY a JSON array/object with no preamble, no markdown"
- Strip ` ```json ` fences before `json.loads()`

### DB Query Pattern (`src/meridant_client.py`)
```python
db = get_client()                          # reads MERIDANT_FRAMEWORKS_DB_PATH + MERIDANT_ASSESSMENTS_DB_PATH from .env
                                           # (falls back to TMM_DB_PATH for legacy single-DB mode)
result = db.query("SELECT ...", [params])  # returns {"rows": [...], "count": N}
rows = result.get("rows", [])
db.write("INSERT ...", [params])           # returns {"lastrowid": N, "rowcount": N}
db.write_many("INSERT ...", list_of_tuples)
```

---

## Assessment Wizard (`src/pages/create_assessment.py`)

The primary workflow. Steps tracked via `st.session_state.wizard_step`.

| Step | Key | Description |
|---|---|---|
| 1 | `1` | Client context + use case intent. Mode toggle: predefined UC or custom |
| 2 | `2` | AI capability discovery (custom mode only — skipped for predefined) |
| 2b | `"2b"` | Domain target-setting (maturity targets per domain, L1–L5) |
| 3 | `3` | Question style selection + AI question generation + review |
| 4 | `4` | Response capture (online or offline; maturity 1–5 / yes-no-evidence / free text) |
| 5 | `5` | Findings: domain/capability scores, maturity heatmap, AI executive narrative, gap table, export |
| 5b | `"5b"` | Gap recommendations: AI per-capability recommendations with P1/P2/P3 priority, actions, dependencies, success indicators. Optional — can be skipped or run later |
| 6 | `6` | Transformation roadmap — AI-generated Gantt with Excel export. Uses Step 5b recommendations when available to structure phases; falls back to scores-only when skipped |

### Session State Keys
```
wizard_step, use_case_name, intent_text, client_name, engagement_name,
client_industry, client_sector, client_country,
assessment_mode ('predefined'/'custom'), selected_usecase_id (int|None),
core_caps, upstream_caps, downstream_caps, domains_covered,
domain_targets, questions, responses, findings_narrative,
assessment_id, findings_saved, responses_ai_scored,
confirm_regen_narrative,          ← bool: True while confirm dialog is shown for narrative regen
confirm_regen_recs,               ← bool: True while confirm dialog is shown for rec regen
recommendations (list|None),
roadmap_data (dict|None), roadmap_timeline_unit, roadmap_horizon_months, roadmap_scope
```

### Predefined Use Case Flow
- Step 1 mode = 'predefined' → skips Step 2 entirely → goes directly to Step 2b
- `_load_predefined_usecases()` → queries `Next_UseCase`
- `_load_predefined_capabilities()` → queries `Next_UseCaseCapabilityImpact`, maps impact_weight to role
- Intent text pre-filled from framework description + business_value, editable by consultant

### Response Scoring (Step 5 pre-processing)
All response types are normalised to numeric 1–5 before Step 5 renders (flagged by `responses_ai_scored`):
- `maturity_1_5`: score already stored numerically — no action needed
- `yes_no_evidence`: mapped via fixed dict (Yes=3, Partial=2, No=1)
- `free_text`: batched to `score_free_text_responses()` in `ai_client.py` → Claude scores 1–5

---

## Key AI Functions (`src/ai_client.py`)

| Function | Purpose | Output |
|---|---|---|
| `rank_capabilities_by_intent()` | Ranks candidate capabilities by relevance to intent | JSON array with ai_score + rationale |
| `generate_findings_narrative(client_name, client_industry, client_country, client_stated_context, ...)` | Executive summary of assessment findings, grounded in client context | Plain text, 3–4 paragraphs |
| `score_free_text_responses()` | Scores free-text responses 1–5 using maturity rubric | Same list with score + rationale added |
| `generate_gap_recommendations(client_country, client_stated_context, ...)` | Per-capability gap recommendation grounded in level descriptors, actual responses, and dependency context | JSON dict with recommended_actions, enabling_dependencies, success_indicators, narrative |
| `generate_roadmap_plan(client_name, client_industry, client_country, client_stated_context, ...)` | Structured gap-closure roadmap (phases → initiatives). Accepts optional `recommendations` list to structure phases by P1/P2/P3 tier | JSON dict (see schema below) |

`generate_questions_for_capability()` lives in **`src/question_generator.py`**, not ai_client.py.

### AI Grounding Rules (all client-facing functions)
All three client-facing AI functions (`generate_findings_narrative`, `generate_gap_recommendations`, `generate_roadmap_plan`) include:
1. **CLIENT-STATED CONTEXT block** — verbatim answer/notes text extracted from assessment responses, injected into the prompt so the AI grounds recommendations in what the client actually said
2. **Technology grounding rule** — hard prohibition: do NOT name specific vendors, cloud providers, platforms, or products unless that exact name appears verbatim in the CLIENT-STATED CONTEXT
3. **Industry + country context** — client_industry and client_country passed to all three functions for market-appropriate framing

`_build_client_stated_context(responses: dict) -> str` is a module-level helper in `create_assessment.py` that deduplicates and formats response answer/notes for injection.

### Roadmap JSON Schema (from `generate_roadmap_plan()`)
```json
{
  "total_weeks": int,
  "phases": [
    {
      "id": "P1", "name": str, "start_week": int, "end_week": int,
      "rationale": str, "story": str, "description": str,
      "activities": [str],
      "initiatives": [
        {
          "id": str, "name": str, "domain": str, "capability_names": [str],
          "priority": "Critical|High|Medium|Low",
          "current_score": float, "target_score": float, "gap": float,
          "start_week": int, "end_week": int, "prerequisites": [],
          "outcome": str
        }
      ]
    }
  ],
  "critical_path": [str],
  "quick_wins": [str]
}
```

---

## Recommendation Engine (`src/recommendation_engine.py`)

### `build_recommendations(db, assessment_id, cap_scores, client_industry, intent_text, usecase_id, max_caps, on_progress, client_country)`
For each gap capability (gap > 0, sorted by gap desc, Core first, capped at `max_caps`):
1. Determines `priority_tier` (P1/P2/P3) and `effort_estimate` deterministically before the AI call
2. Loads from DB: `Next_CapabilityLevel` L(current) and L(target) descriptors (`capability_state` + `key_indicators`), `AssessmentResponse` for this capability, Foundational dependencies from `Next_CapabilityInterdependency` (interaction_type_id=1), `Next_RoadmapStep` framework phase if `usecase_id` provided
3. Calls `generate_gap_recommendations()` with full context
4. Failures on individual capabilities produce a placeholder and continue — run does not abort
5. Returns results sorted P1 → P2 → P3, then gap desc within tier

**Priority tier logic:**
- P1: `framework_phase == 1` OR `gap >= 2.0` OR (`role == 'Core'` AND `gap >= 1.5`)
- P2: `gap >= 1.0`
- P3: `gap < 1.0`

**Table creation:** `CREATE TABLE IF NOT EXISTS AssessmentRecommendation` runs on every call but is a no-op after first creation.

## Heatmap Module (`src/heatmap.py`)

| Function | Purpose |
|---|---|
| `render_heatmap_html(dom_scores)` | Bootstrap 5 HTML table — domain × maturity level (L1–L5) with colour coding |
| `generate_heatmap_excel(dom_scores, client_name, engagement_name, use_case_name)` | XLSX bytes with formatted heatmap + legend |

**Per-level score formula:** `level_score(L) = max(0, min(1, avg_score - (L - 1)))`
- Green (#B7E2CD) = 1.0 (level fully achieved)
- Amber (#FDE9B2) = 0–1 (partial)
- White = 0 (not achieved)

`DOMAIN_COLORS` dict in `heatmap.py` holds the 12 brand colours used across heatmap and Gantt.

---

## Roadmap Module (`src/roadmap.py`)

| Function | Purpose |
|---|---|
| `render_roadmap_gantt_html(roadmap, timeline_unit)` | Bootstrap 5 Gantt — phases, initiatives, quick wins, critical path |
| `generate_roadmap_excel(roadmap, client_name, engagement_name, use_case_name)` | 3-sheet XLSX: Initiatives / Phase Narratives / Critical Path |
| `TIMELINE_UNITS` | List of valid timeline unit strings |

Timeline units: `"Weeks"`, `"Sprints (2 wks)"`, `"Quarters (13 wks)"`
Priority badge colours: Critical=#DC2626, High=#EA580C, Medium=#D97706, Low=#16A34A

---

## Persistence (`src/assessment_store.py`)

| Function | Table(s) | Notes |
|---|---|---|
| `save_assessment()` | `Client`, `Assessment`, `AssessmentCapability`, `AssessmentResponse` | Creates records; returns assessment_id |
| `save_findings()` | `Assessment` (UPDATE), `AssessmentFinding` (INSERT) | Updates overall_score + status; calls `_ensure_narrative_column()` inline |
| `save_narrative(client, assessment_id, narrative)` | `Assessment` (UPDATE) | Persists executive summary to `findings_narrative` column; calls `_ensure_narrative_column()` |
| `save_recommendations()` | `AssessmentRecommendation` | Idempotent — DELETE then INSERT; JSON-encodes list fields; uses actual DB column names |
| `load_recommendations()` | `AssessmentRecommendation` | JSON-decodes list fields; ensures `narrative` key is always set; returns [] if none exist |
| `list_assessments()` | `Assessment`, `Client` | Returns all assessments newest-first |
| `load_assessment()` | `Assessment`, `AssessmentCapability`, `AssessmentResponse` | Returns dict with assessment/capabilities/responses |

**Column mapping for `save_recommendations()` (in-memory → DB):**
- `r["narrative"]` → `narrative` column
- `r["target_maturity"]` → `target_maturity` column
- Timestamp → `created_at` column
- `hpe_relevance` written as NULL (field removed from AI output)

**Note:** Roadmap is generated in-session and is NOT persisted to the database.

---

## Current State

### Assessment Wizard — All Steps Complete ✅

| Step | Status |
|---|---|
| 1 — Client context + use case intent | ✅ Complete |
| 2 — AI capability discovery (custom) | ✅ Complete |
| 2b — Domain target-setting | ✅ Complete |
| 3 — Question generation + review | ✅ Complete |
| 4 — Response capture | ✅ Complete |
| 5 — Findings + heatmap + AI narrative | ✅ Complete |
| 5b — Gap recommendations (per-capability, AI-grounded) | ✅ Complete |
| 6 — Transformation roadmap (Gantt + Excel) | ✅ Complete |

**Step 5 — Findings & Narrative:**
- Executive summary narrative is generated by `generate_findings_narrative()` and persisted to `Assessment.findings_narrative` via `save_narrative()`
- On reload, `_hydrate_session_from_db()` restores `findings_narrative` from DB into session state
- Regenerate button shows confirm-before-overwrite dialog (`confirm_regen_narrative` flag in session state); user must click "Yes, regenerate" to proceed
- `client_name`, `client_industry`, `client_country`, and `_build_client_stated_context()` are all passed to `generate_findings_narrative()`

**Step 5b implementation:**
- Optional step — accessible via "Generate Recommendations →" from Step 5; can also be skipped
- **Priority scope selector**: radio — "All priorities" / "P1 only" / "P1 + P2" — pre-filters caps before AI calls using `_preview_tier()` helper (mirrors engine logic)
- **Cap count slider**: 1 to `eligible_count`, default `min(eligible_count, 20)`; Generate disabled when 0
- `build_recommendations()` in `recommendation_engine.py` orchestrates per-capability AI calls
- Priority tier (P1/P2/P3) determined deterministically before AI call; effort_estimate derived from gap size
- Each capability's AI call receives: L(current) and L(target) descriptors, actual scored responses + notes, Foundational dependency chain, framework phase from `Next_RoadmapStep`, client_country
- Progress callback shows which capability is being analysed
- Results cached in `st.session_state.recommendations`; persisted to `AssessmentRecommendation` via `save_recommendations()`
- On reload, loaded from DB via `load_recommendations()` if session is empty
- UI: expandable cards (P1 expanded by default), priority filter, CSV + JSON export
- Regenerate button shows confirm-before-overwrite dialog (`confirm_regen_recs` flag); user must confirm

**Step 6 implementation:**
- Detects whether `st.session_state.recommendations` is populated
- If recommendations present: passes them to `generate_roadmap_plan(recommendations=...)` → AI uses P1/P2/P3 tiers to assign phases and uses recommended actions for initiative content
- If no recommendations (skipped): falls back to scores-only roadmap (original behaviour)
- User selects timeline unit, horizon (months), scope (Core / Core+Upstream / All)
- `client_name`, `client_industry`, `client_country`, and `_build_client_stated_context()` are all passed to `generate_roadmap_plan()`
- Export via `generate_roadmap_excel()` → 3-sheet XLSX download

### Test Assessments in DB (`scripts/seed_v3_assessments.py`)

Run with: `docker compose exec app python scripts/seed_v3_assessments.py`
Idempotent — skips any assessment whose client_name + use_case_name already exists.
Pass `--clean` to first remove the six seeded clients by name before re-inserting (useful when re-seeding from scratch).

| ID | Client | Country | Use Case | Q-Type | Domains | Caps | Responses |
|---|---|---|---|---|---|---|---|
| 21 | Deutsche Bank AG | Germany | General IT Readiness (UC 31) | `maturity_1_5` | 9 | 53 | 159 |
| 22 | Ramsay Health Care | Australia | General IT Readiness (UC 31) | `yes_no_evidence` | 9 | 53 | 159 |
| 23 | Siemens AG | Germany | Operating Model Modernization (UC 27) | `maturity_1_5` | 7 | 55 | 165 |
| 24 | Qatar National Bank | Qatar | AI Readiness (UC 30) | **mixed** (all 3 types) | 8 | 38 | 114 |
| 25 | Norsk Hydro ASA | Norway | General IT Readiness (UC 31) | `free_text` | 9 | 53 | 159 |
| 26 | Singapore Airlines | Singapore | Datacenter Transformation (UC 32) | `maturity_1_5` | 6 | 30 | 90 |

Each assessment has: 3 questions per capability, 8 gap recommendations, executive summary narrative, domain findings + capability findings rows.

**Use case domain coverage:**
- UC 31 (General IT Readiness): 9 domains × 6 caps — Strategy & Governance, Security, People, Applications, Data, DevOps, Innovation, Operations, AI & Cognitive Systems
- UC 27 (Operating Model): 7 domains, all caps (Strategy & Governance=16, People=17, Applications=11, Security=5, DevOps=3, Operations=2, AI=1)
- UC 30 (AI Readiness): 8 domains, all caps (AI & Cognitive Systems=10, Data=12, People=7, Security=5, + 4 others)
- UC 32 (Datacenter Transformation): 6 domains, all caps (Security=18, Applications=4, Data=3, People=3, + 2 others)

### Pending Work
- `src/pages/simulation.py` — impact heatmap (domain × capability grid). `Next_ScenarioImpactCapability` is empty; `Next_ScenarioCapabilityChange` has data
- `Next_ValueTheme` table is empty — value theme assignment for roadmap steps not yet implemented
- Roadmap persistence to DB (currently session-only)
- **Priority 8.3** — `Next_*` → `Framework_*` table rename (highest-effort part of Priority 8, still pending)

### Completed Since Last CLAUDE.md Update (2026-03-13 → 2026-03-25)
- **Priority 2.1 ✅** — `src/pages/assessments.py` live: table view, framework/status/text filters, pagination (15/page), Resume/Open buttons
- **Priority 2.2 ✅** — Resume assessment: `_hydrate_and_redirect()` in `assessments.py` clears stale session state, calls `_hydrate_session_from_db()`, loads recommendations, navigates to wizard at correct step
- **Priority 2.3 ✅** — Assessment status management: `update_assessment_status()` in `assessment_store.py`; split action buttons in `assessments.py` (View + Resume/Archive); Archived badge + filter; confirm-before-archive pattern; `load_findings()` helper added
- **Priority 2.4 ✅** — Assessment detail page: `src/pages/assessment_detail.py` — 4 tabs (Executive Summary, Domain Findings, Recommendations, Export); routed via `_HIDDEN_PAGES` in `app.py`; loads narrative, findings, recommendations from DB
- **Priority 3.1 ✅** — Client management tab in Admin: `_render_clients_tab()` in `admin_users.py`; list with inline edit + merge + add client; `get_clients_with_count`, `update_client`, `merge_clients` helpers in `sql_templates.py`
- **Priority 4.1 ✅** — Word document export: `src/report_writer.py` — 6 sections (cover, exec summary, domain findings, cap gap analysis, recommendations, appendix) using `python-docx`; integrated in Step 6 export panel + assessment detail Export tab
- **Priority 4.2 ✅** — PowerPoint export: `src/report_presenter.py` — 6 slides (cover, exec summary, heatmap, top gaps, roadmap, next steps) using `python-pptx`; integrated in Step 6 + assessment detail
- **Priority 5.1 ✅** — Framework version history + change log in dashboard: `load_framework_versions()` + `load_change_records()` loaders; version chip, version history table, change log table rendered below domain grid; shown for MMTF (4 versions, 38 change records), note shown for other frameworks
- **NIST CSF 2.0 ✅** — Full framework seeded via `scripts/seed_nist_csf2.py`: 106 subcategories across 6 functions and 22 categories; NIST display name fix in `_load_predefined_capabilities` and `analyze_use_case_readonly` (SQLite GLOB pattern to substitute category names for ID codes); 3 NIST use cases seeded
- **FinOps Foundation ✅** — Full framework seeded via `scripts/seed_finops_framework.py`: domains, capabilities, use cases; `--use-cases-only` flag added; 3 FinOps use cases seeded
- **Priority 8.1 ✅** — DB split complete: `scripts/migrate_split_db.py` copied `Next_*` → `meridant_frameworks.db`, `Assessment*/Client` → `meridant.db`
- **Priority 8.2 ✅ (partial)** — `tmm_client.py` → `meridant_client.py`, `TMMClient` → `MeridantClient`; `.env` vars updated to `MERIDANT_FRAMEWORKS_DB_PATH` + `MERIDANT_ASSESSMENTS_DB_PATH`; remaining rename tasks (page titles, export filenames) are still pending
- **Priority 8.4 ✅** — Sync scripts in place: `deploy.sh`, `db-push.sh`, `db-pull.sh` committed. `deploy.sh` does full deploy (git + fly deploy + framework DB upload) with `--skip-db` / `--skip-code` flags. `db-push.sh` supports `--frameworks`/`--assessments`/`--both`/`--dry-run` with destructive confirmation for assessment DB.
- **Multi-framework foundation ✅** — `scripts/migrate_multi_framework.py`: added `Next_Framework` registry, seeded MMTF (framework_id=1, labels Pillar/Domain/Capability), added `framework_id` FK to all content tables and `Assessment`

---

## Coding Conventions

### Never Do
- Do not use an ORM — all SQL is written directly in `sql_templates.py` or inline in page/engine files
- Do not put Streamlit widgets inside `st.components.v1.html()` components
- Do not use `localStorage` or `sessionStorage` in any HTML component
- Do not modify the legacy schema tables (`Domain`, `SubDomain`, `Capability`, `CapabilityLevel`, `UseCaseCapabilities`)
- Do not use `st.experimental_*` APIs — use current Streamlit stable API
- Do not import from `src.tmm_client` — use `src.meridant_client` (`get_client()`, `MeridantClient`)
- Do not use `TMM_DB_PATH` env var in new code — use `MERIDANT_FRAMEWORKS_DB_PATH` / `MERIDANT_ASSESSMENTS_DB_PATH`

### Always Do
- Filter `Next_CapabilityLevel` with `WHERE level_name IS NOT NULL`
- Use `json.dumps()` / `json.loads()` for all structured data stored in TEXT columns
- Use `_call_with_retry()` for all Anthropic API calls
- Strip markdown fences before parsing JSON from AI responses
- Keep AI prompts in `ai_client.py` — not in page files
- Keep DB query helpers in `sql_templates.py` — not in page files
- Use `st.session_state.setdefault()` before reading session state keys

### SQL Conventions
- Always use `Next_` prefix tables for framework data
- Parameterised queries only — never f-string SQL with user input
- Multi-row inserts via `write_many()` with `executemany`
- Always check for `CHECK` constraints — `impact_weight BETWEEN 1 AND 5`

---

## Environment Setup

**The app runs exclusively in Docker. There is no local `.venv`.** All dependencies are installed inside the container image defined by `Dockerfile`.

```bash
# .env (never commit) — lives at project root, mounted into container
MERIDANT_FRAMEWORKS_DB_PATH=/app/data/meridant_frameworks.db   # container-internal path
MERIDANT_ASSESSMENTS_DB_PATH=/app/data/meridant.db             # container-internal path
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-20250514   # optional override

# Run the app (only supported method)
docker compose up --build            # ALWAYS use --build — code changes are not picked up otherwise
docker compose up --build -d         # detached mode

# Add/remove users without rebuild:
# Edit auth_config.yaml (passwords are bcrypt-hashed via Admin page in-app)
# then: docker compose restart       ← picks up YAML changes without --build

# Stop
docker compose down

# Run seed scripts inside container
docker compose exec app python scripts/seed_v3_assessments.py          # idempotent
docker compose exec app python scripts/seed_v3_assessments.py --clean  # remove + re-seed
docker compose exec app python scripts/migrate_multi_framework.py       # idempotent — safe to re-run

# Deploy to Fly.io
./deploy.sh                    # git commit + push + fly deploy + push framework DB
./deploy.sh --skip-db          # code only (no DB upload)
./deploy.sh --skip-code        # DB upload only, skip git + fly deploy
./db-push.sh --frameworks      # push framework DB only (safe, no deploy)
./db-pull.sh                   # pull both DBs from Fly.io to local
```

**Important:** `docker compose restart` does NOT pick up code changes — it reuses the cached image. Always use `docker compose up --build`.

The `.claude/launch.json` "Docker Compose" config is the correct launch configuration. The "Streamlit (local)" config will fail — there is no local Python environment with dependencies installed.

---

## Active Client Engagements (for context)

| Client | Engagement | Notes |
|---|---|---|
| Viennalife | Private cloud modernisation | 4 RFP streams (WP1–WP4); WP5 removed in v0.2 |
| UBS | VMware Modernisation (VME) | VMware exit planning |
| Massey University (UoO) | Edge-to-Cloud adoption | HERM–E2CAF crosswalk produced; assessment id=2 in DB |
| Salam Monetization Services | Monetisation platform | |
| Dubai Police | SRI regulation posture assessment | |

---

## Key People

| Name | Role | Relevance |
|---|---|---|
| Vernon Rauch | Senior Hybrid Cloud Business Consultant & Chief Technologist, HPE CPS/A&PS | Project owner |

---

## Session Handoff Protocol

At the end of a productive session, create or update `docs/session_notes.md` with:
1. What was completed this session (files changed, DB changes made)
2. What is in progress / partially done
3. Exact next action to take at the start of the next session
4. Any decisions made that should be reflected back into this CLAUDE.md

---

*This file is the source of truth for Claude Code context. Keep it current.*

---

## Roadmap & Planned Features

Features are grouped by theme and sequenced by priority. Within each group, items are ordered — build top-to-bottom unless there is a dependency reason to reorder.

### Priority 1 — Access Control & Authentication

> Goal: Make the app safe to hand to another consultant without exposing client data or API keys.

**1.1 — Login screen via `streamlit-authenticator`** ✅ COMPLETE
- `streamlit-authenticator==0.3.3` added to `requirements.txt`
- `auth_config.yaml` at project root: bcrypt-hashed passwords, usernames, display names, session expiry, `admins` list. Volume-mounted (not `:ro`) so changes picked up on `docker compose restart`.
- `app.py` wrapped — all pages require authenticated session before rendering
- `authenticated_username` captured into `st.session_state` for attribution (Priority 1.2)
- `admins` list in `auth_config.yaml` controls which users see the Admin nav item

**1.1b — User admin page** ✅ COMPLETE
- `src/pages/admin_users.py` — admin-only page (visible only to users in `admins` list)
- Features: current user list with role badges, add user form (bcrypt hashes in-app), remove user (with confirm + last-admin protection), change password
- Writes directly to `auth_config.yaml` — new users can log in immediately, no restart required

**1.2 — Consultant attribution on Assessment** ✅ COMPLETE
- `_ensure_consultant_column()` in `assessment_store.py` — inline `ALTER TABLE Assessment ADD COLUMN consultant_name TEXT` (memoized, no-op if column exists)
- `save_assessment()` writes `session.get("authenticated_username", "")` into the column at creation
- `list_assessments()` returns `COALESCE(a.consultant_name, '')` — column in SELECT
- Step 1 assessment picker (`_fmt_assessment()` in `create_assessment.py`) appends consultant to the label suffix when non-empty
- Column already live in DB; existing assessments show NULL (pre-auth — expected)

**1.3 — Secrets hygiene audit** ✅ COMPLETE
- `.env` in `.gitignore` ✓ (line 3)
- `data/*.db` in `.gitignore` ✓ (line 11 — covers e2caf.db, meridant.db, meridant_frameworks.db)
- `auth_config.yaml` in `.gitignore` ✓ (line 13)
- `.env.example` committed to repo — documents all current vars: `MERIDANT_FRAMEWORKS_DB_PATH`, `MERIDANT_ASSESSMENTS_DB_PATH`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `REQUEST_TIMEOUT_SECONDS`; includes legacy `TMM_DB_PATH` as a commented fallback; includes Fly.io deployment notes

---

### Priority 2 — Assessment Management

> Goal: Transform the app from a one-shot creation tool into a persistent engagement record that consultants can return to.

**2.1 — Assessment list page (`src/pages/assessments.py`)** ✅ COMPLETE
- Page added to sidebar nav between Dashboard and Create Assessment
- Table view: ID, client, engagement, use case, framework, status badge, score, created date
- Filters: Framework (from `Next_Framework` registry), Status, free-text search (client or engagement)
- Pagination: 15 rows per page
- Action buttons: "Resume →" (primary, In Progress) or "Open →" (secondary, Complete)

**2.2 — Resume assessment** ✅ COMPLETE
- `_hydrate_and_redirect()` in `assessments.py`: clears stale wizard session keys, calls `_hydrate_session_from_db()`, loads recommendations from DB, sets `_navigate_to = "Create Assessment"`, calls `st.rerun()`
- Wizard resumes at the step determined by DB state (findings? recommendations? etc.)

**2.3 — Assessment status management**
- Add `status` column transitions: `in_progress` → `complete` → `archived`
- "Mark Complete" button at end of Step 6 (after export)
- "Archive" soft-deletes from default list view (sets status='archived'); archived assessments accessible via filter toggle
- No hard deletes — data is always retained

**2.4 — Assessment detail / view mode**
- Read-only view of a completed assessment (findings, recommendations, roadmap) without re-entering the wizard
- Accessible from assessment list "View" action
- Renders the same Bootstrap HTML components as the wizard steps but with no edit controls

---

### Priority 3 — Client Management

> Goal: Clean up the `Client` table and give consultants control over client records without needing a DB tool.

**3.1 — Client management panel (tab within admin page or standalone page)**
- List all clients: name, industry, sector, country, assessment count
- Add new client form
- Edit existing client (name, industry, sector, country, notes)
- Merge duplicates: select two client records → reassign all assessments to the surviving record → delete the duplicate
- Implementation note: `Client` table is simple; no foreign key cascade issues beyond `Assessment.client_id`

---

### Priority 4 — Full Report Export

> Goal: Produce a single client-ready deliverable from a completed assessment.

**4.1 — Word document export (`src/report_writer.py`)**
- New module using `python-docx`
- Sections: Cover page (client, engagement, consultant, date), Executive Summary (from `Assessment.findings_narrative`), Domain Findings (heatmap summary table), Capability Gap Analysis (from `AssessmentFinding`), Recommendations (from `AssessmentRecommendation` — P1/P2/P3 grouped), Transformation Roadmap (phase summary + Gantt reference), Appendix (capability list with scores)
- Triggered from assessment detail view and Step 6 export panel
- Filename convention: `Meridant_Insight_{ClientName}_{Date}.docx`
- Add `python-docx` to `requirements.txt` and rebuild image

**4.2 — Executive Readout presentation (`src/report_presenter.py`)**
- Consulting-grade PowerPoint deck for client-facing delivery, generated from a completed assessment
- Use `python-pptx`
- Slide structure (proposed):
  1. Cover — client name, engagement, consultant, date, Meridant Insight branding
  2. Executive Summary — `Assessment.findings_narrative` as speaker notes + key stats (domains assessed, capability count, overall maturity score)
  3. Maturity Heatmap — rendered as a formatted table slide (domain × L1–L5)
  4. Top Gaps — P1 recommendations summary (capability, current score, target, gap)
  5. Transformation Roadmap — phase timeline (Gantt-style table or visual)
  6. Next Steps — editable placeholder slide for consultant to customise
- Add `python-pptx` to `requirements.txt` and rebuild image
- Filename convention: `Meridant_Insight_{ClientName}_{Date}.pptx`
- Triggered from Step 6 export panel and (once built) assessment detail view

---

### Priority 5 — Framework Admin Panel

> Goal: Give Vernon (and eventually other framework owners) visibility into the E2CAF framework state from within the app.

**5.1 — Framework overview tab (within Dashboard or new page)**
- Current published version + release date + version label (from `Next_FrameworkVersion`)
- Capability count by domain (table + bar chart)
- Change history log: last 20 entries from `Next_ChangeRecord` — table with change_category, change_type, record_label, rationale, changed_on
- Interdependency count and interaction type breakdown

**5.2 — Seed / reset controls (admin-only, protected by auth)**
- "Re-seed test assessments" button — runs `seed_v3_assessments.py` logic inline (idempotent)
- "Clear test data" button — removes the 6 seeded clients and their assessments (requires confirm dialog)
- DB health check panel — row counts for all key tables, confirms schema columns present

---

### Priority 6 — Roadmap Persistence

> Goal: Persist generated roadmaps to the DB so they survive session expiry and can be reloaded.

**6.1 — `AssessmentRoadmap` table**
- Currently roadmap is session-state only (`roadmap_data`). Add `AssessmentRoadmap` table to DB.
- Schema: `id, assessment_id, phase, phase_label, initiative_title, capability_ids (JSON), effort, timeline_start, timeline_end, phase_narrative, generated_at`
- `save_roadmap()` in `assessment_store.py` — idempotent (DELETE + INSERT pattern, consistent with `save_recommendations()`)
- `load_roadmap()` in `assessment_store.py` — restores `roadmap_data` from DB on session hydration
- Tie into `_hydrate_session_from_db()` alongside existing narrative and recommendations reload

---

### Priority 7 — Simulation Page

> Goal: Complete the partially-built `src/pages/simulation.py` impact heatmap.

**7.1 — Scenario impact simulation**
- Domain × capability maturity grid showing current vs target delta
- Source data: `Next_ScenarioCapabilityChange` (has data); `Next_ScenarioImpactCapability` (currently empty — populate or derive from assessment data)
- Scenario selector: choose from `Next_TransformationScenario` or derive from a completed assessment
- Heatmap colour: red (gap ≥ 2) → amber (gap = 1) → green (at or above target)
- Export: Excel snapshot of the heatmap grid

---

### Priority 8 — Database Split, Rename & Sync Strategy

> Goal: Separate framework data from assessment data, rename all DB files and references to align with the Meridant brand, and establish a reliable local ↔ Fly.io sync workflow.

**8.1 — Split the single DB into two purpose-specific databases** ✅ COMPLETE

| File | Contents | Ownership | Committed to git? |
|---|---|---|---|
| `data/meridant_frameworks.db` | All `Next_*` tables — framework IP | Local master → pushed to Fly.io on version release | No — managed via scripts |
| `data/meridant.db` | All `Assessment*` + `Client` tables | Fly.io master → pulled locally for review | Never — contains client data |

`scripts/migrate_split_db.py` done — idempotent, verified row counts. `MeridantClient` uses `ATTACH DATABASE` so all existing SQL works without modification.

**8.2 — Full product rename across the codebase** ✅ PARTIAL

Completed:
- `tmm_client.py` → `meridant_client.py`, `TMMClient` → `MeridantClient`
- `.env` vars: `TMM_DB_PATH` → `MERIDANT_FRAMEWORKS_DB_PATH` + `MERIDANT_ASSESSMENTS_DB_PATH`
- `e2caf.db` → `meridant_frameworks.db` + `meridant.db`
- App title: `Meridant Matrix` throughout `app.py`

Still remaining:
- Export filename conventions in `heatmap.py`, `roadmap.py` (still use legacy prefixes)
- Some page titles and HTML component headers may still reference E2CAF

**8.3 — `Next_*` table prefix migration** (PENDING — highest effort)

Rename all `Next_*` tables to `Framework_*` in `meridant_frameworks.db`, then update all SQL across the codebase. Do a global search for `Next_` before starting — count is high. Write `scripts/migrate_table_names.py`.

**8.4 — Local ↔ Fly.io sync workflow** ✅ COMPLETE

Sync scripts committed to repo. Use these instead of raw `fly ssh sftp` commands:

```bash
./deploy.sh                           # git push + fly deploy + framework DB upload (full deploy)
./deploy.sh --skip-db                 # code deploy only
./deploy.sh --skip-code               # framework DB upload only
./db-push.sh --frameworks             # push framework DB only (safe)
./db-push.sh --assessments            # push assessment DB (DESTRUCTIVE — requires YES confirmation)
./db-push.sh --both                   # push both DBs (DESTRUCTIVE)
./db-push.sh --dry-run                # preview without uploading
./db-pull.sh                          # pull both DBs from Fly.io to local
./db-pull.sh --frameworks             # pull framework DB only
./db-pull.sh --assessments            # pull assessment DB only
./db-pull.sh --dry-run                # preview without downloading
```

**Convention:** Never push local assessment data up to Fly.io without `YES` confirmation. Framework DB always flows local → Fly.io. Assessment DB always flows Fly.io → local. Never commit either DB file to git.

**8.5 — `.gitignore` and `.env.example` updates** ✅ COMPLETE

`.gitignore` covers `data/*.db`, `.env`, `auth_config.yaml`. `.env.example` documents all current vars with `MERIDANT_FRAMEWORKS_DB_PATH` + `MERIDANT_ASSESSMENTS_DB_PATH`.

---

### Priority 9 — Wizard UX Improvements

> Goal: Improve the Create Assessment wizard experience with better navigation and orientation cues.

**9.1 — Breadcrumb navigation across wizard steps** ✅ COMPLETE (2026-03-23)
- Breadcrumb bar renders above each step heading via `_render_breadcrumbs()` in `create_assessment.py`
- Completed steps: dark blue underlined text, clickable — navigates back to that step
- Current step: bold navy text with indigo background pill
- Future steps: greyed-out text
- Implementation: Bootstrap HTML component (`st.components.v1.html()`) for visual display; hidden Streamlit `st.button` elements as JS-triggered navigation bridges
- `completed_steps` set tracked in `st.session_state`; populated at every forward navigation point; restored correctly on assessment resume via `_hydrate_session_from_db()`
- `_get_wizard_steps(mode)` helper: returns ordered step list, hides Step 2 (Capability Discovery) for predefined mode
- Step numbering adapts: 8 steps for custom mode, 7 steps for predefined mode (step 2 omitted)
- "Start New Assessment" clears `completed_steps`

---

### Priority 10 — White Label Branding

> Goal: Allow the platform to be rebranded at two levels — per-deployment (reseller/partner ships the app under their own brand) and per-client (assessment exports carry the client's logo and colours).

**10.1 — Deployment-level branding config**
- New `branding_config.yaml` (or `.env` vars) that overrides Meridant defaults:
  - `BRAND_NAME` — wordmark text (default: "meridant")
  - `BRAND_TAGLINE` — header tagline (default: "Map the gap.  Chart the path.")
  - `BRAND_LOGO_PATH` — path to SVG or PNG logo file (replaces the polyline SVG in `app.py`)
  - `BRAND_PRIMARY_COLOR` — replaces `#0F2744` (navy)
  - `BRAND_ACCENT_COLOR` — replaces `#2563EB` (accent blue)
  - `BRAND_FOOTER_TEXT` — footer copyright line
- `app.py` reads brand config at startup and injects into header/footer HTML and CSS variables
- CSS custom properties (`--brand-primary`, `--brand-accent`) set on `:root` so all components inherit
- Volume-mountable on Fly.io alongside `auth_config.yaml`; committed template `.branding_config.example.yaml`

**10.2 — Per-client export branding**
- `Client` table gains optional columns: `logo_path TEXT`, `brand_primary TEXT`, `brand_accent TEXT`
- Client management panel (Priority 3.1) exposes logo upload + colour pickers
- Logo stored in `data/client_logos/{client_id}.png` (gitignored); path recorded in `Client.logo_path`
- All export functions accept optional brand overrides:
  - `generate_heatmap_excel()` — client logo in header row, brand colours for highlights
  - `generate_roadmap_excel()` — client logo on cover sheet
  - Word export (`report_writer.py`, Priority 4.1) — client logo on cover page, brand accent for headings
  - PowerPoint export (`report_presenter.py`, Priority 4.2) — client logo on title slide and footer
- Falls back to deployment brand (10.1) or Meridant defaults when no client brand is set
- Implementation note: `openpyxl` supports image insertion via `add_image()`; `python-pptx` via `add_picture()`

**Dependency order:** 10.1 can be built independently. 10.2 depends on Priority 3.1 (client management panel) for the logo upload UI, and on Priority 4.1/4.2 for document exports.

---

## Architectural Decisions (ADRs)

A lightweight log of key decisions made during development. Consult before proposing changes that touch these areas.

---

**ADR-001 — SQLite over PostgreSQL**
*Decision:* Use SQLite as the sole database engine.
*Rationale:* The platform is deployed by a single consultant on a local machine or a single Docker container. SQLite requires zero infrastructure, is trivially backed up (copy the file), and is sufficient for the concurrent load (one user at a time). Migrating to PostgreSQL is straightforward if multi-user or cloud deployment becomes a requirement — the `MeridantClient` abstraction layer (`meridant_client.py`) isolates all DB calls.
*Revisit when:* The platform is deployed to a shared server with multiple simultaneous users, or when the DB file exceeds ~1GB.
*Note:* WAL mode intentionally disabled — not supported on Windows Docker bind mounts.

---

**ADR-002 — Docker-only runtime, no local venv**
*Decision:* All Python dependencies live inside the Docker image. There is no local virtual environment.
*Rationale:* Eliminates "works on my machine" issues when handing the tool to other consultants. The `Dockerfile` is the single source of truth for the runtime environment. `docker compose up --build` is always the correct start command — `docker compose restart` does not pick up code changes.
*Constraint:* Claude Code must not attempt to run `pip install`, `python`, or `streamlit` directly in the shell. All execution happens inside the container via `docker compose exec app ...`.

---

**ADR-003 — No ORM**
*Decision:* All SQL is written directly — in `sql_templates.py` for reusable queries, or inline in engine/page files for one-off queries.
*Rationale:* The `Next_*` schema is complex, has known quirks (duplicate `CapabilityLevel` rows, CHECK constraints, sparse capability IDs), and was built incrementally via ALTER TABLE. An ORM layer would obscure these quirks rather than make them explicit. Raw SQL keeps the behaviour predictable and auditable.
*Constraint:* Never introduce SQLAlchemy, Peewee, or any other ORM. Keep SQL in `sql_templates.py` unless it is truly one-off engine logic.

---

**ADR-004 — Streamlit components via `st.components.v1.html()` only**
*Decision:* All rich UI (heatmaps, Gantt charts, capability cards, recommendation panels) is rendered as Bootstrap 5.3 dark HTML injected via `st.components.v1.html()`. Data is passed via `json.dumps()` into `const DATA = {...}` inside the HTML blob. Streamlit native widgets (buttons, forms) remain outside the component.
*Rationale:* Streamlit's native widget set cannot produce the visual quality required for a consulting tool. Bootstrap + Chart.js inside `st.components.v1.html()` gives full CSS/JS control. Mixing Streamlit widgets inside HTML components causes event handling conflicts.
*Constraint:* Never use `localStorage` or `sessionStorage` inside HTML components — these APIs are not reliably available in the Streamlit iframe context. Never put `st.button()` or `st.form()` inside the HTML blob.

---

**ADR-005 — AI calls centralised in `ai_client.py`**
*Decision:* All Anthropic API calls live in `src/ai_client.py`. Page files and engine files call functions from `ai_client.py` — they never construct prompts or call the Anthropic client directly.
*Rationale:* Centralises model version management (`ANTHROPIC_MODEL` env var), retry logic (`_call_with_retry()` with exponential backoff on 529 overload), and JSON fence stripping. Makes it straightforward to swap models or add caching without touching page logic.
*Constraint:* Do not add `import anthropic` to any file other than `ai_client.py`.

---

**ADR-006 — Roadmap is session-state only (current)**
*Decision:* The generated roadmap (`roadmap_data`) is held in `st.session_state` and not persisted to the DB.
*Rationale:* Roadmap generation is fast and cheap relative to recommendations. Session-state was chosen for MVP speed. The roadmap is always regenerable from the recommendations data, which IS persisted.
*Revisit when:* Assessment resume (ADR planned feature 6.1) is implemented — at that point roadmap persistence becomes necessary for a complete resume experience. See Roadmap item 6.1 for the planned `AssessmentRoadmap` table schema.

---

**ADR-007 — `AssessmentRecommendation` created inline, not via migration script**
*Decision:* `AssessmentRecommendation` is created by `recommendation_engine.py` via `CREATE TABLE IF NOT EXISTS` on first run. It is not in a migration script.
*Rationale:* The table was added late in development. Inline creation keeps it self-healing — if the table is missing it is recreated automatically without manual intervention.
*Constraint:* The exact column list is documented in the Database section above and must be kept in sync. Do not add columns without updating both the `CREATE TABLE` statement in `recommendation_engine.py` and the column list in this file.

---

**ADR-009 — Split DB architecture: framework data vs assessment data** ✅ IMPLEMENTED
*Decision:* Separate the single `e2caf.db` file into two purpose-specific SQLite databases: `meridant_frameworks.db` (framework IP, local master) and `meridant.db` (assessment data, Fly.io master). Connected via SQLite `ATTACH DATABASE` in `meridant_client.py`.
*Rationale:* Framework data and assessment data have fundamentally different ownership, lifecycle, and sensitivity. Framework data is Vernon's IP — it changes deliberately with version releases and always flows local → Fly.io. Assessment data is client-sensitive — it accumulates on Fly.io and should never be committed to git. A single DB conflates these concerns and makes sync error-prone. The split also provides a natural boundary for the future pluggable framework architecture (Meridant Benchmarks).
*Status:* Migration complete — `migrate_split_db.py` ran successfully. Sync scripts (`deploy.ps1`, `db-push.ps1/sh`, `db-pull.ps1/sh`) are committed and documented.
*Constraint:* Never commit either DB file to git. Never push local assessment data up to Fly.io without explicit `YES` confirmation. Framework DB updates always originate locally and are pushed after a version increment.

---

**ADR-010 — Multi-framework architecture target state (future)**
*Decision:* The platform is being designed toward a pluggable framework model where any registered framework (E2CAF, NIST CSF, CSA CCM, ISO 27001, CMMI, etc.) can be loaded and assessed against using the same engine.
*Rationale:* The initial E2CAF-specific `Next_*` schema hardcodes the framework structure. To support multiple frameworks, the schema needs a `framework_id` foreign key on all framework tables, and the assessment engine needs to be framework-agnostic. This is the architecture that makes Meridant Benchmarks a distinct and valuable product — the content layer is separable from the platform engine.
*Constraint:* Do not build new features that further hardcode E2CAF-specific assumptions into the engine or UI. When adding capabilities, ask: "would this work if a different framework were loaded?" If not, it needs to be abstracted. Full schema migration is planned as part of Roadmap Priority 8 and beyond.

---

## Brand Architecture

Meridant is the master brand. All product and capability names are sub-brands under Meridant. Use the full sub-brand name (`Meridant Matrix`, not just `Matrix`) in all user-facing text, export filenames, page titles, and documentation.

### Sub-brand Map

| Sub-brand | Role | Current equivalent in codebase |
|---|---|---|
| **Meridant Matrix** | The platform — the full Streamlit application | `app.py` + all pages |
| **Meridant Index** | The assessment engine — capability scoring, question generation, gap analysis, recommendations | `recommendation_engine.py` + `create_assessment.py` wizard |
| **Meridant Insight** | Reporting and visualisation — heatmaps, Gantt charts, narrative exports | `heatmap.py` + `roadmap.py` + `report_writer.py` + `report_presenter.py` |
| **Meridant Benchmarks** | The framework and model library — E2CAF today, multi-framework in future | `meridant_frameworks.db` + `Framework_*` tables |
| **Meridant Studio** | Configuration and design workspace — framework authoring, use case management | `usecase_workspace.py` + planned framework admin panel |

### Naming Conventions for Claude Code

- Streamlit page titles: use sub-brand name where appropriate (e.g. "Meridant Insight — Assessment Report")
- Export filenames: `Meridant_{SubBrand}_{ClientName}_{Date}.{ext}` (e.g. `Meridant_Insight_DeutscheBank_2026-03-13.docx`)
- Python module names: use `meridant_` prefix for all new top-level modules (e.g. `meridant_client.py`, `meridant_report.py`)
- DB files: `meridant_frameworks.db` and `meridant.db` — no other naming conventions
- Never use "E2CAF", "TMM", or "Assessment MVP" in any new user-facing text, filenames, or comments
- Internal framework content (capability names, domain names, version labels) still refers to "E2CAF" as the framework name — this is correct, E2CAF is the name of the framework loaded into Meridant Benchmarks, not the product itself

### Trademark & IP Notes

**Due diligence completed: 2026-03-13**
- "Meridant" searched on USPTO TESS (Class 042) — no registered trademark or wordmark found
- "Meridant Consulting" exists as a small business consulting firm with a minimal two-page web presence, no substantive service description, and no apparent enterprise software or IT market activity
- Common law risk assessed as low — different market segment, different type of offering (software platform vs small business consulting), no USPTO filing to defend
- No action required at current stage (internal HPE use only)

**When commercialisation becomes concrete** (active licensing conversations): engage a US trademark attorney to file in Class 042. Budget $1,500–2,500. A likelihood-of-confusion response against Meridant Consulting is winnable given the distinctions above.

- Sub-brand names (Matrix, Index, Insight, Benchmarks, Studio) are descriptive and not independently trademarkable — trademark protection derives from the Meridant master mark
- E2CAF framework content loaded into Meridant Benchmarks is HPE IP — maintain clear separation between the platform (Meridant) and the framework content (E2CAF / HPE) in any commercial or licensing conversations

---

*This file is the source of truth for Claude Code context. Keep it current.*
