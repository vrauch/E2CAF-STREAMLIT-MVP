from __future__ import annotations

# -----------------------------
# Framework helpers (multi-framework support)
# -----------------------------

def get_frameworks(client) -> list:
    """Return all active frameworks for the framework selector."""
    result = client.query(
        "SELECT id, framework_key, framework_name, label_level1, label_level2, label_level3 "
        "FROM Next_Framework WHERE status = 'active' ORDER BY id",
        []
    )
    return result.get("rows", [])


def get_framework_labels(client, framework_id: int) -> dict:
    """Return display labels for a given framework_id.
    Returns dict with keys level1/level2/level3.
    Falls back to MMTF labels if not found.
    """
    result = client.query(
        "SELECT label_level1, label_level2, label_level3 FROM Next_Framework WHERE id = ?",
        [int(framework_id)]
    )
    rows = result.get("rows", [])
    if rows:
        return {
            "level1": rows[0]["label_level1"],
            "level2": rows[0]["label_level2"],
            "level3": rows[0]["label_level3"],
        }
    return {"level1": "Pillar", "level2": "Domain", "level3": "Capability"}


def get_domains_for_framework(client, framework_id: int) -> list:
    """Return all Pillars/Functions for a given framework."""
    result = client.query(
        "SELECT id, domain_name FROM Next_Domain WHERE framework_id = ? ORDER BY id",
        [int(framework_id)]
    )
    return result.get("rows", [])


def get_subdomains_for_framework(client, framework_id: int, domain_id: int = None) -> list:
    """Return Domains/Categories for a framework, optionally filtered by Pillar."""
    if domain_id:
        result = client.query(
            "SELECT id, domain_id, subdomain_name FROM Next_SubDomain "
            "WHERE framework_id = ? AND domain_id = ? ORDER BY id",
            [int(framework_id), int(domain_id)]
        )
    else:
        result = client.query(
            "SELECT id, domain_id, subdomain_name FROM Next_SubDomain "
            "WHERE framework_id = ? ORDER BY id",
            [int(framework_id)]
        )
    return result.get("rows", [])


def get_capabilities_for_framework(client, framework_id: int, subdomain_id: int = None) -> list:
    """Return Capabilities/Subcategories for a framework, optionally filtered by Domain."""
    if subdomain_id:
        result = client.query(
            "SELECT id, domain_id, subdomain_id, capability_name, capability_description "
            "FROM Next_Capability WHERE framework_id = ? AND subdomain_id = ? ORDER BY id",
            [int(framework_id), int(subdomain_id)]
        )
    else:
        result = client.query(
            "SELECT id, domain_id, subdomain_id, capability_name, capability_description "
            "FROM Next_Capability WHERE framework_id = ? ORDER BY id",
            [int(framework_id)]
        )
    return result.get("rows", [])


def get_use_cases_for_framework(client, framework_id: int) -> list:
    """Return use cases for a given framework."""
    result = client.query(
        "SELECT id, usecase_title, "
        "COALESCE(usecase_description, '') AS usecase_description, "
        "COALESCE(business_value, '') AS business_value, "
        "COALESCE(owner_role, '') AS owner_role "
        "FROM Next_UseCase WHERE framework_id = ? ORDER BY usecase_title",
        [int(framework_id)]
    )
    return result.get("rows", [])


def get_capability_levels_for_framework(client, capability_id: int, framework_id: int) -> list:
    """Return L1–L5 descriptors for a capability, filtered by framework."""
    result = client.query(
        "SELECT level, level_name, capability_state, key_indicators, scoring_criteria "
        "FROM Next_CapabilityLevel "
        "WHERE capability_id = ? AND framework_id = ? AND level_name IS NOT NULL "
        "ORDER BY level",
        [int(capability_id), int(framework_id)]
    )
    return result.get("rows", [])


# -----------------------------
# Reference data
# -----------------------------
def q_list_next_usecases(limit: int = 200, framework_id: int = None) -> str:
    fw_filter = f"WHERE framework_id = {int(framework_id)}" if framework_id else ""
    return f"SELECT id, usecase_title FROM Next_UseCase {fw_filter} ORDER BY id LIMIT {int(limit)};"

