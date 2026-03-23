"""Dashboard page — Bootstrap 5.3 light theme via st.components.v1.html()

Architecture pattern:
  - All data is json.dumps() injected as const DATA = {...} into the HTML blob
  - st.components.v1.html() renders the entire visual layer
  - No Streamlit widgets inside the component
  - Write/action operations remain as st.button() calls outside the component
"""

import json
import streamlit as st
import streamlit.components.v1 as components
from src.meridant_client import get_client
from src.sql_templates import q_list_next_usecases, get_frameworks, get_framework_labels


# ── cached loaders ────────────────────────────────────────────────────────────

def load_user_stats(_client, consultant_name: str):
    """Load assessment summary stats for the logged-in consultant."""
    res = _client.query(
        """
        SELECT
            COUNT(*)                                          AS total,
            SUM(CASE WHEN a.status = 'in_progress' THEN 1 ELSE 0 END) AS in_progress,
            SUM(CASE WHEN a.status = 'complete'    THEN 1 ELSE 0 END) AS complete,
            COUNT(DISTINCT a.client_id)                       AS clients,
            MAX(a.created_at)                                 AS last_activity
        FROM Assessment a
        WHERE COALESCE(a.consultant_name, '') = ?
        """,
        [consultant_name],
    )
    summary = res.get("rows", [{}])[0]

    fw_res = _client.query(
        """
        SELECT nf.framework_key, COUNT(*) AS cnt
        FROM Assessment a
        LEFT JOIN Next_Framework nf ON a.framework_id = nf.id
        WHERE COALESCE(a.consultant_name, '') = ?
        GROUP BY nf.framework_key
        ORDER BY cnt DESC
        """,
        [consultant_name],
    )
    by_framework = fw_res.get("rows", [])

    ind_res = _client.query(
        """
        SELECT COALESCE(c.industry, 'Unknown') AS industry, COUNT(*) AS cnt
        FROM Assessment a
        LEFT JOIN Client c ON a.client_id = c.id
        WHERE COALESCE(a.consultant_name, '') = ?
        GROUP BY c.industry
        ORDER BY cnt DESC
        """,
        [consultant_name],
    )
    by_industry = ind_res.get("rows", [])

    return summary, by_framework, by_industry


@st.cache_data(ttl=60)
def load_domain_stats(_client, framework_id: int = 1):
    r = _client.query(
        """
        SELECT d.id, d.domain_name,
            COUNT(DISTINCT sd.id)  AS subdomains,
            COUNT(DISTINCT c.id)   AS capabilities,
            COUNT(DISTINCT ci.id)  AS dependencies
        FROM Next_Domain d
        LEFT JOIN Next_SubDomain sd ON sd.domain_id = d.id AND sd.framework_id = ?
        LEFT JOIN Next_Capability c  ON c.domain_id  = d.id AND c.framework_id  = ?
        LEFT JOIN Next_CapabilityInterdependency ci ON ci.source_capability_id = c.id
        WHERE d.framework_id = ?
        GROUP BY d.id, d.domain_name ORDER BY d.id
        """,
        [framework_id, framework_id, framework_id]
    )
    return r.get("rows", [])


@st.cache_data(ttl=60)
def load_dep_mix(_client):
    r = _client.query("""
        SELECT t.interaction_type, COUNT(*) AS count
        FROM Next_CapabilityInterdependency i
        JOIN Next_CapabilityInteractionType t ON i.interaction_type_id = t.id
        GROUP BY t.interaction_type ORDER BY count DESC
    """)
    return r.get("rows", [])


@st.cache_data(ttl=60)
def load_top_subdomains(_client, framework_id: int = 1):
    r = _client.query(
        """
        SELECT d.domain_name, sd.subdomain_name, COUNT(c.id) AS capabilities
        FROM Next_SubDomain sd
        JOIN Next_Domain d ON d.id = sd.domain_id AND d.framework_id = ?
        LEFT JOIN Next_Capability c ON c.subdomain_id = sd.id AND c.framework_id = ?
        WHERE sd.framework_id = ?
        GROUP BY d.domain_name, sd.subdomain_name
        ORDER BY capabilities DESC LIMIT 15
        """,
        [framework_id, framework_id, framework_id]
    )
    return r.get("rows", [])


@st.cache_data(ttl=60)
def load_anchors(_client, framework_id: int = 1):
    r = _client.query(
        """
        SELECT c.capability_name, d.domain_name, COUNT(i.id) AS outbound_links
        FROM Next_Capability c
        JOIN Next_Domain d ON c.domain_id = d.id AND d.framework_id = ?
        JOIN Next_CapabilityInterdependency i
              ON i.source_capability_id = c.id AND i.interaction_type_id = 1
        WHERE c.framework_id = ?
        GROUP BY c.id, c.capability_name, d.domain_name
        ORDER BY outbound_links DESC LIMIT 8
        """,
        [framework_id, framework_id]
    )
    return r.get("rows", [])


