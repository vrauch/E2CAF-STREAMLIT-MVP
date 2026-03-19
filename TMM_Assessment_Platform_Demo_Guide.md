# TMM Assessment Platform — Demo Guide
### Guided Capability Assessment · Step-by-Step Walkthrough
**Hewlett Packard Enterprise | Cloud & Platform Services | Advisory & Professional Services**

---

## Platform Overview

The TMM Assessment Platform is an AI-powered tool that guides consulting teams and clients through structured capability assessments. Built on HPE's Transformation Maturity Model (TMM), it replaces manual spreadsheet-based assessments with an intelligent, repeatable process that identifies capability gaps, generates tailored questions, captures responses, produces executive-ready findings, and delivers an AI-generated transformation roadmap — all persisted to a database for longitudinal tracking.

The platform is designed for use during client discovery and transformation planning engagements. It requires no specialist technical knowledge to operate — a consultant runs the wizard end-to-end, either live in a workshop or by circulating a question sheet for offline completion.

> **What makes this different from a traditional assessment?**
> Traditional assessments rely on pre-built question templates that may not reflect a client's specific context. This platform uses AI to select the most relevant capabilities from a library of 300+ options, generate questions tailored to the client's stated intent, interpret findings in a consulting-grade narrative, and produce a sequenced transformation roadmap — all in minutes rather than days.

---

## Application Navigation

The platform has three pages, accessible from the sidebar:

| Page | Purpose |
|---|---|
| **Dashboard** | Interactive TMM Knowledge Library explorer — browse domains, subdomains, and capabilities |
| **Create Assessment** | Seven-step guided assessment wizard |
| **Architecture** | Platform architecture diagram |

---

## Dashboard — TMM Knowledge Library

The Dashboard is an interactive explorer of the full TMM capability library. It gives consultants a reference view of all 12 domains, their subdomains, and every capability in the model — useful for familiarisation before running an assessment or for exploring the breadth of the framework with a client.

### What the dashboard shows

At the top, a KPI bar summarises the full library: total domains, subdomains, capabilities, interdependencies, and mapped use cases. Below this, 12 domain cards are displayed in a colour-coded grid. Each card shows the domain's subdomain count, capability count, and outbound dependency count.

**Drilling down:**
1. Click any domain card to expand its subdomain panel below the grid
2. Click a subdomain to view its capability cards — each shows the capability name and a five-pip maturity indicator
3. Click any capability card to open a detail overlay with the capability description, owner role, and tabbed maturity level descriptors (L1 through L5), including capability state narrative and key indicators per level

A breadcrumb bar tracks the navigation path and allows jumping back to any level. The domain panel can be collapsed using the Close button.

### Maturity level naming

The TMM uses the following level names throughout the platform:

| Level | Name | Meaning |
|---|---|---|
| L1 | Ad Hoc | No formal process or ownership exists |
| L2 | Defined | Documented and consistently applied |
| L3 | Integrated | Integrated across functions with measured outcomes |
| L4 | Intelligent | Data-driven, automated, and predictive |
| L5 | Adaptive | Continuously optimised, benchmarked, industry-leading |

---

## The Seven Steps at a Glance

| Step | Name | Purpose |
|---|---|---|
| 1 | Define Use Case | Load a saved assessment, or capture client context and intent for a new one |
| 2 | Capability Discovery | AI selects the most relevant capabilities from the TMM library |
| 2b | Set Domain Targets | Consultant sets the desired maturity level per domain |
| 3 | Generate Questions | AI creates tailored assessment questions for each capability |
| 4 | Run Assessment | Capture responses online or via offline upload |
| 5 | Findings & Report | Scores, heatmap, gaps, AI executive narrative, and database persistence |
| 6 | Transformation Roadmap | AI-generated gap-closure roadmap with Gantt chart and Excel export |

---

## Step 1 — Define Client & Use Case

### What this step does

Step 1 opens to an **assessment loader** — a list of all previously saved assessments in the database. The consultant can select any past assessment and click **Load Assessment** to resume or review it. The loaded session jumps directly to Step 5 (Findings), ready for re-examination or roadmap generation.

To start a fresh engagement, the consultant clicks **＋ Start New Assessment** to access the intake form.

### New assessment form

