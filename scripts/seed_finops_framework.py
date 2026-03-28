#!/usr/bin/env python3
"""
seed_finops_framework.py
========================
Meridant Matrix — FinOps Foundation Framework Seed
Run from project root inside Docker:

    docker compose exec app python scripts/seed_finops_framework.py

What this script does
---------------------
1. Registers FinOps Foundation in Next_Framework (framework_id auto-assigned)
2. Seeds 1 Pillar      → Next_Domain      ("FinOps Framework")
3. Seeds 4 Domains     → Next_SubDomain   (Understand / Quantify / Optimize / Manage)
4. Seeds 21 Capabilities → Next_Capability
5. Seeds Crawl/Walk/Run maturity descriptors → Next_CapabilityLevel at levels 1, 3, 5

Hierarchy mapping
-----------------
FinOps is a 2-level hierarchy (Domain → Capability). The 3-level DB schema maps as:
  Next_Domain    = single Pillar: "FinOps Framework"
  Next_SubDomain = 4 FinOps Domains
  Next_Capability = 21 FinOps Capabilities

Attribution
-----------
FinOps Framework content is copyright © 2025 FinOps Foundation, licensed CC BY 4.0.
https://creativecommons.org/licenses/by/4.0/
When using this content in client-facing outputs, include attribution:
    "FinOps Framework © FinOps Foundation (https://www.finops.org), CC BY 4.0"

Capability content sourced from:
    https://www.finops.org/framework/capabilities/

Note on capability names vs URL slugs
--------------------------------------
The FinOps Foundation has reorganised some capability names since the framework was
first published. This script uses the authoritative names from the brief and maps
them to the correct content. Some page titles on finops.org now differ from the
brief's names (e.g. "Architecting for Cloud" → "Architecting & Workload Placement").
The DB names follow the brief; descriptions reflect current page content.

Options
-------
    --dry-run    Print what would be inserted, no DB writes
"""

import argparse
import os
import sqlite3
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

FRAMEWORKS_DB = os.getenv("MERIDANT_FRAMEWORKS_DB_PATH", "/data/meridant_frameworks.db")

# ---------------------------------------------------------------------------
# FinOps Foundation Taxonomy
# ---------------------------------------------------------------------------
# Structure mirrors the NIST seed script pattern:
#   pillar        → Next_Domain
#   domains[].name → Next_SubDomain
#   capabilities  → Next_Capability  (capability_name = key, category = human name)
#   maturity      → Next_CapabilityLevel levels 1 (Crawl), 3 (Walk), 5 (Run)
# ---------------------------------------------------------------------------

# Single top-level pillar
FINOPS_PILLAR = {
    "name": "FinOps Framework",
    "description": (
        "The FinOps Foundation Framework defines the capabilities, domains, and "
        "maturity model that organisations use to optimise cloud financial management. "
        "It enables cross-functional collaboration between finance, engineering, and "
        "leadership to maximise the business value of cloud investment."
    ),
}