def q_list_tags() -> str:
    return "SELECT id, tag_name, tag_description FROM Next_CapabilityTag ORDER BY tag_name;"

def q_list_capabilities(limit: int = 5000) -> str:
    return f"""
    SELECT
      c.id,
      c.capability_name,
      d.domain_name,
      sd.subdomain_name
    FROM Next_Capability c
    LEFT JOIN Next_Domain d ON c.domain_id = d.id
    LEFT JOIN Next_SubDomain sd ON c.subdomain_id = sd.id
    ORDER BY c.capability_name, d.domain_name, sd.subdomain_name, c.id
    LIMIT {int(limit)};
    """

def q_list_capabilities_for_usecase(usecase_id: int, limit: int = 2000) -> str:
    return f"""
    SELECT
      c.id,
      c.capability_name,
      d.domain_name,
      sd.subdomain_name,
      MIN(u.src_rank) AS relevance_bucket
    FROM (
        SELECT DISTINCT capability_id, 1 AS src_rank
        FROM Next_RoadmapStep
        WHERE usecase_id = {int(usecase_id)}
      UNION
        SELECT DISTINCT c2.id AS capability_id, 2 AS src_rank
        FROM Next_UseCaseIntent ui
        JOIN Next_CapabilityTagMap ctm ON ui.intent_tag_id = ctm.tag_id
        JOIN Next_Capability c2 ON ctm.capability_id = c2.id
        WHERE ui.usecase_id = {int(usecase_id)}
      UNION
        SELECT c3.id AS capability_id, 3 AS src_rank
        FROM Next_Capability c3
    ) u
    JOIN Next_Capability c ON c.id = u.capability_id
    LEFT JOIN Next_Domain d ON c.domain_id = d.id
    LEFT JOIN Next_SubDomain sd ON c.subdomain_id = sd.id
    GROUP BY c.id, c.capability_name, d.domain_name, sd.subdomain_name
    ORDER BY
      relevance_bucket ASC,
      c.capability_name ASC,
      d.domain_name ASC,
      sd.subdomain_name ASC,
      c.id ASC
    LIMIT {int(limit)};
    """
# -----------------------------
# Intent
# -----------------------------
def q_get_usecase_intent(usecase_id: int) -> str:
    return f"""
    SELECT ui.id, ui.intent_tag_id AS tag_id, t.tag_name, ui.weight, ui.source, ui.created_on
    FROM Next_UseCaseIntent ui
    JOIN Next_CapabilityTag t ON ui.intent_tag_id = t.id
    WHERE ui.usecase_id = {int(usecase_id)}
    ORDER BY ui.weight DESC, t.tag_name;
    """

def w_replace_usecase_intent(usecase_id: int, tag_weights: dict[int, int], source: str = "ui") -> str:
    statements = [f"DELETE FROM Next_UseCaseIntent WHERE usecase_id={int(usecase_id)};"]
    for tag_id, weight in tag_weights.items():
        statements.append(
            f"INSERT INTO Next_UseCaseIntent (usecase_id, intent_tag_id, weight, source) "
            f"VALUES ({int(usecase_id)}, {int(tag_id)}, {int(weight)}, '{source.replace("'","''")}');"
        )
    return "\n".join(statements)

# -----------------------------
# Capability discovery
# -----------------------------
def q_discover_capabilities(usecase_id: int, limit: int = 50) -> str:
    return f"""
    SELECT
        c.id AS capability_id,
        c.capability_name,
        d.domain_name,
        sd.subdomain_name,
        COUNT(DISTINCT ui.intent_tag_id) AS relevance_score
    FROM Next_UseCaseIntent ui
    JOIN Next_CapabilityTagMap ctm ON ui.intent_tag_id = ctm.tag_id
    JOIN Next_Capability c ON ctm.capability_id = c.id
    JOIN Next_Domain d ON c.domain_id = d.id
    JOIN Next_SubDomain sd ON c.subdomain_id = sd.id
    WHERE ui.usecase_id = {int(usecase_id)}
    GROUP BY c.id
    ORDER BY relevance_score DESC, c.capability_name
    LIMIT {int(limit)};
    """