Every new assessment begins by capturing who the client is and what they are trying to achieve. The consultant fills in client details — name, industry, sector, and country — followed by a use case name and a free-text intent statement. This open-ended approach ensures the entire assessment is anchored to the client's actual goals rather than a generic template.

The intent statement is the most important input in the entire process. Everything that follows — which capabilities are selected, what questions are asked, and how findings are framed — flows from what is written here. A good intent statement describes the transformation outcome the client is seeking, not the technology they want to deploy.

**AI intent enhancement:** A **Strengthen with AI** button is available next to the intent field. Clicking it sends the rough intent to Claude, which rewrites it into a clear, structured 2–3 sentence statement that captures the client's goals, scope, and priorities while remaining faithful to the original meaning. The consultant can accept or further edit the result before proceeding.

### Client fields

| Field | Purpose |
|---|---|
| Client name | Used to create or match a Client record in the database |
| Engagement name | Optional — names the broader programme this assessment belongs to |
| Industry | Education, Financial Services, Government, Healthcare, etc. |
| Sector | Public, Private, Non-Profit |
| Country | Used for context in findings and future benchmarking |

> **Example intent statement:**
> *"Establish a trusted data foundation that enables AI-driven decision-making across the university, with clear governance, secure access controls, and measurable data quality standards that regulators and internal stakeholders can rely on."*

### Inputs & Outputs

| Inputs | Outputs |
|---|---|
| Client name, industry, sector, country | Client record created or matched in database |
| Engagement name | Use case and intent saved to session |
| Use case name and intent (free text) | All context carried forward to every subsequent step |
| Optional: AI intent enhancement | Strengthened intent statement via Claude |

### Future work
- Pre-built intent templates for common use cases (Data Transformation, Cloud Migration, Operating Model Modernisation)
- Multi-stakeholder intent capture — aggregate intent from multiple contributors before running discovery

---

## Step 2 — Capability Discovery

### What this step does
With the intent defined, the platform queries the full TMM capability library — over 300 enterprise capabilities organised by domain and subdomain — and sends them to an AI model along with the client's intent statement. The AI reads the intent and selects the capabilities most likely to be relevant, ranking each with a relevance score and a one-sentence rationale explaining why it was selected.

The selected capabilities become the **Core** set — the capabilities directly in scope for this assessment. The platform then automatically expands the scope by traversing the TMM dependency graph to identify:

- **Upstream** capabilities — the enablers and prerequisites that must be in place for Core capabilities to succeed
- **Downstream** capabilities — the outcomes and consumers that depend on Core capabilities being mature

> **Core / Upstream / Downstream model:**
> Think of Core as the capabilities you are directly assessing. Upstream are the foundations — if they are weak, Core will fail. Downstream are the value outcomes — if Core is immature, Downstream will never be realised. This three-layer model gives a complete picture of transformation risk.

### Inputs & Outputs

| Inputs | Outputs |
|---|---|
| Intent text from Step 1 | Core capabilities with AI relevance scores and rationale |
| Number of Core capabilities to select (slider, 5–20) | Upstream capabilities (dependency-expanded) |
| | Downstream capabilities (dependency-expanded) |
| | Domains covered (derived from selected capabilities) |

### Future work
- Replace AI token-scoring with vector embeddings for higher semantic precision
- Allow the consultant to manually add or remove capabilities from the discovered set
- Visualise the dependency graph as an interactive network diagram
- Filter discovery by domain (e.g. assess Security domain only)

---

## Step 2b — Set Domain Target Maturity

### What this step does
Before questions are generated, the consultant sets a target maturity level for each domain identified in Step 2. This defines what 'good' looks like for each area of the assessment and drives the gap analysis in the final findings.

Targets default to **3 (Integrated)** — meaning the client has documented, integrated, and consistently measured processes. The consultant can raise or lower targets per domain based on client ambition, regulatory requirements, or strategic priority.

### Maturity scale

| Level | Label | Meaning |
|---|---|---|
| 1 | Ad Hoc | No formal process or ownership exists |
| 2 | Defined | Documented and consistently applied |
| 3 | Integrated | Integrated across functions with measured outcomes — **default target** |
| 4 | Intelligent | Data-driven, automated, and predictive |
| 5 | Adaptive | Continuously optimised, benchmarked, industry-leading |