@st.cache_data(ttl=60)
def load_subdomains(_client, framework_id: int = 1):
    r = _client.query(
        """
        SELECT sd.id, sd.domain_id, sd.subdomain_name, COUNT(c.id) AS cap_count
        FROM Next_SubDomain sd
        LEFT JOIN Next_Capability c ON c.subdomain_id = sd.id AND c.framework_id = ?
        WHERE sd.framework_id = ?
        GROUP BY sd.id, sd.domain_id, sd.subdomain_name
        ORDER BY sd.domain_id, sd.id
        """,
        [framework_id, framework_id]
    )
    return r.get("rows", [])


@st.cache_data(ttl=60)
def load_capabilities_with_maturity(_client, framework_id: int = 1):
    r = _client.query(
        """
        SELECT
            c.id, c.capability_name, c.capability_description,
            c.category, c.domain_id, c.subdomain_id, c.owner_role
        FROM Next_Capability c
        WHERE c.framework_id = ?
        ORDER BY c.domain_id, c.subdomain_id, c.id
        """,
        [framework_id]
    )
    return r.get("rows", [])


@st.cache_data(ttl=60)
def load_capability_levels(_client, framework_id: int = 1):
    r = _client.query(
        """
        SELECT capability_id, level, level_name, capability_state, key_indicators
        FROM Next_CapabilityLevel
        WHERE framework_id = ? AND level_name IS NOT NULL
        ORDER BY capability_id, level
        """,
        [framework_id]
    )
    return r.get("rows", [])


@st.cache_data(ttl=60)
def load_use_cases(_client, framework_id: int = 1):
    r = _client.query(q_list_next_usecases(framework_id=framework_id))
    return r.get("rows", [])



# ── render ────────────────────────────────────────────────────────────────────