FINOPS_TAXONOMY = [
    {
        "name": "Understand Usage & Cost",
        "description": (
            "Establish complete visibility into cloud usage and cost data, enabling "
            "organisations to collect, normalise, and distribute accurate financial "
            "information to all stakeholders."
        ),
        "capabilities": [
            {
                "key": "FO-UUC-01",
                "name": "Data Ingestion",
                "description": (
                    "Collect, transfer, store, and normalise data from various cloud and "
                    "technology sources to create a complete, contextual dataset of usage "
                    "and cost data available for analysis. This capability establishes a "
                    "unified, queryable repository supporting all FinOps activities."
                ),
                "maturity": {
                    "crawl": {
                        "state": (
                            "Cloud billing data is collected manually or sporadically from "
                            "provider consoles. No normalisation or enrichment occurs. Data "
                            "quality is inconsistent and coverage is incomplete."
                        ),
                        "indicators": (
                            "Manual data export from cloud consoles | No unified data store | "
                            "Missing or incomplete cost dimensions | No tagging enforcement | "
                            "Ad hoc data requests"
                        ),
                        "criteria": "Basic billing data is retrievable but no automated pipeline or normalisation exists.",
                    },
                    "walk": {
                        "state": (
                            "An automated pipeline ingests billing and usage data from primary "
                            "cloud providers into a central store. Data is normalised to a "
                            "common schema with basic enrichment (account, service, region). "
                            "Stakeholders have defined access to the dataset."
                        ),
                        "indicators": (
                            "Automated ingestion pipeline in place | Common data model applied | "
                            "Primary providers connected | Stakeholder access defined | "
                            "Data freshness SLA established"
                        ),
                        "criteria": "Automated, normalised cost and usage data is available in a central repository for primary providers.",
                    },
                    "run": {
                        "state": (
                            "All technology cost sources (cloud, SaaS, on-premises, licensing) "
                            "are ingested, normalised, and enriched with business metadata in "
                            "near-real-time. Data quality is continuously validated. The "
                            "dataset serves as a single source of truth across the organisation."
                        ),
                        "indicators": (
                            "Multi-source ingestion (cloud, SaaS, on-prem, licensing) | "
                            "Near-real-time availability | Automated quality validation | "
                            "Business metadata enrichment | Documented data lineage | "
                            "Single source of truth"
                        ),
                        "criteria": "All technology cost sources are ingested in near-real-time with validated quality and full business context.",
                    },
                },
            },
            {
                "key": "FO-UUC-02",
                "name": "Allocation",
                "description": (
                    "Assign and distribute cloud costs across teams and projects using "
                    "accounts, tags, labels, and metadata. Establishes strategies for "
                    "allocation, tagging compliance, and shared cost management to create "
                    "accountability and transparency around technology spending."
                ),
                "maturity": {
                    "crawl": {
                        "state": (
                            "Cost allocation is limited to broad account-level groupings. "
                            "Tagging is inconsistent and largely unenforced. Shared costs are "
                            "not distributed and significant spending is unallocated."
                        ),
                        "indicators": (
                            "Account-level allocation only | No tagging policy | "
                            "High percentage of untagged spend | Shared costs not distributed | "
                            "Manual allocation workarounds"
                        ),
                        "criteria": "Some costs are attributable to teams via account structure but most shared spend is unallocated.",
                    },
                    "walk": {
                        "state": (
                            "A tagging policy is defined and enforced for primary workloads. "
                            "Shared costs are distributed using documented allocation rules. "
                            "Most spending is attributable to a cost centre or team. Compliance "
                            "is monitored and reported."
                        ),
                        "indicators": (
                            "Defined tagging policy | Shared cost allocation rules documented | "
                            "Allocation compliance tracked | >80% spend attributed | "
                            "Regular compliance reporting"
                        ),
                        "criteria": "A documented tagging policy is in place with >80% spend attributed; shared costs are distributed via defined rules.",
                    },
                    "run": {
                        "state": (
                            "Near-complete cost allocation is achieved across all technology "
                            "sources. Tagging compliance is automated and enforced at "
                            "provisioning. Shared cost allocation is granular, fair, and "
                            "agreed by all stakeholders. Allocation enables product-level "
                            "unit economics reporting."
                        ),
                        "indicators": (
                            ">95% spend attributed | Automated tag enforcement at provisioning | "
                            "Granular shared cost models | Product-level allocation | "
                            "Allocation supports unit economics | Stakeholder sign-off on model"
                        ),
                        "criteria": "Near-complete allocation (>95%) is automated, granular, and supports product-level unit economics reporting.",
                    },
                },
            },
            {
                "key": "FO-UUC-03",
                "name": "Reporting & Analytics",
                "description": (
                    "Gain insights into cloud usage and cost data by creating reporting "
                    "mechanisms that serve different personas' needs — from ad hoc "
                    "investigation to routine showback and executive dashboards. Fundamental "
                    "for informing decision-making about technology resources."
                ),
                "maturity": {
                    "crawl": {
                        "state": (
                            "Reporting consists of raw provider billing exports or basic "
                            "cost explorer views. Reports are produced on demand for finance "
                            "rather than shared proactively. Limited ability to slice data "
                            "by team, product, or business driver."
                        ),
                        "indicators": (
                            "Provider console reports only | Finance-driven reporting | "
                            "No self-service capability | Limited dimensions | "
                            "Reactive cost reviews"
                        ),
                        "criteria": "Basic cost reporting is available but not distributed or actionable beyond billing reconciliation.",
                    },
                    "walk": {
                        "state": (
                            "Dashboards are available for key personas (engineering, finance, "
                            "leadership) with defined metrics and cost dimensions. Showback "
                            "reports are distributed on a regular cadence. Self-service "
                            "analytics are available for primary stakeholders."
                        ),
                        "indicators": (
                            "Role-specific dashboards in place | Regular showback distribution | "
                            "Self-service access for key teams | Standard cost dimensions available | "
                            "Monthly review cadence established"
                        ),
                        "criteria": "Role-appropriate dashboards are distributed regularly; self-service is available for primary stakeholders.",
                    },
                    "run": {
                        "state": (
                            "Comprehensive, automated reporting covers all technology cost "
                            "dimensions including unit economics, anomalies, and sustainability "
                            "metrics. Real-time or near-real-time dashboards are available "
                            "organisation-wide. Reports actively drive optimisation decisions "
                            "and are used in performance management."
                        ),
                        "indicators": (
                            "Real-time dashboards | Unit economics reporting | "
                            "Sustainability metrics included | Automated distribution | "
                            "Reports linked to OKRs/KPIs | Cross-provider normalised views"
                        ),
                        "criteria": "Automated, near-real-time reporting covers all cost dimensions and actively drives optimisation and performance management.",
                    },
                },
            },
            {
                "key": "FO-UUC-04",
                "name": "Anomaly Management",
                "description": (
                    "Detect, identify, alert, and manage unexpected or unforecasted "
                    "technology cost and usage irregularities in a timely manner. Involves "
                    "tools and processes to identify spending deviations, distribute alerts "
                    "to responsible parties, and drive investigation and resolution."
                ),
                "maturity": {
                    "crawl": {
                        "state": (
                            "Anomalies are discovered reactively — typically after receiving "
                            "a surprise invoice. No automated detection exists. Investigation "
                            "is manual and time-consuming, often after significant cost impact."
                        ),
                        "indicators": (
                            "Reactive discovery only | No automated alerting | "
                            "Manual investigation process | Delays between anomaly and detection | "
                            "No documented response procedure"
                        ),
                        "criteria": "Anomalies are discovered after invoice receipt with no proactive detection capability.",
                    },
                    "walk": {
                        "state": (
                            "Automated anomaly detection is configured for primary workloads "
                            "with threshold-based alerting. Alerts are routed to responsible "
                            "teams. A documented investigation and escalation process exists. "
                            "Key anomaly events are tracked and reviewed."
                        ),
                        "indicators": (
                            "Automated threshold alerts configured | Alerts routed to owners | "
                            "Documented investigation process | Event tracking in place | "
                            "Regular anomaly review meetings"
                        ),
                        "criteria": "Automated alerting is in place for primary workloads with a documented investigation and escalation process.",
                    },
                    "run": {
                        "state": (
                            "ML-driven anomaly detection covers all technology cost sources "
                            "with dynamic baselines and contextual alerting. Alerts are "
                            "automatically correlated with deployment events and business "
                            "context. Resolution workflows are automated where possible, "
                            "and anomaly trends inform forecasting and budgeting."
                        ),
                        "indicators": (
                            "ML/statistical anomaly detection | Dynamic baselines | "
                            "Deployment event correlation | Automated remediation workflows | "
                            "Anomaly trend analysis | Integration with incident management | "
                            "Coverage across all cost sources"
                        ),
                        "criteria": "ML-based detection with dynamic baselines covers all sources; anomaly insights feed into forecasting and budgeting.",
                    },
                },
            },
        ],
    },
    {
        "name": "Quantify Business Value",
        "description": (
            "Connect technology spending to business outcomes by developing the "
            "planning, forecasting, budgeting, and measurement practices that "
            "demonstrate the value generated by cloud investment."
        ),
        "capabilities": [
            {
                "key": "FO-QBV-01",
                "name": "Planning & Estimating",
                "description": (
                    "Explore potential costs and value of workloads under various scenarios "
                    "using cost calculators, trial runs, and extrapolation from past data. "
                    "Estimates inform decision-making around migrations, modernisations, and "
                    "optimisations while considering sustainability impacts."
                ),
                "maturity": {
                    "crawl": {
                        "state": (
                            "Cost estimates are produced informally, often by copying prior "
                            "project spend or using rough order-of-magnitude guesses. No "
                            "standard methodology or tooling exists. Estimates are rarely "
                            "validated against actuals."
                        ),
                        "indicators": (
                            "Informal estimation process | No standard methodology | "
                            "Estimates rarely validated | Ad hoc tooling | "
                            "No linkage to business outcomes"
                        ),
                        "criteria": "Estimates exist but are informal, undocumented, and rarely validated against actual spend.",
                    },
                    "walk": {
                        "state": (
                            "A standard estimation methodology is defined and used for new "
                            "workloads and migrations. Provider cost calculators and historical "
                            "data are used. Estimates are reviewed by FinOps and finance before "
                            "project approval and tracked against actuals post-deployment."
                        ),
                        "indicators": (
                            "Standard estimation process documented | Provider calculators used | "
                            "Historical benchmarks referenced | Pre-approval FinOps review | "
                            "Estimate vs actual tracking"
                        ),
                        "criteria": "A defined estimation methodology is applied to new projects with FinOps review and post-deployment validation.",
                    },
                    "run": {
                        "state": (
                            "Cost estimation is integrated into engineering design and project "
                            "planning as a standard gate. Automated tooling generates estimates "
                            "from infrastructure-as-code. Estimates cover all cost dimensions "
                            "including sustainability. Estimation accuracy is measured and "
                            "continuously improved."
                        ),
                        "indicators": (
                            "Estimation integrated into design workflow | IaC-based cost preview | "
                            "Multi-scenario modelling | Sustainability cost included | "
                            "Estimation accuracy KPI tracked | Continuous methodology improvement"
                        ),
                        "criteria": "Automated cost estimation is embedded in design workflow with multi-scenario modelling and tracked accuracy.",
                    },
                },
            },
            {
                "key": "FO-QBV-02",
                "name": "Forecasting",
                "description": (
                    "Develop models of anticipated future cloud costs and value using "
                    "statistical methods, historical spending patterns, and planned changes. "
                    "Establishes shared expectations among stakeholders about future spending "
                    "and feeds into budgeting decisions."
                ),
                "maturity": {
                    "crawl": {
                        "state": (
                            "Forecasting is based on prior-year spend with a flat percentage "
                            "uplift. No statistical modelling or trend analysis is performed. "
                            "Engineering roadmap changes are not reflected in forecasts. "
                            "Forecast accuracy is not measured."
                        ),
                        "indicators": (
                            "Prior year plus uplift only | No statistical modelling | "
                            "Roadmap changes not incorporated | Forecast accuracy unmeasured | "
                            "Single forecast scenario"
                        ),
                        "criteria": "Forecasts exist but use simple percentage uplift with no statistical basis or accuracy tracking.",
                    },
                    "walk": {
                        "state": (
                            "Forecasts use trend analysis and known planned changes from "
                            "engineering roadmaps. Multiple scenarios are modelled. Forecast "
                            "accuracy is tracked monthly and reviewed with finance and "
                            "engineering teams. Variance explanations are documented."
                        ),
                        "indicators": (
                            "Trend-based forecasting | Roadmap changes incorporated | "
                            "Multiple scenarios modelled | Monthly accuracy review | "
                            "Variance documented | Finance and engineering alignment"
                        ),
                        "criteria": "Trend-based forecasting incorporating roadmap changes is reviewed monthly with documented variance explanations.",
                    },
                    "run": {
                        "state": (
                            "Automated forecasting uses ML models incorporating usage trends, "
                            "seasonal patterns, and committed usage. Forecasts are refreshed "
                            "continuously and served to stakeholders via self-service. "
                            "Accuracy is a tracked KPI with continuous model improvement. "
                            "Forecast data feeds directly into budget and commitment decisions."
                        ),
                        "indicators": (
                            "ML-based forecasting models | Continuous refresh | "
                            "Seasonal and trend factors | Forecast accuracy as KPI | "
                            "Self-service forecast access | Directly informs commitments and budget"
                        ),
                        "criteria": "ML-based automated forecasting is continuously refreshed, accuracy-tracked, and directly informs budget and commitment decisions.",
                    },
                },
            },
            {
                "key": "FO-QBV-03",
                "name": "Budgeting",
                "description": (
                    "Establish approved funding to support an organisation's planned "
                    "technology activities while tracking spending and ensuring accountability. "
                    "Aligns technology costs with business objectives through regular budget "
                    "cycles, holdback strategies, and variance management across cost centres."
                ),
                "maturity": {
                    "crawl": {
                        "state": (
                            "Cloud costs are bundled into a single IT budget line item without "
                            "team-level breakdown. Budget is set annually using prior spend "
                            "without FinOps input. Variance is identified only during monthly "
                            "finance reviews with no actionable alerts."
                        ),
                        "indicators": (
                            "Single IT budget line | No team-level budgets | Annual set-and-forget | "
                            "No FinOps input into budget process | Variance identified monthly at best"
                        ),
                        "criteria": "Cloud costs exist in a single IT budget with no team breakdown and no proactive variance management.",
                    },
                    "walk": {
                        "state": (
                            "Team or product-level cloud budgets are defined and agreed. "
                            "FinOps provides input into the budget process based on forecasts. "
                            "Budget vs actuals is tracked and shared with owners. Alert "
                            "thresholds trigger notifications before budget breach."
                        ),
                        "indicators": (
                            "Team-level budgets defined | FinOps input into budget cycle | "
                            "Budget vs actual tracking | Threshold alerts before breach | "
                            "Quarterly budget review process"
                        ),
                        "criteria": "Team-level budgets are defined with FinOps input, tracked against actuals with threshold alerts.",
                    },
                    "run": {
                        "state": (
                            "Dynamic, granular budgets are maintained at product or service "
                            "level, automatically adjusted for committed discounts and "
                            "engineering changes. Budget governance includes holdback reserves "
                            "and reallocation processes. Budget performance is a KPI reviewed "
                            "by leadership with FinOps recommendations for rebalancing."
                        ),
                        "indicators": (
                            "Product/service-level granularity | Dynamic budget adjustment | "
                            "Holdback reserve managed | Reallocation process defined | "
                            "Budget KPI in leadership reviews | FinOps rebalancing recommendations"
                        ),
                        "criteria": "Dynamic product-level budgets with holdback reserves are auto-adjusted and reviewed by leadership with FinOps recommendations.",
                    },
                },
            },
            {
                "key": "FO-QBV-04",
                "name": "Benchmarking",
                "description": (
                    "Compare KPIs for important aspects of technology value and optimisation, "
                    "both internally between teams and externally against industry peers. "
                    "Establishes reference points that drive continuous improvement and "
                    "align FinOps activities with organisational objectives."
                ),
                "maturity": {
                    "crawl": {
                        "state": (
                            "No formal benchmarking exists. Team performance is compared "
                            "informally against prior periods only. No external benchmarks "
                            "or industry KPIs are used. FinOps success has no defined metrics."
                        ),
                        "indicators": (
                            "No defined FinOps KPIs | Period-over-period comparison only | "
                            "No external benchmarks | No team comparison capability | "
                            "Success defined qualitatively"
                        ),
                        "criteria": "No formal benchmarking exists; performance assessment is informal and qualitative.",
                    },
                    "walk": {
                        "state": (
                            "Internal KPIs are defined for key FinOps metrics (unit costs, "
                            "coverage rates, waste percentage). Teams are compared against "
                            "internal baselines. Industry benchmarks from FinOps Foundation "
                            "or equivalent sources are used as reference points."
                        ),
                        "indicators": (
                            "Defined internal FinOps KPIs | Team-level comparison available | "
                            "Industry benchmarks referenced | Baseline established | "
                            "KPI trends tracked over time"
                        ),
                        "criteria": "Internal FinOps KPIs are defined with team comparison against baselines and external industry benchmarks referenced.",
                    },
                    "run": {
                        "state": (
                            "Comprehensive benchmarking covers all relevant FinOps dimensions. "
                            "Internal benchmarks drive team accountability and improvement goals. "
                            "External benchmarking is systematic and influences strategic targets. "
                            "Benchmark data is embedded in leadership reporting and performance reviews."
                        ),
                        "indicators": (
                            "Comprehensive FinOps KPI coverage | Internal benchmarks drive team goals | "
                            "Systematic external benchmarking | Benchmarks in leadership reporting | "
                            "Benchmark insights influence strategy | Continuous improvement cycle"
                        ),
                        "criteria": "Comprehensive benchmarking covering internal and external dimensions is embedded in leadership reporting and drives strategic targets.",
                    },
                },
            },
            {
                "key": "FO-QBV-05",
                "name": "Unit Economics",
                "description": (
                    "Develop and track metrics that connect technology spending to "
                    "organisational value by relating costs to business outcomes. Enables "
                    "organisations to understand whether spending generates appropriate "
                    "returns through metrics like cost per transaction or cost per customer."
                ),
                "maturity": {
                    "crawl": {
                        "state": (
                            "Technology costs are tracked in aggregate without connection to "
                            "business output metrics. No unit cost metrics are defined. "
                            "Engineering and finance teams cannot relate technology spend "
                            "to product or service value."
                        ),
                        "indicators": (
                            "Aggregate cost reporting only | No unit cost metrics | "
                            "No business outcome linkage | Engineering and finance siloed | "
                            "Value of cloud investment unquantified"
                        ),
                        "criteria": "Costs are tracked in aggregate with no connection to business output or value metrics.",
                    },
                    "walk": {
                        "state": (
                            "Key unit cost metrics (cost per transaction, cost per user, "
                            "cost per GB) are defined and measured for primary products. "
                            "Metrics are reviewed regularly by product and finance teams. "
                            "Trends are tracked to identify cost efficiency changes."
                        ),
                        "indicators": (
                            "Core unit metrics defined (cost/transaction, cost/user) | "
                            "Metrics measured for primary products | Regular metric reviews | "
                            "Trend tracking in place | Product and finance alignment"
                        ),
                        "criteria": "Core unit cost metrics are defined, measured for primary products, and reviewed regularly by product and finance.",
                    },
                    "run": {
                        "state": (
                            "Unit economics metrics are comprehensive, covering all products "
                            "and services. Metrics are automated, real-time, and embedded in "
                            "engineering and product decision-making. Unit cost trends inform "
                            "architectural choices, pricing decisions, and strategic investment. "
                            "Metrics are comparable across teams and external benchmarks."
                        ),
                        "indicators": (
                            "Comprehensive unit metrics across all products | Real-time automated metrics | "
                            "Metrics embedded in engineering decisions | Inform pricing and investment | "
                            "Cross-team and external comparability | Linked to business KPIs"
                        ),
                        "criteria": "Automated, real-time unit economics metrics cover all products, inform engineering and pricing decisions, and enable external comparison.",
                    },
                },
            },
        ],
    },
    {
        "name": "Optimize Usage & Cost",
        "description": (
            "Reduce technology costs while maintaining or improving business value "
            "through architectural choices, rate optimisation, workload rightsizing, "
            "sustainable practices, and licence management."
        ),
        "capabilities": [
            {
                "key": "FO-OUC-01",
                "name": "Architecting for Cloud",
                "description": (
                    "Design cost-aware solutions and direct workload placement across "
                    "technology options to maximise business value. Encompasses evaluating "
                    "workloads for modernisation, re-platforming, and relocation while "
                    "maintaining alignment with operational objectives and cost effectiveness."
                ),
                "maturity": {
                    "crawl": {
                        "state": (
                            "Architecture decisions are made without cost consideration. "
                            "Workloads are deployed without evaluation of cost-optimal "
                            "placement options. No cost review occurs during design. "
                            "Cloud migration decisions ignore operating cost implications."
                        ),
                        "indicators": (
                            "No cost input into architecture decisions | No workload placement evaluation | "
                            "Migration decisions ignore OPEX | No cost-aware design patterns | "
                            "Post-deployment cost surprises common"
                        ),
                        "criteria": "Architecture decisions are made without cost consideration and no cost review occurs at design time.",
                    },
                    "walk": {
                        "state": (
                            "Cost is included as a design criterion alongside performance and "
                            "reliability. Architects use cost modelling tools for significant "
                            "workload decisions. Workload placement reviews include cost "
                            "comparison across options. Cost estimates are produced at "
                            "design review stage."
                        ),
                        "indicators": (
                            "Cost included in design criteria | Cost modelling at design stage | "
                            "Placement review includes cost comparison | Design review includes cost estimate | "
                            "Cost-aware patterns documented"
                        ),
                        "criteria": "Cost is a defined design criterion with cost estimates produced at design review for significant workloads.",
                    },
                    "run": {
                        "state": (
                            "Cost-aware architecture is standard practice embedded in design "
                            "governance. Architectural decisions include total cost of ownership "
                            "modelling across modernisation scenarios. Cost efficiency is a "
                            "continuous improvement target with metrics tracking architectural "
                            "debt and optimisation opportunities."
                        ),
                        "indicators": (
                            "Cost governance in architecture board | TCO modelling standard | "
                            "Modernisation scenarios evaluated | Architectural cost debt tracked | "
                            "Cost efficiency OKRs at architecture level | Continuous workload review"
                        ),
                        "criteria": "Cost-aware architecture with TCO modelling is embedded in governance; architectural cost debt is tracked and reduces continuously.",
                    },
                },
            },
            {
                "key": "FO-OUC-02",
                "name": "Rate Optimization",
                "description": (
                    "Manage the rates paid for consumed resources across technology "
                    "categories through negotiated discounts, commitment discounts "
                    "(Reserved Instances, Savings Plans), and other pricing mechanisms. "
                    "Balances discount coverage with usage flexibility."
                ),
                "maturity": {
                    "crawl": {
                        "state": (
                            "All resources are consumed at on-demand rates. No commitment "
                            "purchases are in place. Rate optimisation is not a defined "
                            "activity. The organisation has no visibility into discount "
                            "opportunity or coverage."
                        ),
                        "indicators": (
                            "100% on-demand pricing | No commitment discounts | "
                            "No rate optimisation process | Coverage metrics undefined | "
                            "Pricing models not understood"
                        ),
                        "criteria": "All consumption is at on-demand rates with no commitment discounts or rate optimisation activity.",
                    },
                    "walk": {
                        "state": (
                            "Commitment discounts (Reserved Instances, Savings Plans) are "
                            "purchased for stable baseline workloads. Coverage and utilisation "
                            "rates are measured. A defined process governs commitment purchases "
                            "with FinOps and finance approval. Expiry management prevents "
                            "discount lapses."
                        ),
                        "indicators": (
                            "Commitments purchased for stable workloads | Coverage rate tracked | "
                            "Utilisation rate tracked | Defined purchase approval process | "
                            "Expiry management in place | FinOps and finance sign-off"
                        ),
                        "criteria": "Commitment discounts are purchased for stable workloads with coverage and utilisation tracked and an approved purchase process.",
                    },
                    "run": {
                        "state": (
                            "Rate optimisation is a continuous process covering all discount "
                            "types including negotiated discounts, EDPs, and SaaS contracts. "
                            "Coverage and utilisation targets are set and met. Automated tools "
                            "recommend and initiate commitment purchases. Discount strategy "
                            "is integrated with capacity planning and engineering forecasts."
                        ),
                        "indicators": (
                            "All discount types managed | Automated purchase recommendations | "
                            "Coverage and utilisation targets met | EDP and negotiated discounts managed | "
                            "Integrated with capacity planning | Continuous optimisation cycle"
                        ),
                        "criteria": "All discount mechanisms are managed with automated recommendations, achieving coverage and utilisation targets, integrated with capacity planning.",
                    },
                },
            },
            {
                "key": "FO-OUC-03",
                "name": "Workload Optimization",
                "description": (
                    "Ensure resources across all FinOps scopes are properly selected, "
                    "correctly sized, run only when needed, appropriately configured, "
                    "and highly utilised. Applies rightsizing, waste reduction, workload "
                    "scheduling, and scaling to reduce cost while meeting requirements."
                ),
                "maturity": {
                    "crawl": {
                        "state": (
                            "No systematic rightsizing or waste reduction occurs. Resources "
                            "are provisioned at peak capacity and left running regardless of "
                            "demand. Idle and underutilised resources accumulate. Optimisation "
                            "is reactive and driven by cost spike incidents."
                        ),
                        "indicators": (
                            "No rightsizing process | Idle resources not addressed | "
                            "Over-provisioning is norm | Optimisation only after cost incidents | "
                            "No utilisation monitoring | Dev/test environments run 24/7"
                        ),
                        "criteria": "No systematic workload optimisation; resources are over-provisioned and idle resources accumulate without action.",
                    },
                    "walk": {
                        "state": (
                            "Rightsizing recommendations are generated and reviewed regularly. "
                            "Idle resource policies are defined and enforced for key environments. "
                            "Dev and test environments are scheduled to shut down out of hours. "
                            "Engineering teams action recommendations within defined SLAs."
                        ),
                        "indicators": (
                            "Regular rightsizing recommendations | Idle resource policy | "
                            "Dev/test scheduling enforced | Engineering actioning SLA defined | "
                            "Utilisation metrics tracked | Waste reporting to teams"
                        ),
                        "criteria": "Rightsizing recommendations are reviewed regularly with idle resource policies enforced and engineering actioning SLAs defined.",
                    },
                    "run": {
                        "state": (
                            "Workload optimisation is continuous and largely automated. "
                            "Auto-scaling and dynamic rightsizing are standard across the "
                            "estate. Utilisation targets are defined at team level and "
                            "tracked. Zero-waste engineering practices are embedded in "
                            "deployment pipelines. Sustainability is a co-equal optimisation goal."
                        ),
                        "indicators": (
                            "Auto-scaling standard across estate | Dynamic rightsizing automated | "
                            "Team-level utilisation targets | Zero-waste practices in CI/CD | "
                            "Sustainability co-equal goal | Continuous optimisation metrics"
                        ),
                        "criteria": "Automated, continuous workload optimisation with auto-scaling, team utilisation targets, and sustainability as a co-equal goal.",
                    },
                },
            },
            {
                "key": "FO-OUC-04",
                "name": "Cloud Sustainability",
                "description": (
                    "Integrate environmental impact assessment into FinOps activities, "
                    "balancing sustainability goals with financial optimisation. Requires "
                    "organisations to measure carbon emissions across technology categories "
                    "and incorporate sustainability data into cost reporting and decisions."
                ),
                "maturity": {
                    "crawl": {
                        "state": (
                            "Sustainability is not considered in cloud or technology decisions. "
                            "No carbon or emissions data is collected. No sustainability "
                            "objectives exist for technology operations. Cost and carbon "
                            "are treated as entirely separate concerns."
                        ),
                        "indicators": (
                            "No carbon data collected | No sustainability objectives | "
                            "Cost and carbon siloed | No sustainability reporting | "
                            "Provider sustainability tools unused"
                        ),
                        "criteria": "No sustainability consideration in technology decisions; carbon data is not collected or reported.",
                    },
                    "walk": {
                        "state": (
                            "Carbon emissions data is collected from primary cloud providers "
                            "and included in FinOps reporting. Sustainability targets are "
                            "defined at organisational level. Optimisation decisions consider "
                            "carbon impact alongside cost. Sustainability metrics are reported "
                            "to leadership."
                        ),
                        "indicators": (
                            "Provider carbon data collected | Sustainability targets defined | "
                            "Carbon in FinOps reporting | Optimisation decisions consider carbon | "
                            "Sustainability in leadership reporting"
                        ),
                        "criteria": "Carbon data from primary providers is included in FinOps reporting and leadership reviews, with sustainability targets defined.",
                    },
                    "run": {
                        "state": (
                            "Sustainability is a co-equal optimisation goal alongside cost. "
                            "Carbon data covers all technology sources. Workload placement "
                            "decisions factor in carbon intensity. Sustainability KPIs are "
                            "tracked and reported externally. The organisation demonstrates "
                            "measurable improvement in carbon efficiency year-on-year."
                        ),
                        "indicators": (
                            "All-source carbon data | Carbon-aware workload placement | "
                            "Sustainability KPIs externally reported | Year-on-year improvement tracked | "
                            "Carbon co-equal to cost in decisions | Green engineering practices embedded"
                        ),
                        "criteria": "Sustainability is a co-equal goal with cost, with all-source carbon data, carbon-aware placement, and externally reported KPIs.",
                    },
                },
            },
            {
                "key": "FO-OUC-05",
                "name": "Licensing & SaaS",
                "description": (
                    "Manage software licences and SaaS products to optimise costs while "
                    "maintaining compliance. Understand vendor licensing terms, purchasing "
                    "options, and usage patterns to avoid over-deployment risks and wasted "
                    "spending across engineering, finance, and procurement."
                ),
                "maturity": {
                    "crawl": {
                        "state": (
                            "Software licences and SaaS subscriptions are managed informally "
                            "and in silos. No central inventory exists. Licence compliance "
                            "is not monitored. Renewals are handled reactively. Significant "
                            "licence waste and duplicate subscriptions are common."
                        ),
                        "indicators": (
                            "No central licence inventory | Siloed management | "
                            "Compliance not monitored | Reactive renewals | "
                            "Duplicate SaaS subscriptions undetected | Waste unmeasured"
                        ),
                        "criteria": "Software licences are managed informally in silos with no central inventory or compliance monitoring.",
                    },
                    "walk": {
                        "state": (
                            "A central software asset inventory covers primary licences and "
                            "SaaS products. Usage is monitored and compared to licence "
                            "entitlements. Renewal calendar is maintained. Unused licences "
                            "are reclaimed. Procurement is involved in major licence decisions."
                        ),
                        "indicators": (
                            "Central licence inventory maintained | Usage vs entitlement tracked | "
                            "Renewal calendar active | Unused licence reclamation process | "
                            "Procurement involved in major decisions | Basic SaaS rationalisation"
                        ),
                        "criteria": "A central inventory tracks usage vs entitlements with a renewal calendar, unused licence reclamation, and procurement involvement.",
                    },
                    "run": {
                        "state": (
                            "Comprehensive licence and SaaS management is automated with real-time "
                            "usage monitoring, automated right-sizing recommendations, and "
                            "proactive renewal optimisation. Licence strategy is integrated with "
                            "cloud architecture decisions. SaaS sprawl is continuously monitored "
                            "and rationalised. Total software spend is a managed KPI."
                        ),
                        "indicators": (
                            "Automated usage monitoring and alerts | Right-sizing recommendations | "
                            "Proactive renewal optimisation | Licence strategy in architecture decisions | "
                            "SaaS sprawl KPI | Total software spend managed | Continuous rationalisation"
                        ),
                        "criteria": "Automated, comprehensive licence and SaaS management with proactive renewal optimisation and architecture integration.",
                    },
                },
            },
        ],
    },
    {
        "name": "Manage the FinOps Practice",
        "description": (
            "Build and sustain the organisational capabilities, governance structures, "
            "and cultural practices that enable a mature and effective FinOps function "
            "across teams, tools, education, and cross-discipline collaboration."
        ),
        "capabilities": [
            {
                "key": "FO-MFP-01",
                "name": "FinOps Practice Operations",
                "description": (
                    "Connect technology spending and usage to organisational business "
                    "strategy, enabling leaders to compare investment options and manage "
                    "trade-offs. Translates strategic priorities into aligned expectations, "
                    "measures, and behaviours across the organisation."
                ),
                "maturity": {
                    "crawl": {
                        "state": (
                            "FinOps activities are performed by individuals without an "
                            "established team structure or charter. No formal FinOps practice "
                            "exists. Activities are reactive and driven by cost incidents. "
                            "No executive sponsorship or defined scope."
                        ),
                        "indicators": (
                            "No formal FinOps team | No charter or mission | "
                            "Reactive cost activities only | No executive sponsor | "
                            "FinOps scope undefined | Ad hoc stakeholder engagement"
                        ),
                        "criteria": "FinOps activities occur reactively without a formal team structure, charter, or executive sponsorship.",
                    },
                    "walk": {
                        "state": (
                            "A FinOps team or centre of excellence is established with a "
                            "defined charter, scope, and executive sponsor. Team operates "
                            "with a regular cadence of stakeholder engagements. Processes "
                            "are documented. Success metrics are defined and tracked."
                        ),
                        "indicators": (
                            "FinOps team established | Charter and scope defined | "
                            "Executive sponsor identified | Regular stakeholder cadence | "
                            "Processes documented | Success metrics defined"
                        ),
                        "criteria": "A FinOps team is established with a charter, executive sponsor, regular cadence, and defined success metrics.",
                    },
                    "run": {
                        "state": (
                            "FinOps operates as a strategic function aligned to organisational "
                            "objectives. The practice is mature, continuously improving, and "
                            "demonstrably linked to business outcomes. FinOps is embedded in "
                            "planning cycles, investment decisions, and performance management. "
                            "Executive reporting includes FinOps KPIs."
                        ),
                        "indicators": (
                            "FinOps aligned to strategic objectives | Demonstrated business outcomes | "
                            "Embedded in planning cycles | Investment decisions include FinOps input | "
                            "FinOps KPIs in executive reporting | Mature continuous improvement process"
                        ),
                        "criteria": "FinOps is a strategic function embedded in planning, investment decisions, and executive reporting with demonstrated business outcomes.",
                    },
                },
            },
            {
                "key": "FO-MFP-02",
                "name": "Policy & Governance",
                "description": (
                    "Establish policies, controls, and governance mechanisms to ensure "
                    "technology use aligns with business objectives while managing financial "
                    "and operational risks. Encompasses policy definition, governance "
                    "structures, accountability, and risk management."
                ),
                "maturity": {
                    "crawl": {
                        "state": (
                            "No FinOps policies exist. Governance is informal and inconsistent. "
                            "Technology spending decisions are made without defined guardrails. "
                            "Risk related to cloud spending is not assessed or managed. "
                            "No accountability framework for cost management."
                        ),
                        "indicators": (
                            "No FinOps policies | Informal governance | "
                            "No spending guardrails | Cloud cost risk unassessed | "
                            "No accountability framework | Policy compliance unmeasured"
                        ),
                        "criteria": "No formal FinOps policies or governance structures exist; spending decisions have no defined guardrails.",
                    },
                    "walk": {
                        "state": (
                            "Core FinOps policies are defined covering tagging, budgets, "
                            "commitment purchases, and provisioning guardrails. Governance "
                            "structure assigns accountability for policy compliance. Exceptions "
                            "process exists. Policy compliance is measured and reported."
                        ),
                        "indicators": (
                            "Core policies defined (tagging, budgets, commitments) | "
                            "Accountability assigned | Exceptions process exists | "
                            "Compliance measured and reported | Policy review cadence"
                        ),
                        "criteria": "Core FinOps policies are defined with assigned accountability, a compliance measurement process, and an exceptions procedure.",
                    },
                    "run": {
                        "state": (
                            "FinOps policies are comprehensive, automated where possible, "
                            "and integrated into provisioning workflows. Governance is "
                            "embedded in organisational processes. Risk management is "
                            "proactive and data-driven. Policy compliance is near-complete "
                            "with automated enforcement and reporting."
                        ),
                        "indicators": (
                            "Comprehensive automated policies | Provisioning workflow integration | "
                            "Proactive risk management | Near-complete compliance | "
                            "Automated enforcement and reporting | Policy embedded in governance"
                        ),
                        "criteria": "Comprehensive automated FinOps policies are integrated into provisioning workflows with proactive risk management and near-complete compliance.",
                    },
                },
            },
            {
                "key": "FO-MFP-03",
                "name": "FinOps Assessment",
                "description": (
                    "Conduct repeatable, measurable, thoughtful analysis of the maturity "
                    "of a FinOps practice. Uses a structured three-phase approach — define "
                    "goals, set baseline, continuous assessment — to identify improvement "
                    "areas and track progress over time."
                ),
                "maturity": {
                    "crawl": {
                        "state": (
                            "No formal FinOps maturity assessment has been conducted. "
                            "The organisation has no baseline understanding of FinOps "
                            "capability maturity. Improvement areas are identified "
                            "informally based on cost incidents rather than structured assessment."
                        ),
                        "indicators": (
                            "No maturity assessment conducted | No FinOps baseline | "
                            "Capability gaps identified reactively | No structured methodology | "
                            "No improvement roadmap"
                        ),
                        "criteria": "No formal FinOps maturity assessment has been conducted and no baseline capability measurement exists.",
                    },
                    "walk": {
                        "state": (
                            "A FinOps maturity assessment has been completed using a recognised "
                            "framework (e.g. FinOps Foundation maturity model). A baseline is "
                            "established. Priority improvement areas are identified and a "
                            "roadmap is in place. Assessment is repeated annually."
                        ),
                        "indicators": (
                            "Formal assessment completed | Recognised framework used | "
                            "Baseline established | Priority gaps identified | "
                            "Improvement roadmap in place | Annual reassessment scheduled"
                        ),
                        "criteria": "A formal maturity assessment using a recognised framework is completed with a baseline, priority gaps, and an improvement roadmap.",
                    },
                    "run": {
                        "state": (
                            "FinOps maturity assessment is a continuous, integrated practice. "
                            "Self-assessment is supplemented by external benchmarking. "
                            "Maturity scores are tracked over time and inform strategic FinOps "
                            "investment. Assessment findings are directly linked to OKRs and "
                            "budgets. The organisation uses assessment data for peer comparison."
                        ),
                        "indicators": (
                            "Continuous self-assessment | External benchmarking | "
                            "Maturity trends tracked over time | Linked to OKRs and budgets | "
                            "Peer comparison available | Assessment drives strategic investment"
                        ),
                        "criteria": "Continuous, benchmarked maturity assessment drives strategic FinOps investment with maturity trends tracked and linked to OKRs.",
                    },
                },
            },
            {
                "key": "FO-MFP-04",
                "name": "FinOps Tools & Services",
                "description": (
                    "Evaluate and integrate software tools, automation solutions, and "
                    "professional services within the FinOps practice. Develop strategies "
                    "for selecting solutions, implementing them, and measuring ROI to "
                    "advance financial operations capability."
                ),
                "maturity": {
                    "crawl": {
                        "state": (
                            "FinOps tooling consists of basic cloud provider native tools "
                            "with no strategy for tool evaluation or selection. Tools are "
                            "adopted ad hoc based on immediate need. No ROI measurement "
                            "or tool effectiveness review occurs."
                        ),
                        "indicators": (
                            "Provider native tools only | Ad hoc tool adoption | "
                            "No tool strategy | No ROI measurement | "
                            "Tool selection uncoordinated | No tool inventory"
                        ),
                        "criteria": "FinOps relies on provider native tools adopted ad hoc with no strategy, inventory, or ROI measurement.",
                    },
                    "walk": {
                        "state": (
                            "A FinOps tool strategy is defined covering primary use cases. "
                            "Tool selection follows an evaluation process with defined criteria. "
                            "A tool inventory is maintained. ROI is measured for major tools. "
                            "Tool usage is monitored and reported."
                        ),
                        "indicators": (
                            "Tool strategy defined | Evaluation criteria documented | "
                            "Tool inventory maintained | ROI measured for major tools | "
                            "Tool usage monitored | Renewal decisions evidence-based"
                        ),
                        "criteria": "A FinOps tool strategy with an evaluation process, inventory, and ROI measurement covers primary use cases.",
                    },
                    "run": {
                        "state": (
                            "The FinOps tool ecosystem is comprehensive, integrated, and "
                            "continuously optimised. Tools are evaluated against strategic "
                            "requirements and total cost of ownership. Automation reduces "
                            "manual FinOps effort. Tool performance is a tracked KPI. "
                            "The organisation contributes to and benefits from the FinOps "
                            "community tool ecosystem."
                        ),
                        "indicators": (
                            "Comprehensive integrated tool ecosystem | TCO-based tool evaluation | "
                            "Automation reduces manual effort | Tool performance KPI | "
                            "Community tool contribution | Continuous optimisation of tooling"
                        ),
                        "criteria": "A comprehensive, integrated tool ecosystem is continuously optimised with automation reducing manual effort and TCO-based evaluation.",
                    },
                },
            },
            {
                "key": "FO-MFP-05",
                "name": "FinOps Education & Enablement",
                "description": (
                    "Enable everyone participating in a FinOps practice to develop a "
                    "common understanding of FinOps concepts, terminology, and practice. "
                    "Builds organisational accountability for costs through communications, "
                    "training, and centralised knowledge resources."
                ),
                "maturity": {
                    "crawl": {
                        "state": (
                            "FinOps knowledge is limited to a small number of practitioners. "
                            "No formal training or enablement programme exists. Engineering, "
                            "product, and finance teams have no shared FinOps vocabulary. "
                            "Awareness of FinOps principles is low across the organisation."
                        ),
                        "indicators": (
                            "Knowledge limited to FinOps team | No training programme | "
                            "No shared vocabulary | Low organisational awareness | "
                            "No FinOps community or forum | No knowledge repository"
                        ),
                        "criteria": "FinOps knowledge is siloed to practitioners with no training programme or shared organisational awareness.",
                    },
                    "walk": {
                        "state": (
                            "A FinOps onboarding programme introduces key stakeholders to "
                            "concepts and terminology. Role-specific training is available "
                            "for engineering, finance, and product teams. A FinOps community "
                            "of practice or forum exists. A knowledge base is maintained."
                        ),
                        "indicators": (
                            "Onboarding programme for key stakeholders | Role-specific training available | "
                            "Community of practice or forum | Knowledge base maintained | "
                            "Regular FinOps communications | Certification paths encouraged"
                        ),
                        "criteria": "A FinOps onboarding and role-specific training programme is in place with a community of practice and maintained knowledge base.",
                    },
                    "run": {
                        "state": (
                            "FinOps education is embedded in organisational culture. "
                            "All relevant personas have completed role-appropriate training. "
                            "A continuous learning programme keeps knowledge current. "
                            "FinOps champions exist across all major teams. Certification "
                            "is encouraged and supported. The organisation contributes to "
                            "industry FinOps knowledge."
                        ),
                        "indicators": (
                            "All relevant personas trained | Continuous learning programme | "
                            "FinOps champions in all major teams | Certification supported | "
                            "Industry contribution | FinOps embedded in culture | "
                            "Knowledge currency maintained"
                        ),
                        "criteria": "FinOps education is embedded in culture with all personas trained, champions in every team, certification supported, and industry contribution.",
                    },
                },
            },
            {
                "key": "FO-MFP-06",
                "name": "Invoicing & Chargeback",
                "description": (
                    "Manage cloud provider invoices and allocate costs through chargeback "
                    "models. Covers reconciling invoices, creating formal cost allocations "
                    "to departments, and establishing workflows between Finance, Accounting, "
                    "and FinOps teams."
                ),
                "maturity": {
                    "crawl": {
                        "state": (
                            "Cloud invoices are processed by finance without FinOps involvement "
                            "or detailed review. No chargeback model exists. Costs are allocated "
                            "as a shared overhead. Finance and FinOps operate without a "
                            "defined workflow or reconciliation process."
                        ),
                        "indicators": (
                            "Invoices processed without FinOps review | No chargeback | "
                            "Shared overhead allocation | No finance/FinOps workflow | "
                            "Invoice discrepancies undetected | Manual reconciliation"
                        ),
                        "criteria": "Cloud invoices are processed by finance without FinOps involvement and no chargeback model exists.",
                    },
                    "walk": {
                        "state": (
                            "FinOps and finance have a defined invoice reconciliation workflow. "
                            "A showback or chargeback model distributes costs to teams. "
                            "Invoice discrepancies are identified and tracked. Regular "
                            "reconciliation meetings occur between finance and FinOps."
                        ),
                        "indicators": (
                            "Defined reconciliation workflow | Showback or chargeback in place | "
                            "Discrepancy tracking | Regular finance/FinOps meetings | "
                            "Cost distributed to teams | Invoice accuracy reviewed"
                        ),
                        "criteria": "A defined reconciliation workflow and showback/chargeback model distributes costs to teams with regular finance/FinOps meetings.",
                    },
                    "run": {
                        "state": (
                            "Invoice reconciliation is automated and near-real-time. "
                            "A formal chargeback model with agreed methodology is applied "
                            "consistently across all technology costs. Teams receive timely, "
                            "accurate cost statements. Disputes are resolved through a "
                            "defined process. Chargeback drives cost accountability and "
                            "informs team budgeting."
                        ),
                        "indicators": (
                            "Automated reconciliation | Formal chargeback model agreed | "
                            "All technology costs charged back | Timely accurate cost statements | "
                            "Dispute resolution process | Chargeback drives team accountability"
                        ),
                        "criteria": "Automated, formal chargeback covers all technology costs, with timely cost statements, a dispute process, and chargeback driving team accountability.",
                    },
                },
            },
            {
                "key": "FO-MFP-07",
                "name": "Intersecting Disciplines",
                "description": (
                    "Coordinate FinOps activities with related IT disciplines including "
                    "IT Asset Management, IT Financial Management, and security. Aligns "
                    "cost management with asset management, financial management, and "
                    "platform engineering practices."
                ),
                "maturity": {
                    "crawl": {
                        "state": (
                            "FinOps operates in isolation from related disciplines. ITAM, "
                            "ITFM, security, and platform engineering teams have no defined "
                            "interaction with FinOps. Data and processes are duplicated or "
                            "contradictory. Cross-discipline alignment does not occur."
                        ),
                        "indicators": (
                            "FinOps siloed from ITAM/ITFM/security | No cross-discipline workflows | "
                            "Duplicated data and processes | Contradictory reporting | "
                            "No shared frameworks or metrics | Alignment meetings absent"
                        ),
                        "criteria": "FinOps operates in isolation from related disciplines with no defined interactions or shared processes.",
                    },
                    "walk": {
                        "state": (
                            "Defined touchpoints exist between FinOps and key related disciplines. "
                            "Data sharing agreements cover primary overlap areas. Joint processes "
                            "are documented for shared activities (e.g. ITAM licence reconciliation, "
                            "ITFM cost model alignment). Regular cross-discipline meetings occur."
                        ),
                        "indicators": (
                            "Defined touchpoints with ITAM, ITFM, security | Data sharing agreements | "
                            "Joint processes for shared activities | Regular cross-discipline meetings | "
                            "Shared metrics where applicable"
                        ),
                        "criteria": "Defined touchpoints, data sharing agreements, and joint processes exist with key related disciplines.",
                    },
                    "run": {
                        "state": (
                            "FinOps is fully integrated with all relevant disciplines into a "
                            "cohesive technology management ecosystem. Shared data models, "
                            "governance frameworks, and automation span disciplines. FinOps "
                            "contributes to and benefits from ITAM, ITFM, security, and "
                            "platform engineering in a continuous, value-generating feedback loop."
                        ),
                        "indicators": (
                            "Fully integrated cross-discipline ecosystem | Shared data models | "
                            "Shared governance frameworks | Cross-discipline automation | "
                            "FinOps embedded in ITAM/ITFM/security workflows | Continuous value exchange"
                        ),
                        "criteria": "FinOps is fully integrated across all relevant disciplines with shared data models, governance, and automation in a continuous value-generating loop.",
                    },
                },
            },
        ],
    },
]