> **Example:** A Security domain might target 4 (Intelligent) due to regulatory pressure, while an Innovation domain might only need to reach 2 (Defined) in the near term.

### Inputs & Outputs

| Inputs | Outputs |
|---|---|
| Domains discovered in Step 2 | Domain target maturity map |
| Consultant judgement on client ambition per domain | Per-domain targets used in Step 5 gap analysis and heatmap |

### Future work
- AI-suggested targets per domain based on intent and industry benchmarks
- Regulatory preset targets — e.g. EU AI Act compliance auto-sets Security and Governance targets to 4
- Pull target maturity from `Next_TargetMaturity` table in TMM for use-case-specific targets

---

## Step 3 — Generate Assessment Questions

### What this step does
For each capability in scope — Core, Upstream, and Downstream — the platform calls an AI model to generate a set of tailored assessment questions. Unlike template-based approaches, these questions are written specifically for the capability, domain, subdomain, and role in the context of the client's stated intent.

The consultant controls three parameters: how many questions to generate per capability, the question style, and whether to include Upstream and Downstream capabilities. A progress bar shows generation advancing capability by capability.

### Three question styles

| Style | Response type | Best for |
|---|---|---|
| Maturity (1–5) | Scored 1–5 | Structured scoring assessments |
| Evidence (Yes/No) | Yes / No / Partial + notes | Compliance-style assessments |
| Workshop (Discussion) | Free text + score | Facilitated workshop sessions |

Once generated, questions are displayed in a table and can be downloaded as a CSV. This CSV serves as the **offline question sheet** — assessors fill in the score, answer, and notes columns and upload it back in Step 4.

### Inputs & Outputs

| Inputs | Outputs |
|---|---|
| Capabilities from Step 2 (Core, Upstream, Downstream) | Question set with capability, domain, subdomain, role, question text, response type, and guidance |
| Client intent from Step 1 | Downloadable CSV with score/answer/notes columns pre-added for offline use |
| Questions per capability (slider, 2–7) | |
| Question style (Maturity / Evidence / Workshop) | |
| Include Upstream and Downstream (toggle) | |

### Future work
- Generate questions informed by CapabilityLevel feature descriptions from TMM
- Multi-language question generation for non-English engagements
- Question deduplication across capabilities to reduce assessment fatigue
- Consultant review and edit mode — accept, reject, or rewrite individual questions before use

---

## Step 4 — Run Assessment

### What this step does
Step 4 is where responses are captured. Questions are presented grouped by capability role (Core first, then Upstream, then Downstream), and within each role by domain and capability. Each capability is presented in a collapsible panel so the assessor can work through sections at their own pace.

A progress bar at the top tracks how many questions have been answered. The Submit Assessment button becomes active once at least one response has been recorded.

### Online mode
For each question, the response widget adapts to the question style:
- **Maturity** — 1–5 radio button with labels (Not Defined → Optimized)
- **Yes/No** — Yes / No / Partial radio with evidence notes field
- **Workshop** — free-text discussion notes field and score slider

### Offline mode
If the assessment cannot be completed in the application — for example, responses are gathered in a workshop, by email, or in a printed session — the consultant downloads the question CSV from Step 3, distributes it, collects completed responses, and uploads the filled-in file here. The platform accepts **both CSV and Excel (.xlsx) formats** and reads each row, loading valid responses into the session ready for Step 5.

### On submit
When the consultant clicks **Submit Assessment**, the platform writes the following to the database before proceeding to findings:

- A new **Assessment** record linked to the Client
- All **AssessmentCapability** records (Core, Upstream, Downstream with AI scores and rationale)
- All **AssessmentResponse** records (one row per answered question)

### Inputs & Outputs

| Inputs | Outputs |
|---|---|
| Question set from Step 3 | Response set stored in session and database |
| Responses entered online or via uploaded CSV/Excel | Assessment and response records written to database |
| | Progress indicator (X of Y answered) |

### Future work
- Resume a partially completed assessment in a later session
- Multi-respondent mode — aggregate responses from multiple stakeholders per capability
- Confidence weighting — flag responses where the assessor indicated low confidence
- Response validation rules — flag inconsistencies (e.g. score 5 with notes indicating major gaps)