# -----------------------------
# Roadmap
# -----------------------------
def w_init_target_maturity(usecase_id: int, dimension_id: int = 1, target_score: int = 3) -> str:
    return f"""
    INSERT INTO Next_TargetMaturity (usecase_id, capability_id, dimension_id, target_score)
    SELECT {int(usecase_id)}, c.id, {int(dimension_id)}, {int(target_score)}
    FROM Next_Capability c
    WHERE NOT EXISTS (
      SELECT 1 FROM Next_TargetMaturity tm
      WHERE tm.usecase_id = {int(usecase_id)} AND tm.capability_id = c.id AND tm.dimension_id = {int(dimension_id)}
    );
    """

def w_generate_roadmap(usecase_id: int) -> str:
    return f"""
    DELETE FROM Next_RoadmapStep WHERE usecase_id={int(usecase_id)};

    INSERT INTO Next_RoadmapStep (usecase_id, capability_id, phase, priority_score)
    SELECT
      {int(usecase_id)},
      ranked.capability_id,
      CASE
        WHEN ranked.priority_score >= 8 THEN 1
        WHEN ranked.priority_score >= 5 THEN 2
        WHEN ranked.priority_score >= 3 THEN 3
        ELSE 4
      END,
      ranked.priority_score
    FROM (
      SELECT
        c.id AS capability_id,
        COUNT(DISTINCT ui.intent_tag_id) AS intent_score,
        (tm.target_score - COALESCE(ma.maturity_score,0)) AS maturity_gap,
        COUNT(DISTINCT ci.target_capability_id) AS dependency_weight,
        (
          COUNT(DISTINCT ui.intent_tag_id)
          + (tm.target_score - COALESCE(ma.maturity_score,0))
          + COUNT(DISTINCT ci.target_capability_id)
        ) AS priority_score
      FROM Next_Capability c
      LEFT JOIN Next_CapabilityTagMap ctm ON c.id = ctm.capability_id
      LEFT JOIN Next_UseCaseIntent ui ON ui.intent_tag_id = ctm.tag_id AND ui.usecase_id = {int(usecase_id)}
      LEFT JOIN Next_TargetMaturity tm ON tm.capability_id = c.id AND tm.usecase_id = {int(usecase_id)}
      LEFT JOIN Next_MaturityAssessment ma ON ma.capability_id = c.id
      LEFT JOIN Next_CapabilityInterdependency ci ON ci.source_capability_id = c.id
      GROUP BY c.id
    ) ranked;
    """

def q_roadmap_phase_counts(usecase_id: int) -> str:
    return f"""
    SELECT phase, COUNT(*) AS capability_count
    FROM Next_RoadmapStep
    WHERE usecase_id={int(usecase_id)}
    GROUP BY phase
    ORDER BY phase;
    """

def q_roadmap_steps(usecase_id: int, limit: int = 500) -> str:
    return f"""
    SELECT rs.phase, rs.priority_score, c.capability_name
    FROM Next_RoadmapStep rs
    JOIN Next_Capability c ON rs.capability_id = c.id
    WHERE rs.usecase_id={int(usecase_id)}
    ORDER BY rs.phase, rs.priority_score DESC, c.capability_name
    LIMIT {int(limit)};
    """

def w_generate_cluster_roadmap(usecase_id: int) -> str:
    return f"""
    DELETE FROM Next_RoadmapClusterStep WHERE usecase_id={int(usecase_id)};

    INSERT INTO Next_RoadmapClusterStep (usecase_id, cluster_id, phase, priority_score, capability_count)
    SELECT
      {int(usecase_id)},
      cm.cluster_id,
      CASE
        WHEN AVG(rs.priority_score) >= 8 THEN 1
        WHEN AVG(rs.priority_score) >= 5 THEN 2
        WHEN AVG(rs.priority_score) >= 3 THEN 3
        ELSE 4
      END,
      AVG(rs.priority_score),
      COUNT(*)
    FROM Next_RoadmapStep rs
    JOIN Next_CapabilityClusterMap cm ON rs.capability_id = cm.capability_id
    WHERE rs.usecase_id = {int(usecase_id)}
    GROUP BY cm.cluster_id;
    """