# ---------------------------------------------------------------------------
# FinOps starter use cases
# ---------------------------------------------------------------------------
# Domain key prefixes used to assign impact weights:
#   weight 5 = Core domain for this use case
#   weight 3 = Complementary domain
#   weight 1 = Context / background
# ---------------------------------------------------------------------------

FINOPS_USE_CASES = [
    {
        "title": "Cloud Cost Baseline Assessment",
        "description": (
            "Establish a comprehensive baseline of FinOps capability maturity across "
            "all four domains. Provides an organisation-wide view of current cloud "
            "financial management practices, gaps, and quick wins."
        ),
        "business_value": (
            "Delivers a defensible, structured view of current FinOps posture for "
            "leadership and board reporting. Identifies highest-priority investment "
            "areas to reduce cloud waste and improve financial accountability."
        ),
        "owner_role": "FinOps Lead / Head of Cloud",
        # domain_name → weight; all 4 domains are core (balanced assessment)
        "domain_weights": {
            "Understand Usage & Cost":   5,
            "Quantify Business Value":   5,
            "Optimize Usage & Cost":     5,
            "Manage the FinOps Practice": 5,
        },
    },
    {
        "title": "Cloud Optimisation Focus",
        "description": (
            "Deep-dive assessment of cost reduction and optimisation capability "
            "maturity. Focuses on rate optimisation, workload rightsizing, "
            "architectural cost-awareness, and the foundational data visibility "
            "required to act on optimisation opportunities."
        ),
        "business_value": (
            "Identifies immediate and structural opportunities to reduce cloud spend "
            "through commitment discounts, rightsizing, and cost-aware architecture. "
            "Typically surfaces 15-30% cost reduction opportunities."
        ),
        "owner_role": "Head of Cloud Engineering / Platform",
        "domain_weights": {
            "Optimize Usage & Cost":     5,
            "Understand Usage & Cost":   3,
            "Quantify Business Value":   3,
            "Manage the FinOps Practice": 1,
        },
    },
    {
        "title": "FinOps Practice Maturity",
        "description": (
            "Assess the organisational and governance maturity of the FinOps practice "
            "itself — policies, tooling, education, operations, and cross-discipline "
            "integration. Supported by business value quantification to demonstrate "
            "practice ROI to leadership."
        ),
        "business_value": (
            "Establishes a roadmap for building a sustainable, high-impact FinOps "
            "practice. Demonstrates to leadership that FinOps is a managed discipline "
            "with measurable outcomes, accelerating investment and adoption."
        ),
        "owner_role": "CTO / CFO / FinOps Practice Lead",
        "domain_weights": {
            "Manage the FinOps Practice": 5,
            "Quantify Business Value":    3,
            "Understand Usage & Cost":    1,
            "Optimize Usage & Cost":      1,
        },
    },
]