---

## Step 5 — Assessment Findings

### What this step does
Step 5 transforms raw responses into a structured set of findings. Before any scores are displayed, the platform runs an **automatic pre-scoring pass** to ensure all responses have a numeric score regardless of question type:

- **Maturity (1–5)** responses — score is already numeric; no action needed
- **Yes/No/Evidence** responses — mapped to numeric scores: Yes → 3, Partial → 2, No → 1
- **Free-text / Workshop** responses without a score — sent in batch to Claude, which assigns a 1–5 score with rationale based on the Ad Hoc → Adaptive rubric; the rationale is appended to the response notes

Once pre-scoring is complete, scores are rolled up to capability averages and domain averages. Each capability and domain is measured against its target maturity from Step 2b, and the gap is calculated.

### Five layers of insight

1. **Overall maturity score** — single headline number for the assessment, with client and use case context
2. **Maturity Heatmap** — visual grid showing per-level completion per domain (see below)
3. **Domain scores** — average score per domain with gap-to-target
4. **Capability scores by role** — Core, Upstream, and Downstream in separate tabs, sorted by score
5. **High-risk capabilities** — anything scoring below 2, flagged for immediate attention

### Maturity Heatmap

The heatmap is a colour-coded grid with domains across the columns and maturity levels (L5 Adaptive → L1 Ad Hoc) down the rows. Each cell shows a completion percentage for that domain at that level, using a per-level score formula that maps the domain's average score to a staircase of 0–1 completions per level:

- **Green** — fully achieved at this level (100%)
- **Amber** — partially achieved (1–99%)
- **White** — not yet reached (0%)

The bottom rows show the overall average maturity score (1–5 scale) and the target set in Step 2b for each domain.

### AI Executive Summary
The final section is an AI-generated executive narrative — a consulting-grade summary that interprets the scores rather than restating them. It identifies the strongest and weakest domains, calls out high-risk capabilities and their transformation implications, and closes with prioritised recommendations for immediate action. The narrative is generated fresh from the actual scores and can be regenerated using the **Regenerate Summary** button.

### Database persistence
When Step 5 loads, the platform automatically writes findings to the database:

- **AssessmentFinding** records for every domain and capability (avg_score, target_maturity, gap, risk_level)
- **Assessment** record updated with overall_score, status = 'complete', and completed_at timestamp

### Database schema summary

| Table | Contents |
|---|---|
| `Client` | Client name, industry, sector, country |
| `Assessment` | Use case, intent, overall score, status, timestamps — linked to Client |
| `AssessmentCapability` | All capabilities in scope with AI scores, rationale, and domain targets |
| `AssessmentResponse` | Every question response with score, answer, and notes |
| `AssessmentFinding` | Rolled-up scores per capability and domain with gap and risk level |

### Exports

Four download buttons are provided:

| Export | Format | Contents |
|---|---|---|
| Capability Scores | CSV | Per-capability avg score, target, gap, and risk flag |
| Domain Scores | CSV | Per-domain avg score, target, and gap |
| All Responses | CSV | Every answered question with score, answer, and notes |
| Maturity Heatmap | Excel (.xlsx) | Styled heatmap grid with per-level scores, avg maturity, target, gap, and legend — branded for client delivery |

### Navigation
At the bottom of Step 5, two buttons are provided:
- **Start New Assessment** — clears all session state and returns to Step 1
- **Continue to Roadmap →** — advances to Step 6 to generate the transformation roadmap

### Inputs & Outputs

| Inputs | Outputs |
|---|---|
| All responses from Step 4 | Overall maturity score |
| Domain targets from Step 2b | Maturity heatmap visualisation |
| Client intent from Step 1 | Domain and capability score tables |
| | High-risk capability list |
| | AI executive summary narrative |
| | Findings persisted to database |
| | CSV and Excel exports |

### Future work
- Auto-generate a formatted Word or PDF client report from findings
- Benchmark comparison — compare client scores against industry or peer averages stored in TMM

---

## Step 6 — Transformation Roadmap

### What this step does
Step 6 generates an AI-powered transformation roadmap that sequences capability improvements based on the assessment findings. Claude analyses the gaps, domain scores, client intent, and the dependency relationships between capabilities to produce a realistic, phased plan for closing the maturity gap.

