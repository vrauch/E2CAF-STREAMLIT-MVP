# src/assessment_builder.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import re

from src.meridant_client import MeridantClient

@dataclass
class CapabilityResult:
    capability_id: int
    capability_name: str
    domain_name: str
    subdomain_name: str
    score: float
    rationale: str = ""
    
#@dataclass(frozen=True)
#class Capability:
#    id: int
#    name: str
#    domain: Optional[str] = None
#    subdomain: Optional[str] = None


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _intent_score(intent: str, cap: CapabilityResult) -> float:
    """
    Lightweight scoring for MVP:
    - token overlap between intent and capability name/domain/subdomain
    - small boosts if intent contains common data/security/governance terms
    """
    intent_tokens = _tokenize(intent)
    name_tokens = _tokenize(cap.name)
    dom_tokens = _tokenize(cap.domain or "")
    sub_tokens = _tokenize(cap.subdomain or "")

    overlap = len(intent_tokens & (name_tokens | dom_tokens | sub_tokens))

    # Heuristic boosts (still deterministic; replace later with embeddings/LLM ranking)
    boosts = 0.0
    boost_terms = {
        "governance": 0.6,
        "security": 0.6,
        "privacy": 0.5,
        "risk": 0.3,
        "compliance": 0.5,
        "access": 0.4,
        "quality": 0.4,
        "metadata": 0.4,
        "lineage": 0.4,
        "analytics": 0.3,
        "ai": 0.3,
        "trust": 0.3,
        "lifecycle": 0.3,
        "retention": 0.3,
    }
    for term, w in boost_terms.items():
        if term in intent_tokens:
            # Boost if the capability name/domain/subdomain contains related words too
            if term in name_tokens or term in dom_tokens or term in sub_tokens:
                boosts += w

    # Normalize by name length so long names don't dominate
    denom = max(len(name_tokens), 1)
    return (overlap / denom) + boosts

def q_capability_count() -> str:
    return "SELECT COUNT(*) AS capability_count FROM Next_Capability;"

def q_capabilities_with_taxonomy(limit: int = 5000) -> str:
    return f"""
    SELECT c.id, c.capability_name, d.domain_name, sd.subdomain_name
    FROM Next_Capability c
    LEFT JOIN Next_Domain d ON c.domain_id = d.id
    LEFT JOIN Next_SubDomain sd ON c.subdomain_id = sd.id
    ORDER BY c.capability_name
    LIMIT {int(limit)};
    """


def q_upstream_ids(core_ids: List[int]) -> str:
    if not core_ids:
        return "SELECT NULL AS capability_id WHERE 1=0;"
    ids = ",".join(str(i) for i in core_ids)
    return f"""
    SELECT DISTINCT source_capability_id AS capability_id
    FROM Next_CapabilityInterdependency
    WHERE target_capability_id IN ({ids});
    """


def q_downstream_ids(core_ids: List[int]) -> str:
    if not core_ids:
        return "SELECT NULL AS capability_id WHERE 1=0;"
    ids = ",".join(str(i) for i in core_ids)
    return f"""
    SELECT DISTINCT target_capability_id AS capability_id
    FROM Next_CapabilityInterdependency
    WHERE source_capability_id IN ({ids});
    """


def q_capabilities_by_ids(ids: List[int]) -> str:
    if not ids:
        return "SELECT NULL WHERE 1=0;"
    s = ",".join(str(i) for i in ids)
    return f"""
    SELECT c.id, c.capability_name, d.domain_name, sd.subdomain_name
    FROM Next_Capability c
    LEFT JOIN Next_Domain d ON c.domain_id = d.id
    LEFT JOIN Next_SubDomain sd ON c.subdomain_id = sd.id
    WHERE c.id IN ({s})
    ORDER BY d.domain_name, sd.subdomain_name, c.capability_name;
    """