def render() -> None:
    client = get_client()

    framework_id = st.session_state.get("framework_id", 1)
    labels       = st.session_state.get(
        "framework_labels",
        {"level1": "Pillar", "level2": "Domain", "level3": "Capability"}
    )

    # ── My Assessments summary (folded into main payload) ───────────────────
    current_user = st.session_state.get("authenticated_username") or ""
    user_summary = {}
    if current_user:
        _us, _by_fw, _by_ind = load_user_stats(client, current_user)
        user_summary = {
            "username":      current_user,
            "total":         _us.get("total") or 0,
            "in_progress":   _us.get("in_progress") or 0,
            "complete":      _us.get("complete") or 0,
            "clients":       _us.get("clients") or 0,
            "last_activity": (_us.get("last_activity") or "")[:10],
            "by_framework":  _by_fw,
            "by_industry":   _by_ind,
        }

    # ── Load all frameworks into payload for client-side switching ───────────
    _fw_list     = get_frameworks(client)
    dep_mix      = load_dep_mix(client)

    frameworks_data = {}
    for _fw in _fw_list:
        _fid  = _fw["id"]
        _doms = load_domain_stats(client, _fid)
        _sds  = load_subdomains(client, _fid)
        _caps = load_capabilities_with_maturity(client, _fid)
        _lvls = load_capability_levels(client, _fid)
        _ucs  = load_use_cases(client, _fid)
        frameworks_data[str(_fid)] = {
            "domains":      _doms,
            "subdomains":   _sds,
            "capabilities": _caps,
            "cap_levels":   _lvls,
            "use_cases":    _ucs,
            "kpis": {
                "domains":      len(_doms),
                "subdomains":   sum(d["subdomains"]   for d in _doms),
                "capabilities": sum(d["capabilities"] for d in _doms),
                "use_cases":    len(_ucs),
            },
        }

    payload = json.dumps({
        "frameworks":      [{"id": f["id"], "framework_name": f["framework_name"],
                             "label_level1": f["label_level1"] or "Pillar",
                             "label_level2": f["label_level2"] or "Domain",
                             "label_level3": f["label_level3"] or "Capability"}
                            for f in _fw_list],
        "frameworks_data": frameworks_data,
        "default_fw_id":   framework_id,
        "dep_mix":         dep_mix,
        "user_summary":    user_summary,
    }, default=str)

    html = (
        """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Inter:wght@300;400;600;700;800&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
<style>
  :root {
    --bs-body-bg:      #F9FAFB;
    --bs-body-color:   #111827;
    --bs-card-bg:      #ffffff;
    --bs-border-color: #D1D5DB;
    --accent:  #2563EB;
    --green:   #0D9488;
    --gold:    #D97706;
    --red:     #DC2626;
    --purple:  #7C3AED;
    --orange:  #EA580C;
  }
  body { font-family:'Inter',sans-serif; background:var(--bs-body-bg); color:var(--bs-body-color); }
  code, .mono { font-family:'JetBrains Mono',monospace; }

  .kpi-card {
    background:#ffffff; border:1px solid #D1D5DB; border-radius:10px;
    padding:1.1rem 1.4rem; transition:border-color .2s;
  }
  .kpi-card:hover { border-color:var(--accent); }
  .kpi-value { font-family:'JetBrains Mono',monospace; font-size:2rem; font-weight:700; line-height:1; color:var(--accent); }
  .kpi-label { font-size:.72rem; color:#6B7280; letter-spacing:.08em; text-transform:uppercase; margin-top:.3rem; }

  /* User summary */
  .my-kpi-card { background:#fff; border:1px solid #D1D5DB; border-radius:10px; padding:1rem 1.25rem; height:100%; }
  .my-kpi-val  { font-family:'JetBrains Mono',monospace; font-size:1.8rem; font-weight:700; line-height:1; }
  .my-kpi-lbl  { font-size:.67rem; color:#6B7280; letter-spacing:.08em; text-transform:uppercase; margin-top:.25rem; }
  .my-panel    { background:#fff; border:1px solid #D1D5DB; border-radius:10px; padding:1rem 1.25rem; height:100%; }

  /* Framework selector */
  .fw-selector-bar { display:flex; align-items:center; gap:.75rem; margin-bottom:1.25rem; }
  .fw-selector-bar label { font-size:.7rem; letter-spacing:.12em; text-transform:uppercase; color:#6B7280; font-family:'JetBrains Mono',monospace; white-space:nowrap; }
  #fw-select {
    background:#fff; border:1px solid #D1D5DB; border-radius:6px;
    padding:.35rem .75rem; font-size:.82rem; color:#111827;
    font-family:'Inter',sans-serif; cursor:pointer; min-width:180px;
  }
  #fw-select:focus { outline:none; border-color:#2563EB; box-shadow:0 0 0 3px #2563EB22; }

  .domain-card {
    background:#ffffff; border:1px solid #D1D5DB; border-radius:10px;
    cursor:pointer; padding:clamp(.55rem,.9vw,1rem) clamp(.55rem,.9vw,1.1rem);
    transition:transform .18s, box-shadow .18s, border-color .18s;
    overflow:hidden;
  }
  .domain-card:hover { transform:translateY(-3px); box-shadow:0 4px 16px rgba(0,0,0,.08); }
  .domain-card.active { border-width:2px !important; }
  .domain-id   { font-family:'JetBrains Mono',monospace; font-size:clamp(.58rem,.6vw,.68rem); font-weight:700; letter-spacing:.06em; margin-bottom:.3rem; }
  .domain-name { font-size:clamp(.68rem,.75vw,.82rem); font-weight:700; line-height:1.3;
                 color:#111827; margin-bottom:.6rem;
                 overflow-wrap:break-word; word-break:break-word; hyphens:auto; }
  .stat-val    { font-family:'JetBrains Mono',monospace; font-size:clamp(.85rem,1.1vw,1.25rem); font-weight:700; }
  .stat-lbl    { font-size:clamp(.54rem,.6vw,.62rem); color:#6B7280; text-transform:uppercase; }

  #drilldown { display:none; }
  #drilldown.show { display:block; }
  .sd-card {
    background:#F9FAFB; border:1px solid #D1D5DB; border-radius:8px;
    padding:.9rem 1rem; font-size:.78rem; cursor:pointer;
    transition:border-color .15s, background .15s;
  }
  .sd-card:hover { background:#F3F4F6; }
  .sd-card.active { border-width:2px !important; background:#F3F4F6; }
  .sd-name { font-weight:700; font-size:.8rem; margin-bottom:.3rem; }

  #cap-view { display:none; }
  #cap-view.show { display:block; }
  .cap-card {
    background:#ffffff; border:1px solid #D1D5DB; border-radius:8px;
    padding:.8rem 1rem; cursor:pointer;
    transition:transform .15s, box-shadow .15s, border-color .15s;
  }
  .cap-card:hover { transform:translateY(-2px); box-shadow:0 4px 12px rgba(0,0,0,.08); border-color:#D1D5DB; }
  .cap-identifier { font-size:.62rem; font-family:'JetBrains Mono',monospace; color:#6B7280; margin-bottom:.25rem; }
  .cap-name  { font-size:.78rem; font-weight:700; color:#111827; line-height:1.3; }

  .bc-nav { display:flex; align-items:center; gap:.5rem; font-size:.75rem; color:#6B7280; margin-bottom:1.2rem; font-family:'JetBrains Mono',monospace; }
  .bc-link { color:var(--accent); cursor:pointer; text-decoration:underline; }
  .bc-link:hover { color:#1D4ED8; }
  .bc-sep  { color:#D1D5DB; }

  .section-label { font-size:.7rem; letter-spacing:.16em; text-transform:uppercase; color:#6B7280; margin-bottom:1rem; font-family:'JetBrains Mono',monospace; }
  .anchor-row    { margin-bottom:.85rem; }
  .anchor-name   { font-size:.78rem; font-weight:600; color:#111827; }
  .anchor-domain { font-size:.65rem; color:#6B7280; margin-bottom:.3rem; }
  .anchor-links  { font-family:'JetBrains Mono',monospace; font-size:.7rem; font-weight:700; }

  .table th { font-size:.68rem; letter-spacing:.08em; text-transform:uppercase; color:#6B7280; border-color:#D1D5DB; }
  .table td { font-size:.82rem; border-color:#D1D5DB; vertical-align:middle; }
  .table-hover tbody tr:hover td { background:#F9FAFB; }
  hr.section-divider { border-color:#D1D5DB; margin:2rem 0; }

  .modal-content { background:#ffffff; border:1px solid #D1D5DB; }
  .modal-header  { border-bottom:1px solid #D1D5DB; }
  .modal-footer  { border-top:1px solid #D1D5DB; }

  /* Custom overlay */
  #capOverlay {
    display:none; position:fixed; top:0; left:0; width:100%; height:100%;
    z-index:9999; background:rgba(0,0,0,.3); overflow-y:auto;
    justify-content:center; align-items:flex-start; padding:3vh 1rem;
  }
  #capOverlay.show { display:flex; }
  #capOverlayContent {
    background:#ffffff; border:1px solid #D1D5DB; border-radius:10px;
    width:100%; max-width:800px; max-height:94vh; overflow-y:auto;
    box-shadow:0 12px 40px rgba(0,0,0,.12);
  }
  #capOverlayContent .modal-header { display:flex; align-items:flex-start; padding:1rem 1.2rem; }
  #capOverlayContent .modal-body   { padding:0 1.2rem 1rem; }
  #capOverlayContent .modal-footer  { padding:.8rem 1.2rem; display:flex; justify-content:flex-end; }
  .overlay-close {
    background:none; border:none; color:#6B7280; font-size:1.4rem; cursor:pointer;
    padding:0; line-height:1; margin-left:auto;
  }
  .overlay-close:hover { color:#111827; }
  .nav-tabs .nav-link        { color:#6B7280; border-color:#D1D5DB; font-size:.78rem; }
  .nav-tabs .nav-link.active { background:#F9FAFB; color:#111827; border-color:#D1D5DB #D1D5DB #F9FAFB; }
  .nav-tabs .nav-link:hover  { color:#111827; border-color:#D1D5DB; }
  .tab-content  { background:#F9FAFB; border:1px solid #D1D5DB; border-top:none; border-radius:0 0 6px 6px; padding:1rem; }
  .level-state  { font-size:.8rem; color:#374151; line-height:1.6; margin-bottom:.8rem; }
  .level-indicators { font-size:.75rem; color:#6B7280; }
  .level-badge  { font-family:'JetBrains Mono',monospace; font-size:.65rem; font-weight:700; padding:.25rem .6rem; border-radius:4px; display:inline-block; margin-bottom:.8rem; }
  .owner-badge  { background:#F3F4F6; border:1px solid #D1D5DB; border-radius:4px; padding:.2rem .5rem; font-size:.68rem; color:#6B7280; }
</style>
</head>
<body class="p-3">

<script>const DATA = """
        + payload
        + """;</script>

<!-- User summary -->
<div id="user-summary" class="mb-4"></div>

<!-- Framework selector -->
<div class="fw-selector-bar">
  <label for="fw-select">Framework</label>
  <select id="fw-select"></select>
</div>

<!-- Breadcrumb (hidden until drill-down) -->
<div id="breadcrumb-nav" style="display:none" class="mb-2"></div>

<!-- Domain cards + drilldown -->
<div id="view1">
  <div class="section-label" id="domain-overview-label">Domain Overview &mdash; click any card to expand, then click a subdomain to view capabilities</div>
  <div class="row g-2 mb-3" id="domain-grid"></div>

  <!-- Subdomain panel -->
  <div id="drilldown" class="mb-4">
    <div class="d-flex align-items-center gap-2 mb-3">
      <div id="dd-dot" class="rounded-circle" style="width:10px;height:10px;flex-shrink:0"></div>
      <span id="dd-title" class="fw-bold" style="font-size:.95rem"></span>
      <span id="dd-badge" class="badge rounded-pill ms-1" style="font-size:.65rem"></span>
      <button class="btn btn-sm ms-auto" id="dd-close"
              style="background:#F3F4F6;border:1px solid #D1D5DB;color:#6B7280;font-size:.7rem">
        &#x2715; Close
      </button>
    </div>
    <div class="section-label" style="margin-bottom:.6rem">Subdomains &mdash; click to view capabilities</div>
    <div class="row g-2" id="sd-grid"></div>

    <!-- Capability cards (inline, below subdomains) -->
    <div id="cap-view" class="mt-3">
      <div class="section-label" id="cap-view-label">Capabilities</div>
      <div class="row g-2" id="cap-grid"></div>
    </div>
  </div>
</div>

<!-- Capability detail overlay -->
<div id="capOverlay">
  <div id="capOverlayContent">
    <div class="modal-header">
      <div>
        <div class="d-flex align-items-center gap-2 mb-1">
          <span id="modal-domain-badge" class="badge" style="font-size:.65rem"></span>
          <span id="modal-subdomain-badge" class="badge" style="background:#F3F4F6;color:#6B7280;font-size:.65rem"></span>
        </div>
        <h6 class="fw-bold" id="modal-cap-name" style="color:#111827;font-size:.95rem;margin:0"></h6>
      </div>
      <button type="button" class="overlay-close" id="overlay-close-x">&#x2715;</button>
    </div>
    <div class="modal-body">
      <p id="modal-cap-desc" style="font-size:.8rem;color:#6B7280;margin-bottom:1rem"></p>
      <div id="modal-owner" class="mb-3"></div>
      <div class="section-label">Maturity Level Descriptors</div>
      <ul class="nav nav-tabs" id="levelTabs" role="tablist"></ul>
      <div class="tab-content" id="levelTabContent"></div>
    </div>
    <div class="modal-footer">
      <button type="button" class="btn btn-sm" id="overlay-close-btn"
              style="background:#F3F4F6;border:1px solid #D1D5DB;color:#6B7280;font-size:.75rem">
        Close
      </button>
    </div>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
<script>
const DOMAIN_COLORS = ['#0F2744','#DC2626','#7C3AED','#2563EB','#0D9488','#6366F1','#0EA5E9','#374151','#5B21B6','#0369A1','#047857','#9333EA'];
const DEP_COLORS    = ['#DC2626','#D97706','#0D9488','#2563EB'];
const LEVEL_COLORS  = ['#DC2626','#D97706','#EA580C','#0D9488','#2563EB'];
const LEVEL_NAMES   = ['Ad Hoc','Defined','Integrated','Intelligent','Adaptive'];

// ── Framework selector + lookup maps ─────────────────────────────────────────
let currentFwId = String(DATA.default_fw_id || Object.keys(DATA.frameworks_data)[0]);
let currentFw   = DATA.frameworks_data[currentFwId];

let domainColorMap = {}, domainById = {}, sdById = {}, capLevelMap = {};

function buildLookups() {
  domainColorMap = {};
  currentFw.domains.forEach((d,i) => { domainColorMap[d.domain_name] = DOMAIN_COLORS[i % DOMAIN_COLORS.length]; });
  domainById  = Object.fromEntries(currentFw.domains.map(d => [d.id, d]));
  sdById      = Object.fromEntries(currentFw.subdomains.map(s => [s.id, s]));
  capLevelMap = {};
  currentFw.cap_levels.forEach(cl => {
    if (!capLevelMap[cl.capability_id]) capLevelMap[cl.capability_id] = [];
    capLevelMap[cl.capability_id].push(cl);
  });
  Object.values(capLevelMap).forEach(arr => arr.sort((a,b) => a.level - b.level));
}
buildLookups();

(function initFwSelector() {
  const sel = document.getElementById('fw-select');
  DATA.frameworks.forEach(fw => {
    const opt = document.createElement('option');
    opt.value = String(fw.id);
    opt.textContent = fw.framework_name;
    if (String(fw.id) === currentFwId) opt.selected = true;
    sel.appendChild(opt);
  });
  sel.addEventListener('change', function() {
    currentFwId = this.value;
    currentFw   = DATA.frameworks_data[currentFwId];
    activeDomainId = null; activeSubdomainId = null;
    closeCapView();
    document.getElementById('drilldown').classList.remove('show');
    document.getElementById('breadcrumb-nav').style.display = 'none';
    buildLookups();
    renderDomainGrid();
  });
})();

// ── User summary ─────────────────────────────────────────────────────────────
(function() {
  const us = DATA.user_summary;
  if (!us || !us.total) return;

  const FW_COLORS  = { MMTF:'#2563EB', NIST_CSF_2:'#0D9488' };
  const FW_LABELS  = { MMTF:'MMTF',    NIST_CSF_2:'NIST CSF 2' };

  // KPI row
  const kpis = [
    { val:us.total,       lbl:'Total',       color:'#2563EB' },
    { val:us.in_progress, lbl:'In Progress', color:'#2563EB' },
    { val:us.complete,    lbl:'Complete',    color:'#0D9488' },
    { val:us.clients,     lbl:'Clients',     color:'#7C3AED' },
  ];
  let kpiHtml = '<div class="row g-2 mb-3">';
  kpis.forEach(k => {
    kpiHtml += `<div class="col-6 col-md-3"><div class="my-kpi-card">
      <div class="my-kpi-val" style="color:${k.color}">${k.val}</div>
      <div class="my-kpi-lbl">${k.lbl}</div>
    </div></div>`;
  });
  kpiHtml += '</div>';

  // Framework pills
  let fwHtml = '';
  (us.by_framework || []).forEach(fw => {
    const key   = fw.framework_key || 'Unknown';
    const color = FW_COLORS[key]  || '#6B7280';
    const label = FW_LABELS[key]  || key;
    fwHtml += `<span class="badge rounded-pill me-1 mb-1"
      style="background:${color}18;color:${color};border:1px solid ${color}44;font-size:.75rem;font-weight:600;padding:.35rem .8rem">
      <span style="font-family:'JetBrains Mono',monospace;font-size:.9rem;font-weight:700">${fw.cnt}</span> ${label}
    </span>`;
  });
  const lastHtml = us.last_activity
    ? `<div style="font-size:.68rem;color:#9CA3AF;margin-top:.5rem">Last activity: ${us.last_activity}</div>` : '';

  // Industry bars
  const maxInd = Math.max(...(us.by_industry || []).map(r => r.cnt), 1);
  let indHtml = '';
  (us.by_industry || []).forEach(r => {
    const pct = Math.round(r.cnt / maxInd * 100);
    indHtml += `<div class="d-flex align-items-center gap-2 mb-1">
      <span style="font-size:.75rem;color:#374151;width:130px;flex-shrink:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${r.industry}</span>
      <div class="flex-grow-1" style="background:#F3F4F6;border-radius:3px;height:6px">
        <div style="width:${pct}%;background:#2563EB;border-radius:3px;height:6px"></div>
      </div>
      <span style="font-family:'JetBrains Mono',monospace;font-size:.72rem;color:#6B7280;width:14px;text-align:right">${r.cnt}</span>
    </div>`;
  });
  if (!indHtml) indHtml = '<span style="font-size:.75rem;color:#9CA3AF">No data</span>';

  const panelRow = `<div class="row g-2">
    <div class="col-12 col-md-6"><div class="my-panel">
      <div class="section-label mb-2">By Framework</div>
      <div class="d-flex flex-wrap">${fwHtml}</div>
      ${lastHtml}
    </div></div>
    <div class="col-12 col-md-6"><div class="my-panel">
      <div class="section-label mb-2">By Industry</div>
      ${indHtml}
    </div></div>
  </div>`;

  document.getElementById('user-summary').innerHTML =
    `<div class="section-label mb-3">My Assessments \u2014 ${us.username}</div>` + kpiHtml + panelRow;
})();

// ── state ────────────────────────────────────────────────────────────────────
let activeDomainId   = null;
let activeSubdomainId = null;

// helpers
function fmt(v) {
  const n = parseFloat(v);
  return (!v && v !== 0) || isNaN(n) ? '-' : n.toFixed(1);
}

// Domain cards
function renderDomainGrid() {
  const domainGrid = document.getElementById('domain-grid');
  domainGrid.innerHTML = '';
  currentFw.domains.forEach((d,i) => {
    const col = document.createElement('div');
    col.className = 'col-6 col-md-3';
    const color = DOMAIN_COLORS[i % DOMAIN_COLORS.length];
    col.innerHTML = `<div class="domain-card" id="dc-${d.id}" style="border-top:3px solid ${color}" onclick="toggleDomain(${d.id},'${color}')">
      <div class="domain-id" style="color:${color}">D${d.id}</div>
      <div class="domain-name">${d.domain_name}</div>
      <div class="d-flex gap-2 flex-wrap">
        <div><div class="stat-val" style="color:${color}">${d.subdomains}</div><div class="stat-lbl">Subdomains</div></div>
        <div><div class="stat-val" style="color:#111827">${d.capabilities}</div><div class="stat-lbl">Capabilities</div></div>
        <div><div class="stat-val" style="color:#6B7280">${d.dependencies}</div><div class="stat-lbl">Deps</div></div>
      </div>
    </div>`;
    domainGrid.appendChild(col);
  });
}
renderDomainGrid();

function toggleDomain(id, color) {
  if (activeDomainId !== null) {
    const prev = document.getElementById('dc-' + activeDomainId);
    if (prev) prev.classList.remove('active');
  }
  if (activeDomainId === id) {
    activeDomainId = null;
    closeCapView();
    document.getElementById('drilldown').classList.remove('show');
    return;
  }
  activeDomainId   = id;
  activeSubdomainId = null;
  closeCapView();

  const card   = document.getElementById('dc-' + id);
  card.classList.add('active');
  card.style.borderColor = color;

  const domain = currentFw.domains.find(d => d.id === id);
  document.getElementById('dd-dot').style.cssText        = `width:10px;height:10px;flex-shrink:0;background:${color}`;
  document.getElementById('dd-title').textContent        = domain.domain_name;
  document.getElementById('dd-title').style.color        = color;
  document.getElementById('dd-badge').textContent        = `${domain.subdomains} subdomains \u00b7 ${domain.capabilities} capabilities`;
  document.getElementById('dd-badge').style.background   = color + '22';
  document.getElementById('dd-badge').style.color        = color;

  const sds  = currentFw.subdomains.filter(s => s.domain_id === id);
  const grid = document.getElementById('sd-grid');
  grid.innerHTML = '';
  sds.forEach(sd => {
    const col = document.createElement('div');
    col.className = 'col-6 col-md-4 col-lg-3';
    col.innerHTML = `<div class="sd-card" id="sdc-${sd.id}" style="border-top:2px solid ${color}" onclick="selectSubdomain(${sd.id},'${color}')">
      <div class="sd-name" style="color:${color}">${sd.subdomain_name}</div>
      <div class="mono" style="font-size:.7rem;color:#6B7280">${sd.cap_count} capabilities</div>
    </div>`;
    grid.appendChild(col);
  });

  document.getElementById('drilldown').classList.add('show');
  document.getElementById('drilldown').scrollIntoView({behavior:'smooth',block:'nearest'});
}

function selectSubdomain(sdId, color) {
  if (activeSubdomainId !== null) {
    const prev = document.getElementById('sdc-' + activeSubdomainId);
    if (prev) prev.classList.remove('active');
  }
  activeSubdomainId = sdId;
  const card = document.getElementById('sdc-' + sdId);
  if (card) card.classList.add('active');

  const sd = sdById[sdId];
  renderCapabilities(sdId, color, sd ? sd.subdomain_name : '');
}

document.getElementById('dd-close').addEventListener('click', () => {
  if (activeDomainId !== null) {
    const prev = document.getElementById('dc-' + activeDomainId);
    if (prev) prev.classList.remove('active');
    activeDomainId = null;
  }
  activeSubdomainId = null;
  closeCapView();
  document.getElementById('drilldown').classList.remove('show');
});

// Capability view
function renderCapabilities(sdId, color, sdName) {
  const caps   = currentFw.capabilities.filter(c => c.subdomain_id === sdId);
  const domain = caps[0] ? domainById[caps[0].domain_id] : null;

  document.getElementById('cap-view-label').textContent =
    (domain ? domain.domain_name + ' \u00b7 ' : '') + sdName + ' \u2014 ' + caps.length + ' capabilities';

  // breadcrumb
  const nav = document.getElementById('breadcrumb-nav');
  nav.style.display = 'flex';
  nav.className     = 'bc-nav';
  nav.innerHTML     = `<span class="bc-link" onclick="closeToDomain()">All Domains</span>
    <span class="bc-sep">\u203a</span>
    <span style="color:${color}">${domain ? domain.domain_name : ''}</span>
    <span class="bc-sep">\u203a</span>
    <span style="color:#111827">${sdName}</span>`;

  const grid = document.getElementById('cap-grid');
  grid.innerHTML = '';
  caps.forEach(cap => {
    const col = document.createElement('div');
    col.className = 'col-6 col-md-4 col-lg-3';
    const isIdCode  = /^[A-Z]{2,3}\.[A-Z]{2,4}-\d{2}$/.test(cap.capability_name);
    const cardLabel = (isIdCode && cap.category) ? cap.category : cap.capability_name;
    const cardIdBadge = isIdCode ? `<div class="cap-identifier">${cap.capability_name}</div>` : '';
    col.innerHTML = `<div class="cap-card" style="border-top:2px solid ${color}" onclick="openCapModal(${cap.id})">
      ${cardIdBadge}
      <div class="cap-name">${cardLabel}</div>
    </div>`;
    grid.appendChild(col);
  });

  document.getElementById('cap-view').classList.add('show');
  document.getElementById('cap-view').scrollIntoView({behavior:'smooth',block:'start'});
}

function closeCapView() {
  document.getElementById('cap-view').classList.remove('show');
  document.getElementById('cap-grid').innerHTML = '';
  const nav = document.getElementById('breadcrumb-nav');
  nav.style.display = 'none';
  nav.innerHTML = '';
}

function closeToDomain() {
  closeCapView();
  if (activeSubdomainId !== null) {
    const prev = document.getElementById('sdc-' + activeSubdomainId);
    if (prev) prev.classList.remove('active');
    activeSubdomainId = null;
  }
  document.getElementById('drilldown').scrollIntoView({behavior:'smooth',block:'nearest'});
}

// Capability modal
function openCapModal(capId) {
  const cap    = currentFw.capabilities.find(c => c.id === capId);
  if (!cap) return;
  const domain = domainById[cap.domain_id];
  const sd     = sdById[cap.subdomain_id];
  const color  = domain ? DOMAIN_COLORS[(domain.id - 1) % DOMAIN_COLORS.length] : '#6B7280';
  const levels = capLevelMap[capId] || [];

  const modalNameEl = document.getElementById('modal-cap-name');
  const isIdCode = /^[A-Z]{2,3}\.[A-Z]{2,4}-\d{2}$/.test(cap.capability_name);
  if (isIdCode && cap.category) {
    modalNameEl.innerHTML = `${cap.category} <span style="font-size:.7rem;font-weight:400;color:#6B7280;margin-left:.4rem;font-family:monospace">${cap.capability_name}</span>`;
  } else {
    modalNameEl.textContent = cap.capability_name;
  }
  const levels0 = capLevelMap[capId] || [];
  const l1desc  = levels0.length ? (levels0[0].capability_state || '') : '';
  document.getElementById('modal-cap-desc').textContent =
    cap.capability_description || l1desc || 'No description available.';

  const domBadge = document.getElementById('modal-domain-badge');
  domBadge.textContent      = domain ? domain.domain_name : '';
  domBadge.style.cssText   += `;background:${color}22;color:${color};border:1px solid ${color}44`;

  document.getElementById('modal-subdomain-badge').textContent = sd ? sd.subdomain_name : '';

  const ownerEl = document.getElementById('modal-owner');
  ownerEl.innerHTML = cap.owner_role ? `<span class="owner-badge">Owner: ${cap.owner_role}</span>` : '';

  const tabs    = document.getElementById('levelTabs');
  const content = document.getElementById('levelTabContent');
  tabs.innerHTML = '';
  content.innerHTML = '';

  if (levels.length === 0) {
    content.innerHTML = '<p style="color:#6B7280;font-size:.8rem">No maturity level data available.</p>';
  } else {
    levels.forEach((lv, idx) => {
      const lc     = LEVEL_COLORS[(lv.level - 1) % LEVEL_COLORS.length];
      const paneId = `cp-${capId}-${lv.level}`;
      const active = idx === 0 ? 'active' : '';
      const indHtml = lv.key_indicators
        ? lv.key_indicators.split('\\n').filter(s => s.trim())
            .map(s => `<li>${s.trim()}</li>`).join('')
        : '';

      tabs.innerHTML += `<li class="nav-item" role="presentation">
        <button class="nav-link ${active}" data-bs-toggle="tab" data-bs-target="#${paneId}"
                type="button" style="${active ? 'color:'+lc+';border-bottom-color:'+lc+'!important' : ''}">
          L${lv.level} &middot; ${lv.level_name || LEVEL_NAMES[lv.level-1] || ''}
        </button></li>`;

      content.innerHTML += `<div class="tab-pane fade show ${active}" id="${paneId}" role="tabpanel">
        <span class="level-badge" style="background:${lc}22;color:${lc};border:1px solid ${lc}44">L${lv.level} \u2014 ${lv.level_name || LEVEL_NAMES[lv.level-1]}</span>
        <div class="level-state">${lv.capability_state || 'No description available.'}</div>
        ${indHtml ? `<div style="font-size:.72rem;color:#6B7280;text-transform:uppercase;letter-spacing:.08em;margin-bottom:.4rem">Key Indicators</div>
        <ul style="padding-left:1.2rem;margin:0" class="level-indicators">${indHtml}</ul>` : ''}
      </div>`;
    });
  }

  // Show overlay and scroll parent page to bring iframe into view
  var overlay = document.getElementById('capOverlay');
  overlay.classList.add('show');
  document.getElementById('capOverlayContent').scrollTop = 0;
  try { window.frameElement.scrollIntoView({behavior: 'smooth', block: 'start'}); } catch(e) {}
}

// Close overlay handlers
function closeOverlay() {
  document.getElementById('capOverlay').classList.remove('show');
}
document.getElementById('overlay-close-x').addEventListener('click', closeOverlay);
document.getElementById('overlay-close-btn').addEventListener('click', closeOverlay);
document.getElementById('capOverlay').addEventListener('click', function(e) {
  if (e.target === this) closeOverlay();  // click on backdrop
});

// Tab switching (no Bootstrap tab JS needed — manual)
document.addEventListener('click', function(e) {
  var btn = e.target.closest('#levelTabs .nav-link');
  if (!btn) return;
  document.querySelectorAll('#levelTabs .nav-link').forEach(b => {
    b.classList.remove('active'); b.style.color = ''; b.style.borderBottomColor = '';
  });
  document.querySelectorAll('#levelTabContent .tab-pane').forEach(p => {
    p.classList.remove('show','active');
  });
  btn.classList.add('active');
  var target = document.querySelector(btn.getAttribute('data-bs-target'));
  if (target) target.classList.add('show','active');
  // colour
  var idx = Array.from(btn.parentElement.parentElement.children).indexOf(btn.parentElement);
  var lc = LEVEL_COLORS[idx % LEVEL_COLORS.length];
  btn.style.color = lc;
  btn.style.borderBottomColor = lc;
});

</script>
</body>
</html>"""
    )

    components.html(html, height=1400, scrolling=True)