### Roadmap settings
Before generating the roadmap, the consultant configures three parameters:

| Setting | Options | Purpose |
|---|---|---|
| Timeline unit | Sprints (2 wks) · Weeks · Quarters (13 wks) | Controls the Gantt chart time axis |
| Horizon | 3 · 6 · 9 · 12 · 18 · 24 months | Total planning window for the roadmap |
| Capability scope | Core · Core + Upstream · All | Which capability tiers to include in the plan |

Clicking **Generate Roadmap** sends the full assessment data — capability scores, domain scores, overall score, intent text, horizon, and scope — to Claude, which returns a structured JSON roadmap.

### What Claude generates
The roadmap is structured as a set of **phases**, each containing **initiatives**. Each initiative maps to a specific capability and domain, carries a priority (Critical / High / Medium / Low), and is positioned on a timeline with start and end periods.

Each phase also includes:
- **Story** — a Scrum-format user story that frames the phase outcome
- **Description** — a narrative summary of what the phase accomplishes
- **Activities** — a bullet list of concrete actions within the phase

The roadmap JSON also identifies a **quick wins** list (initiatives achievable early with high impact) and a **critical path** (the sequence of initiatives that determines the minimum delivery timeline).

### Gantt chart visualisation
The roadmap is rendered as a colour-coded Gantt chart in the browser. Each row is an initiative; columns are time periods (sprints, weeks, or quarters) up to the chosen horizon. Initiatives are colour-coded by domain (matching the TMM domain palette) and carry a priority badge. Phase header rows divide the Gantt into logical sections.

### Phase narratives
Below the Gantt, each phase is rendered as an expandable section showing its story, description, and key activities. These narratives are written for consultant use and can be incorporated directly into client presentations or programme documentation.

### Excel export
A single **Download Roadmap (Excel)** button exports a three-sheet workbook:
- **Initiatives** — full initiative list with domain, priority, start/end periods, and outcome statement
- **Phase Narratives** — story, description, and activities for each phase
- **Critical Path** — the sequenced critical path initiatives

### Inputs & Outputs

| Inputs | Outputs |
|---|---|
| Cap/domain scores from Step 5 | AI-structured roadmap JSON with phases and initiatives |
| Client intent and overall score | Interactive Gantt chart (browser-rendered) |
| Timeline unit, horizon, scope settings | Phase narratives with story, description, activities |
| | Quick wins and critical path lists |
| | Roadmap Excel export (3 sheets) |

### Future work
- Effort and investment estimation per initiative
- Dependency arrows on the Gantt chart between linked initiatives
- Roadmap comparison — show how the plan changes if target maturities are raised or lowered
- Programme milestone integration — overlay client delivery milestones on the Gantt

---

## Platform Roadmap — Planned Enhancements

### Reporting
A one-click report generation feature will produce a formatted Word document or PDF containing the full findings, including the domain and capability tables, heatmap, executive summary, and roadmap summary. Reports will be branded and structured for direct client delivery without further editing.

### Assessment History Dashboard
The existing dashboard currently serves as a TMM Knowledge Library explorer. A planned enhancement will add an assessment history view — showing all past assessments sortable by client, industry, use case, date, and overall score — allowing consultants to load a past assessment, compare two assessments side-by-side, and track maturity improvement over time for repeat engagements.

### AI Enhancements
The current AI capability ranking uses semantic scoring based on intent similarity. Planned enhancements include:
- Vector embeddings for higher-precision capability selection
- AI-suggested domain targets based on industry benchmarks and regulatory context
- Deeper roadmap intelligence: effort estimation, dependency-aware sequencing, and investment prioritisation

### Multi-Respondent Assessments
In large engagements, different stakeholders own different domains. A future multi-respondent mode will allow the consultant to assign question sets to named respondents by domain, aggregate scores automatically, and flag divergence between respondents as an additional insight layer.

### Client Benchmarking
As assessment data accumulates across clients and industries, the platform will support cross-client benchmarking — allowing consultants to show a client how their maturity compares to peers in the same industry or sector. This is enabled by the Client table's industry and sector fields captured in Step 1.

---

*Hewlett Packard Enterprise | Cloud & Platform Services | Advisory & Professional Services*