def domains_covered(caps: List[CapabilityResult]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for c in caps:
        key = c.domain_name or "Unspecified"
        out[key] = out.get(key, 0) + 1
    return out


def analyze_use_case_readonly(
    client,
    intent_text: str,
    core_k: int = 10,
) -> tuple:
    """
    Reads TMM capabilities, uses AI to rank by intent,
    expands upstream/downstream via dependency graph.
    Returns: candidates, core, upstream, downstream, domains_covered, cap_count
    """
    import os
    from dotenv import load_dotenv
    load_dotenv()

    # ── 1. Load full capability library from TMM ──
    res = client.query("""
        SELECT
            nc.id            AS capability_id,
            nc.capability_name,
            nd.domain_name,
            ns.subdomain_name
        FROM Next_Capability nc
        JOIN Next_Domain nd ON nc.domain_id = nd.id
        JOIN Next_SubDomain ns ON nc.subdomain_id = ns.id
        ORDER BY nd.domain_name, ns.subdomain_name, nc.capability_name
    """)
    rows = res.get("rows", [])
    cap_count = len(rows)

    if not rows:
        return [], [], [], [], {}, 0

    candidates = [
        CapabilityResult(
            capability_id=int(r["capability_id"]),
            capability_name=r["capability_name"],
            domain_name=r["domain_name"],
            subdomain_name=r["subdomain_name"],
            score=0.0,
        )
        for r in rows
    ]

    # ── 2. AI ranking ──
    from src.ai_client import rank_capabilities_by_intent

    candidate_dicts = [c.__dict__ for c in candidates]

    ranked_dicts = rank_capabilities_by_intent(
        intent_text=intent_text,
        use_case_name="Assessment",
        candidates=candidate_dicts,
        top_k=core_k,
    )

    core = [
        CapabilityResult(
            capability_id=int(d["capability_id"]),
            capability_name=d["capability_name"],
            domain_name=d["domain_name"],
            subdomain_name=d["subdomain_name"],
            score=d.get("ai_score", 0.0),
            rationale=d.get("rationale", ""),
        )
        for d in ranked_dicts
    ]

    core_ids = {c.capability_id for c in core}

    # ── 3. Expand upstream (capabilities that feed into core) ──
    if core_ids:
        id_list = ",".join(str(i) for i in core_ids)
        res_up = client.query(
            f"""
            SELECT DISTINCT
                nc.id AS capability_id, nc.capability_name, nd.domain_name, ns.subdomain_name
            FROM Next_CapabilityInterdependency dep
            JOIN Next_Capability nc ON nc.id = dep.source_capability_id
            JOIN Next_Domain nd ON nc.domain_id = nd.id
            JOIN Next_SubDomain ns ON nc.subdomain_id = ns.id
            WHERE dep.target_capability_id IN ({id_list})
              AND dep.source_capability_id NOT IN ({id_list})
            """
        )
        upstream = [
            CapabilityResult(
                capability_id=int(r["capability_id"]),
                capability_name=r["capability_name"],
                domain_name=r["domain_name"],
                subdomain_name=r["subdomain_name"],
                score=0.0,
            )
            for r in res_up.get("rows", [])
        ]
    else:
        upstream = []

    upstream_ids = {c.capability_id for c in upstream}

    # ── 4. Expand downstream (capabilities that core feeds into) ──
    if core_ids:
        id_list = ",".join(str(i) for i in core_ids)
        res_dn = client.query(
            f"""
            SELECT DISTINCT
                nc.id AS capability_id, nc.capability_name, nd.domain_name, ns.subdomain_name
            FROM Next_CapabilityInterdependency dep
            JOIN Next_Capability nc ON nc.id = dep.target_capability_id
            JOIN Next_Domain nd ON nc.domain_id = nd.id
            JOIN Next_SubDomain ns ON nc.subdomain_id = ns.id
            WHERE dep.source_capability_id IN ({id_list})
              AND dep.target_capability_id NOT IN ({id_list})
            """
        )
        downstream = [
            CapabilityResult(
                capability_id=int(r["capability_id"]),
                capability_name=r["capability_name"],
                domain_name=r["domain_name"],
                subdomain_name=r["subdomain_name"],
                score=0.0,
            )
            for r in res_dn.get("rows", [])
            if int(r["capability_id"]) not in upstream_ids
        ]
    else:
        downstream = []

    # ── 5. Derive domains ──
    all_caps = core + upstream + downstream
    domains_covered: dict[str, int] = {}
    for c in all_caps:
        domains_covered[c.domain_name] = domains_covered.get(c.domain_name, 0) + 1

    return candidates, core, upstream, downstream, domains_covered, cap_count