# ---------------------------------------------------------------------------
# Maturity level mapping: FinOps uses Crawl / Walk / Run
# Map to Next_CapabilityLevel.level = 1, 3, 5 to maintain compatibility with
# the existing 1-5 scoring engine. Levels 2 and 4 are not seeded for FinOps.
# ---------------------------------------------------------------------------
LEVEL_MAP = {
    "crawl": (1, "Crawl"),
    "walk":  (3, "Walk"),
    "run":   (5, "Run"),
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def table_exists(conn, table: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


# ---------------------------------------------------------------------------
# Seed functions
# ---------------------------------------------------------------------------

def seed_framework_registry(conn, dry_run: bool = False) -> int:
    """Register FinOps Foundation in Next_Framework. Returns framework_id."""
    print("\n[1] Registering FinOps Foundation in Next_Framework")

    existing = conn.execute(
        "SELECT id FROM Next_Framework WHERE framework_key = 'FINOPS_FOUNDATION'"
    ).fetchone()

    if existing:
        fw_id = existing[0]
        print(f"  . Already registered as framework_id = {fw_id}")
        return fw_id

    if dry_run:
        print("  [dry-run] Would INSERT FINOPS_FOUNDATION into Next_Framework")
        return -1

    conn.execute("""
        INSERT INTO Next_Framework (
            framework_key, framework_name, version, status,
            is_native, label_level1, label_level2, label_level3
        ) VALUES (
            'FINOPS_FOUNDATION',
            'FinOps Foundation Framework',
            '2025',
            'active',
            0,
            'Framework',
            'Domain',
            'Capability'
        )
    """)
    fw_id = conn.execute(
        "SELECT id FROM Next_Framework WHERE framework_key = 'FINOPS_FOUNDATION'"
    ).fetchone()[0]
    print(f"  + Registered as framework_id = {fw_id}")
    return fw_id


def seed_taxonomy(conn, fw_id: int, dry_run: bool = False):
    """Seed the pillar, domains, capabilities, and maturity levels."""
    print("\n[2] Seeding taxonomy (Pillar → Domains → Capabilities)")

    pillar_id = None
    domain_map = {}   # domain_name → subdomain_id
    cap_map = {}      # cap_key → capability_id
    caps_total = 0
    levels_total = 0

    # --- Pillar (single Next_Domain row) ---
    existing_pillar = conn.execute(
        "SELECT id FROM Next_Domain WHERE domain_name = ? AND framework_id = ?",
        (FINOPS_PILLAR["name"], fw_id)
    ).fetchone()

    if existing_pillar:
        pillar_id = existing_pillar[0]
        print(f"  . Pillar already exists: id={pillar_id}")
    elif dry_run:
        pillar_id = -1
        print(f"  [dry-run] Would INSERT pillar: {FINOPS_PILLAR['name']}")
    else:
        conn.execute("""
            INSERT INTO Next_Domain (domain_name, domain_description, framework_id, version)
            VALUES (?, ?, ?, 'FinOps_2025')
        """, (FINOPS_PILLAR["name"], FINOPS_PILLAR["description"], fw_id))
        pillar_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        print(f"  + Pillar: {FINOPS_PILLAR['name']} (id={pillar_id})")

    # --- Domains (Next_SubDomain rows) ---
    for domain in FINOPS_TAXONOMY:
        existing_domain = conn.execute(
            "SELECT id FROM Next_SubDomain WHERE subdomain_name = ? AND domain_id = ?",
            (domain["name"], pillar_id)
        ).fetchone()

        if existing_domain:
            domain_id = existing_domain[0]
        elif dry_run:
            domain_id = -1
            print(f"  [dry-run] Would INSERT domain: {domain['name']}")
        else:
            conn.execute("""
                INSERT INTO Next_SubDomain (domain_id, subdomain_name, subdomain_description, framework_id)
                VALUES (?, ?, ?, ?)
            """, (pillar_id, domain["name"], domain["description"], fw_id))
            domain_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            print(f"  + Domain: {domain['name']} (id={domain_id})")

        domain_map[domain["name"]] = domain_id

        # --- Capabilities (Next_Capability rows) ---
        for cap in domain["capabilities"]:
            existing_cap = conn.execute(
                "SELECT id FROM Next_Capability WHERE capability_name = ? AND framework_id = ?",
                (cap["key"], fw_id)
            ).fetchone()

            if existing_cap:
                cap_id = existing_cap[0]
            elif dry_run:
                cap_id = -1
                caps_total += 1
                print(f"    [dry-run] Would INSERT capability: {cap['name']}")
            else:
                conn.execute("""
                    INSERT INTO Next_Capability (
                        domain_id, subdomain_id, capability_name,
                        capability_description, framework_id, category
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (pillar_id, domain_id, cap["key"], cap["description"], fw_id, cap["name"]))
                cap_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                caps_total += 1

            cap_map[cap["key"]] = cap_id

            # --- Maturity levels (Next_CapabilityLevel rows) ---
            for maturity_key, (level_num, level_name) in LEVEL_MAP.items():
                m = cap["maturity"][maturity_key]

                existing_level = conn.execute(
                    "SELECT id FROM Next_CapabilityLevel "
                    "WHERE capability_id = ? AND level = ? AND framework_id = ?",
                    (cap_id, level_num, fw_id)
                ).fetchone()

                if existing_level or dry_run or cap_id == -1:
                    if not existing_level and dry_run:
                        levels_total += 1
                    continue

                conn.execute("""
                    INSERT INTO Next_CapabilityLevel (
                        capability_id, level, level_name,
                        capability_state, key_indicators, scoring_criteria, framework_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    cap_id, level_num, level_name,
                    m["state"], m["indicators"], m["criteria"], fw_id
                ))
                levels_total += 1

    if dry_run:
        print(f"\n  [dry-run] Would seed {caps_total} capabilities and ~{caps_total * 3} maturity levels")
    else:
        print(f"\n  ✓ {caps_total} capabilities seeded")
        print(f"  ✓ {levels_total} maturity level descriptors seeded (Crawl/Walk/Run)")

    return pillar_id, domain_map, cap_map


def seed_use_cases(conn, fw_id: int, cap_map: dict, dry_run: bool = False) -> None:
    """Seed the 3 FinOps starter use cases into Next_UseCase and Next_UseCaseCapabilityImpact."""
    print("\n[3] Seeding starter use cases")

    # Build domain_name → [cap_keys] lookup from the taxonomy
    domain_caps: dict[str, list[str]] = {}
    for domain in FINOPS_TAXONOMY:
        domain_caps[domain["name"]] = [cap["key"] for cap in domain["capabilities"]]

    for uc in FINOPS_USE_CASES:
        existing = conn.execute(
            "SELECT id FROM Next_UseCase WHERE usecase_title = ? AND framework_id = ?",
            (uc["title"], fw_id)
        ).fetchone()

        if existing:
            print(f"  . Already exists: {uc['title']}")
            continue

        if dry_run:
            print(f"  [dry-run] Would INSERT use case: {uc['title']}")
            continue

        conn.execute("""
            INSERT INTO Next_UseCase (
                usecase_title, usecase_description, business_value, owner_role,
                framework_id, version
            ) VALUES (?, ?, ?, ?, ?, 'FinOps_2025')
        """, (uc["title"], uc["description"], uc["business_value"], uc["owner_role"], fw_id))
        uc_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        caps_inserted = 0
        for domain_name, weight in uc["domain_weights"].items():
            for cap_key in domain_caps.get(domain_name, []):
                cap_id = cap_map.get(cap_key)
                if cap_id and cap_id != -1:
                    conn.execute("""
                        INSERT OR IGNORE INTO Next_UseCaseCapabilityImpact
                        (usecase_id, capability_id, impact_weight, maturity_target, feasibility_score)
                        VALUES (?, ?, ?, 3, 3)
                    """, (uc_id, cap_id, weight))
                    caps_inserted += 1

        print(f"  + {uc['title']} ({caps_inserted} capability weights)")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Seed FinOps Foundation Framework into meridant_frameworks.db")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen, no DB writes")
    parser.add_argument("--use-cases-only", action="store_true", help="Seed use cases only (taxonomy must exist)")
    args = parser.parse_args()

    print("Meridant Matrix — FinOps Foundation Framework Seed")
    print(f"DB : {FRAMEWORKS_DB}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}\n")
    print("Attribution: FinOps Framework © FinOps Foundation (https://www.finops.org), CC BY 4.0")
    print()

    if not Path(FRAMEWORKS_DB).exists():
        print(f"ERROR: {FRAMEWORKS_DB} not found")
        print("Check MERIDANT_FRAMEWORKS_DB_PATH env var")
        sys.exit(1)

    conn = sqlite3.connect(FRAMEWORKS_DB)
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL mode omitted — Windows Docker bind mounts don't support .shm file creation

    try:
        fw_id = seed_framework_registry(conn, dry_run=args.dry_run)
        if not args.dry_run:
            conn.commit()

        if args.use_cases_only:
            # Taxonomy must already exist — load cap_map from DB
            rows = conn.execute(
                "SELECT capability_name, id FROM Next_Capability WHERE framework_id = ?", (fw_id,)
            ).fetchall()
            cap_map = {r[0]: r[1] for r in rows}
            pillar_id = None
            domain_map = {}
        else:
            pillar_id, domain_map, cap_map = seed_taxonomy(conn, fw_id, dry_run=args.dry_run)
            if not args.dry_run:
                conn.commit()

        seed_use_cases(conn, fw_id, cap_map, dry_run=args.dry_run)
        if not args.dry_run:
            conn.commit()

        # --- Summary ---
        print(f"\n{'='*60}")
        if args.dry_run:
            print("DRY RUN complete — no DB changes made")
        else:
            print("FinOps Foundation Framework seed complete")

            # Verify row counts
            fw_row = conn.execute(
                "SELECT id, framework_key, framework_name, version FROM Next_Framework WHERE id = ?",
                (fw_id,)
            ).fetchone()
            pillar_count = conn.execute(
                "SELECT COUNT(*) FROM Next_Domain WHERE framework_id = ?", (fw_id,)
            ).fetchone()[0]
            domain_count = conn.execute(
                "SELECT COUNT(*) FROM Next_SubDomain WHERE framework_id = ?", (fw_id,)
            ).fetchone()[0]
            cap_count = conn.execute(
                "SELECT COUNT(*) FROM Next_Capability WHERE framework_id = ?", (fw_id,)
            ).fetchone()[0]
            level_count = conn.execute(
                "SELECT COUNT(*) FROM Next_CapabilityLevel WHERE framework_id = ?", (fw_id,)
            ).fetchone()[0]

            print(f"{'='*60}")
            print(f"framework_id   : {fw_row[0]}")
            print(f"framework_key  : {fw_row[1]}")
            print(f"framework_name : {fw_row[2]}")
            print(f"version        : {fw_row[3]}")
            print(f"Labels         : Framework / Domain / Capability")
            print(f"{'='*60}")
            print(f"Next_Domain    : {pillar_count} row(s)  (1 Pillar)")
            print(f"Next_SubDomain : {domain_count} row(s)  (4 Domains)")
            print(f"Next_Capability: {cap_count} row(s)  (capabilities)")
            uc_count = conn.execute(
                "SELECT COUNT(*) FROM Next_UseCase WHERE framework_id = ?", (fw_id,)
            ).fetchone()[0]
            print(f"Next_CapLevel  : {level_count} row(s)  (Crawl/Walk/Run at L1/L3/L5)")
            print(f"Next_UseCase   : {uc_count} row(s)  (starter use cases)")
            print(f"{'='*60}")

            # Domain breakdown
            print("\nDomain breakdown:")
            for dname, did in sorted(domain_map.items(), key=lambda x: x[1]):
                n = conn.execute(
                    "SELECT COUNT(*) FROM Next_Capability WHERE subdomain_id = ? AND framework_id = ?",
                    (did, fw_id)
                ).fetchone()[0]
                print(f"  {dname}: {n} capabilities")

    except Exception as e:
        print(f"\nERROR: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