def q_cluster_roadmap(usecase_id: int) -> str:
    return f"""
    SELECT c.cluster_name, r.phase, r.capability_count, ROUND(r.priority_score,2) AS avg_priority
    FROM Next_RoadmapClusterStep r
    JOIN Next_CapabilityCluster c ON r.cluster_id=c.id
    WHERE r.usecase_id={int(usecase_id)}
    ORDER BY r.phase, r.priority_score DESC;
    """

# -----------------------------
# Investment optimization (MVP)
# -----------------------------
def w_run_investment(usecase_id: int, budget: float) -> str:
    return f"""
    INSERT INTO Next_InvestmentRun (usecase_id, budget, cost_model)
    VALUES ({int(usecase_id)}, {float(budget)}, 'default-unit-cost');

    DELETE FROM Next_InvestmentSelection
    WHERE run_id = (SELECT id FROM Next_InvestmentRun ORDER BY id DESC LIMIT 1);

    INSERT INTO Next_InvestmentSelection (run_id, capability_id, selected_order, estimated_cost, benefit_score, benefit_per_cost)
    SELECT
      (SELECT id FROM Next_InvestmentRun ORDER BY id DESC LIMIT 1),
      ranked.capability_id,
      ROW_NUMBER() OVER (ORDER BY ranked.benefit_per_cost DESC),
      ranked.estimated_cost,
      ranked.benefit_score,
      ranked.benefit_per_cost
    FROM (
      SELECT
        c.id AS capability_id,
        ic.estimated_cost,
        (
          COUNT(DISTINCT ui.intent_tag_id)
          + (tm.target_score - COALESCE(ma.maturity_score,0))
          + COUNT(DISTINCT ci.target_capability_id)
        ) AS benefit_score,
        (
          (
            COUNT(DISTINCT ui.intent_tag_id)
            + (tm.target_score - COALESCE(ma.maturity_score,0))
            + COUNT(DISTINCT ci.target_capability_id)
          ) / ic.estimated_cost
        ) AS benefit_per_cost
      FROM Next_Capability c
      JOIN Next_CapabilityInvestmentCost ic ON ic.capability_id = c.id
      LEFT JOIN Next_CapabilityTagMap ctm ON c.id = ctm.capability_id
      LEFT JOIN Next_UseCaseIntent ui ON ui.intent_tag_id = ctm.tag_id AND ui.usecase_id = {int(usecase_id)}
      LEFT JOIN Next_TargetMaturity tm ON tm.capability_id = c.id AND tm.usecase_id = {int(usecase_id)}
      LEFT JOIN Next_MaturityAssessment ma ON ma.capability_id = c.id
      LEFT JOIN Next_CapabilityInterdependency ci ON ci.source_capability_id = c.id
      GROUP BY c.id
    ) ranked
    WHERE ranked.benefit_per_cost > 0
    LIMIT 20;
    """

def q_latest_investment_selection(usecase_id: int) -> str:
    return f"""
    SELECT
      c.capability_name,
      s.selected_order,
      s.estimated_cost,
      s.benefit_score,
      s.benefit_per_cost
    FROM Next_InvestmentSelection s
    JOIN Next_Capability c ON s.capability_id=c.id
    WHERE s.run_id = (SELECT id FROM Next_InvestmentRun WHERE usecase_id={int(usecase_id)} ORDER BY id DESC LIMIT 1)
    ORDER BY s.selected_order;
    """

# -----------------------------
# Executive strategy (MVP)
# -----------------------------
def w_generate_executive_strategy(usecase_id: int, title: str) -> str:
    safe_title = title.replace("'", "''")
    return f"""
    CREATE TABLE IF NOT EXISTS Next_ExecutiveStrategy (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      usecase_id INTEGER NOT NULL,
      strategy_title TEXT,
      transformation_vision TEXT,
      strategic_priorities TEXT,
      roadmap_summary TEXT,
      investment_summary TEXT,
      risk_summary TEXT,
      outcome_summary TEXT,
      created_on DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    INSERT INTO Next_ExecutiveStrategy (
      usecase_id, strategy_title, transformation_vision,
      strategic_priorities, roadmap_summary, investment_summary,
      risk_summary, outcome_summary
    )
    VALUES (
      {int(usecase_id)},
      '{safe_title}',
      'Establish a secure, automated platform aligned to the selected use case.',
      'Top clusters and investments drive the highest enterprise impact.',
      'Phased roadmap derived from cluster priorities and capability dependencies.',
      'Portfolio derived from benefit-per-cost optimization.',
      'Key risks: dependency readiness, data quality, and change adoption.',
      'Expected outcomes: improved delivery speed, resilience, and security posture.'
    );
    """

def q_latest_executive_strategy(usecase_id: int) -> str:
    return f"SELECT * FROM Next_ExecutiveStrategy WHERE usecase_id={int(usecase_id)} ORDER BY id DESC LIMIT 1;"

# -----------------------------
# Simulation
# -----------------------------
def w_create_scenario(usecase_id: int, name: str, description: str = "") -> str:
    n = name.replace("'", "''")
    d = description.replace("'", "''")
    return f"""
    INSERT INTO Next_TransformationScenario (scenario_name, description, usecase_id)
    VALUES ('{n}', '{d}', {int(usecase_id)});
    """

def q_list_scenarios_for_usecase(usecase_id: int, limit: int = 200) -> str:
    return f"""
    SELECT id, scenario_name, description, created_on
    FROM Next_TransformationScenario
    WHERE usecase_id={int(usecase_id)}
    ORDER BY id DESC
    LIMIT {int(limit)};
    """

def w_set_scenario_change(scenario_id: int, capability_id: int, dimension_id: int, current_score: int, target_score: int) -> str:
    return f"""
    DELETE FROM Next_ScenarioCapabilityChange
    WHERE scenario_id={int(scenario_id)} AND capability_id={int(capability_id)} AND dimension_id={int(dimension_id)};

    INSERT INTO Next_ScenarioCapabilityChange (scenario_id, capability_id, dimension_id, current_score, target_score)
    VALUES ({int(scenario_id)}, {int(capability_id)}, {int(dimension_id)}, {int(current_score)}, {int(target_score)});
    """

def w_run_scenario(scenario_id: int, max_depth: int = 3) -> str:
    return f"""
    DELETE FROM Next_ScenarioImpactCapability WHERE scenario_id={int(scenario_id)};
    DELETE FROM Next_ScenarioImpactCluster WHERE scenario_id={int(scenario_id)};

    WITH RECURSIVE impact_chain(source_capability_id, target_capability_id, impact_score, depth) AS (
      SELECT
        sc.capability_id,
        ci.target_capability_id,
        (ci.influence_strength * (sc.target_score - sc.current_score)) AS impact_score,
        1
      FROM Next_ScenarioCapabilityChange sc
      JOIN Next_CapabilityInterdependency ci
        ON sc.capability_id = ci.source_capability_id
      WHERE sc.scenario_id = {int(scenario_id)}

      UNION ALL

      SELECT
        ic.source_capability_id,
        ci.target_capability_id,
        (ci.influence_strength * ic.impact_score) AS impact_score,
        ic.depth + 1
      FROM impact_chain ic
      JOIN Next_CapabilityInterdependency ci
        ON ic.target_capability_id = ci.source_capability_id
      WHERE ic.depth < {int(max_depth)}
    )
    INSERT INTO Next_ScenarioImpactCapability (scenario_id, capability_id, impact_score, depth)
    SELECT {int(scenario_id)}, target_capability_id, SUM(impact_score), MIN(depth)
    FROM impact_chain
    GROUP BY target_capability_id;

    INSERT INTO Next_ScenarioImpactCluster (scenario_id, cluster_id, impact_score, capability_count)
    SELECT
      {int(scenario_id)},
      cm.cluster_id,
      SUM(ic.impact_score),
      COUNT(*)
    FROM Next_ScenarioImpactCapability ic
    JOIN Next_CapabilityClusterMap cm ON ic.capability_id = cm.capability_id
    WHERE ic.scenario_id = {int(scenario_id)}
    GROUP BY cm.cluster_id;
    """

def q_scenario_impacts_cluster(scenario_id: int) -> str:
    return f"""
    SELECT cc.cluster_name, ROUND(ic.impact_score,2) AS impact_score, ic.capability_count
    FROM Next_ScenarioImpactCluster ic
    JOIN Next_CapabilityCluster cc ON ic.cluster_id = cc.id
    WHERE ic.scenario_id={int(scenario_id)}
    ORDER BY ic.impact_score DESC;
    """

def q_scenario_impacts_capability(scenario_id: int, limit: int = 200) -> str:
    return f"""
    SELECT ic.depth, ROUND(ic.impact_score,2) AS impact_score, c.capability_name
    FROM Next_ScenarioImpactCapability ic
    JOIN Next_Capability c ON ic.capability_id = c.id
    WHERE ic.scenario_id={int(scenario_id)}
    ORDER BY ic.impact_score DESC
    LIMIT {int(limit)};
    """


# ── Client management helpers ─────────────────────────────────────────────────

def get_clients_with_count(client) -> list:
    """Return all clients with their assessment count."""
    result = client.query(
        """
        SELECT c.id, c.client_name,
               COALESCE(c.industry, '') AS industry,
               COALESCE(c.sector, '')   AS sector,
               COALESCE(c.country, '')  AS country,
               COUNT(a.id) AS assessment_count
        FROM Client c
        LEFT JOIN Assessment a ON a.client_id = c.id
        GROUP BY c.id
        ORDER BY c.client_name
        """,
        [],
    )
    return result.get("rows", [])


def update_client(
    client,
    client_id: int,
    name: str,
    industry: str,
    sector: str,
    country: str,
) -> dict:
    """Update an existing client record."""
    return client.write(
        "UPDATE Client SET client_name=?, industry=?, sector=?, country=? WHERE id=?",
        [name, industry, sector, country, int(client_id)],
    )


def merge_clients(client, source_id: int, target_id: int) -> dict:
    """
    Merge source client into target: reassign all assessments then delete source.
    Returns {"rowcount": N} or {"error": str}.
    """
    r1 = client.write(
        "UPDATE Assessment SET client_id=? WHERE client_id=?",
        [int(target_id), int(source_id)],
    )
    if r1.get("error"):
        return r1
    return client.write(
        "DELETE FROM Client WHERE id=?",
        [int(source_id)],
    )


def get_survey_progress(client, assessment_id: int) -> dict:
    """Return survey progress summary for an assessment.

    Returns {
        "total_questions": int,
        "respondents": [{"name", "role", "answered", "total"}]
    }
    """
    total_res = client.query(
        "SELECT COUNT(*) AS cnt FROM AssessmentResponse "
        "WHERE assessment_id = ? AND (respondent_name IS NULL OR respondent_name = '')",
        [int(assessment_id)],
    )
    total_q = (total_res.get("rows") or [{}])[0].get("cnt") or 0

    resp_res = client.query(
        """
        SELECT respondent_name, respondent_role, COUNT(*) AS answered
        FROM AssessmentResponse
        WHERE assessment_id = ?
          AND respondent_name IS NOT NULL
          AND respondent_name != ''
        GROUP BY respondent_name, respondent_role
        ORDER BY respondent_name
        """,
        [int(assessment_id)],
    )
    respondents = [
        {
            "name":     r["respondent_name"],
            "role":     r.get("respondent_role") or "",
            "answered": r["answered"],
            "total":    total_q,
        }
        for r in resp_res.get("rows", [])
    ]
    return {"total_questions": total_q, "respondents": respondents}
