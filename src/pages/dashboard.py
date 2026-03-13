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
from src.sql_templates import q_list_next_usecases


# ── cached loaders ────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def load_domain_stats(_client):
    r = _client.query("""
        SELECT d.id, d.domain_name,
            COUNT(DISTINCT sd.id)  AS subdomains,
            COUNT(DISTINCT c.id)   AS capabilities,
            COUNT(DISTINCT ci.id)  AS dependencies
        FROM Next_Domain d
        LEFT JOIN Next_SubDomain              sd ON sd.domain_id          = d.id
        LEFT JOIN Next_Capability             c  ON c.domain_id           = d.id
        LEFT JOIN Next_CapabilityInterdependency ci ON ci.source_capability_id = c.id
        GROUP BY d.id, d.domain_name ORDER BY d.id
    """)
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
def load_top_subdomains(_client):
    r = _client.query("""
        SELECT d.domain_name, sd.subdomain_name, COUNT(c.id) AS capabilities
        FROM Next_SubDomain sd
        JOIN Next_Domain d ON d.id = sd.domain_id
        LEFT JOIN Next_Capability c ON c.subdomain_id = sd.id
        GROUP BY d.domain_name, sd.subdomain_name
        ORDER BY capabilities DESC LIMIT 15
    """)
    return r.get("rows", [])


@st.cache_data(ttl=60)
def load_anchors(_client):
    r = _client.query("""
        SELECT c.capability_name, d.domain_name, COUNT(i.id) AS outbound_links
        FROM Next_Capability c
        JOIN Next_Domain d ON c.domain_id = d.id
        JOIN Next_CapabilityInterdependency i
              ON i.source_capability_id = c.id AND i.interaction_type_id = 1
        GROUP BY c.id, c.capability_name, d.domain_name
        ORDER BY outbound_links DESC LIMIT 8
    """)
    return r.get("rows", [])


@st.cache_data(ttl=60)
def load_subdomains(_client):
    r = _client.query("""
        SELECT sd.id, sd.domain_id, sd.subdomain_name, COUNT(c.id) AS cap_count
        FROM Next_SubDomain sd
        LEFT JOIN Next_Capability c ON c.subdomain_id = sd.id
        GROUP BY sd.id, sd.domain_id, sd.subdomain_name
        ORDER BY sd.domain_id, sd.id
    """)
    return r.get("rows", [])


@st.cache_data(ttl=60)
def load_capabilities_with_maturity(_client):
    r = _client.query("""
        SELECT
            c.id, c.capability_name, c.capability_description,
            c.domain_id, c.subdomain_id, c.owner_role,
            AVG(ma.maturity_score) AS avg_maturity
        FROM Next_Capability c
        LEFT JOIN Next_MaturityAssessment ma ON ma.capability_id = c.id
        GROUP BY c.id, c.capability_name, c.capability_description,
                 c.domain_id, c.subdomain_id, c.owner_role
        ORDER BY c.domain_id, c.subdomain_id, c.id
    """)
    return r.get("rows", [])


@st.cache_data(ttl=60)
def load_capability_levels(_client):
    r = _client.query("""
        SELECT capability_id, level, level_name, capability_state, key_indicators
        FROM Next_CapabilityLevel
        WHERE level_name IS NOT NULL
        ORDER BY capability_id, level
    """)
    return r.get("rows", [])


@st.cache_data(ttl=60)
def load_use_cases(_client):
    r = _client.query(q_list_next_usecases())
    return r.get("rows", [])


# ── render ────────────────────────────────────────────────────────────────────

def render() -> None:
    client = get_client()

    domains      = load_domain_stats(client)
    dep_mix      = load_dep_mix(client)
    top_sds      = load_top_subdomains(client)
    anchors      = load_anchors(client)
    subdomains   = load_subdomains(client)
    capabilities = load_capabilities_with_maturity(client)
    cap_levels   = load_capability_levels(client)
    use_cases    = load_use_cases(client)

    total_caps = sum(d["capabilities"] for d in domains)
    total_sds  = sum(d["subdomains"]   for d in domains)
    total_deps = sum(d["count"]        for d in dep_mix)
    total_ucs  = len(use_cases)

    payload = json.dumps({
        "domains":      domains,
        "dep_mix":      dep_mix,
        "top_sds":      top_sds,
        "anchors":      anchors,
        "subdomains":   subdomains,
        "capabilities": capabilities,
        "cap_levels":   cap_levels,
        "use_cases":    use_cases,
        "kpis": {
            "domains":      len(domains),
            "subdomains":   total_sds,
            "capabilities": total_caps,
            "dependencies": total_deps,
            "use_cases":    total_ucs,
        },
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
    --bs-body-bg:      #ffffff;
    --bs-body-color:   #1a1a2e;
    --bs-card-bg:      #ffffff;
    --bs-border-color: #e0e4ea;
    --accent:  #0066cc;
    --green:   #1a8a7a;
    --gold:    #c09030;
    --red:     #d04830;
    --purple:  #7c3aed;
    --orange:  #d07020;
  }
  body { font-family:'Inter',sans-serif; background:var(--bs-body-bg); color:var(--bs-body-color); }
  code, .mono { font-family:'JetBrains Mono',monospace; }

  .kpi-card {
    background:#ffffff; border:1px solid #e0e4ea; border-radius:10px;
    padding:1.1rem 1.4rem; transition:border-color .2s;
  }
  .kpi-card:hover { border-color:var(--accent); }
  .kpi-value { font-family:'JetBrains Mono',monospace; font-size:2rem; font-weight:700; line-height:1; color:var(--accent); }
  .kpi-label { font-size:.72rem; color:#8a929a; letter-spacing:.08em; text-transform:uppercase; margin-top:.3rem; }

  .domain-card {
    background:#ffffff; border:1px solid #e0e4ea; border-radius:10px;
    cursor:pointer; padding:1rem 1.1rem;
    transition:transform .18s, box-shadow .18s, border-color .18s;
  }
  .domain-card:hover { transform:translateY(-3px); box-shadow:0 4px 16px rgba(0,0,0,.08); }
  .domain-card.active { border-width:2px !important; }
  .domain-id   { font-family:'JetBrains Mono',monospace; font-size:.68rem; font-weight:700; letter-spacing:.06em; margin-bottom:.4rem; }
  .domain-name { font-size:.82rem; font-weight:700; line-height:1.3; min-height:2.4rem; color:#1a1a2e; margin-bottom:.8rem; }
  .stat-val    { font-family:'JetBrains Mono',monospace; font-size:1.25rem; font-weight:700; }
  .stat-lbl    { font-size:.62rem; color:#8a929a; text-transform:uppercase; }

  #drilldown { display:none; }
  #drilldown.show { display:block; }
  .sd-card {
    background:#f7f8fa; border:1px solid #e0e4ea; border-radius:8px;
    padding:.9rem 1rem; font-size:.78rem; cursor:pointer;
    transition:border-color .15s, background .15s;
  }
  .sd-card:hover { background:#eef1f5; }
  .sd-card.active { border-width:2px !important; background:#eef1f5; }
  .sd-name { font-weight:700; font-size:.8rem; margin-bottom:.3rem; }

  #cap-view { display:none; }
  #cap-view.show { display:block; }
  .cap-card {
    background:#ffffff; border:1px solid #e0e4ea; border-radius:8px;
    padding:.8rem 1rem; cursor:pointer;
    transition:transform .15s, box-shadow .15s, border-color .15s;
  }
  .cap-card:hover { transform:translateY(-2px); box-shadow:0 4px 12px rgba(0,0,0,.08); border-color:#c0c8d0; }
  .cap-name  { font-size:.78rem; font-weight:700; color:#1a1a2e; margin-bottom:.5rem; line-height:1.3; min-height:2.2rem; }
  .pip-track { display:flex; gap:3px; margin-bottom:.4rem; }
  .pip       { flex:1; height:4px; border-radius:2px; }
  .cap-meta  { font-size:.64rem; color:#8a929a; }

  .bc-nav { display:flex; align-items:center; gap:.5rem; font-size:.75rem; color:#8a929a; margin-bottom:1.2rem; font-family:'JetBrains Mono',monospace; }
  .bc-link { color:var(--accent); cursor:pointer; text-decoration:underline; }
  .bc-link:hover { color:#004499; }
  .bc-sep  { color:#c0c8d0; }

  .section-label { font-size:.7rem; letter-spacing:.12em; text-transform:uppercase; color:#5a6570; margin-bottom:1rem; font-family:'JetBrains Mono',monospace; }
  .anchor-row    { margin-bottom:.85rem; }
  .anchor-name   { font-size:.78rem; font-weight:600; color:#1a1a2e; }
  .anchor-domain { font-size:.65rem; color:#8a929a; margin-bottom:.3rem; }
  .anchor-links  { font-family:'JetBrains Mono',monospace; font-size:.7rem; font-weight:700; }

  .table th { font-size:.68rem; letter-spacing:.08em; text-transform:uppercase; color:#8a929a; border-color:#e0e4ea; }
  .table td { font-size:.82rem; border-color:#e0e4ea; vertical-align:middle; }
  .table-hover tbody tr:hover td { background:#f7f8fa; }
  hr.section-divider { border-color:#e0e4ea; margin:2rem 0; }

  .modal-content { background:#ffffff; border:1px solid #e0e4ea; }
  .modal-header  { border-bottom:1px solid #e0e4ea; }
  .modal-footer  { border-top:1px solid #e0e4ea; }

  /* Custom overlay */
  #capOverlay {
    display:none; position:fixed; top:0; left:0; width:100%; height:100%;
    z-index:9999; background:rgba(0,0,0,.3); overflow-y:auto;
    justify-content:center; align-items:flex-start; padding:3vh 1rem;
  }
  #capOverlay.show { display:flex; }
  #capOverlayContent {
    background:#ffffff; border:1px solid #e0e4ea; border-radius:10px;
    width:100%; max-width:800px; max-height:94vh; overflow-y:auto;
    box-shadow:0 12px 40px rgba(0,0,0,.12);
  }
  #capOverlayContent .modal-header { display:flex; align-items:flex-start; padding:1rem 1.2rem; }
  #capOverlayContent .modal-body   { padding:0 1.2rem 1rem; }
  #capOverlayContent .modal-footer  { padding:.8rem 1.2rem; display:flex; justify-content:flex-end; }
  .overlay-close {
    background:none; border:none; color:#8a929a; font-size:1.4rem; cursor:pointer;
    padding:0; line-height:1; margin-left:auto;
  }
  .overlay-close:hover { color:#1a1a2e; }
  .nav-tabs .nav-link        { color:#8a929a; border-color:#e0e4ea; font-size:.78rem; }
  .nav-tabs .nav-link.active { background:#f7f8fa; color:#1a1a2e; border-color:#e0e4ea #e0e4ea #f7f8fa; }
  .nav-tabs .nav-link:hover  { color:#1a1a2e; border-color:#e0e4ea; }
  .tab-content  { background:#f7f8fa; border:1px solid #e0e4ea; border-top:none; border-radius:0 0 6px 6px; padding:1rem; }
  .level-state  { font-size:.8rem; color:#3a3f48; line-height:1.6; margin-bottom:.8rem; }
  .level-indicators { font-size:.75rem; color:#5a6570; }
  .level-badge  { font-family:'JetBrains Mono',monospace; font-size:.65rem; font-weight:700; padding:.25rem .6rem; border-radius:4px; display:inline-block; margin-bottom:.8rem; }
  .maturity-current { font-family:'JetBrains Mono',monospace; font-size:1.6rem; font-weight:700; line-height:1; }
  .owner-badge  { background:#f0f2f5; border:1px solid #e0e4ea; border-radius:4px; padding:.2rem .5rem; font-size:.68rem; color:#5a6570; }
</style>
</head>
<body class="p-3">

<script>const DATA = """
        + payload
        + """;</script>

<!-- Breadcrumb (hidden until drill-down) -->
<div id="breadcrumb-nav" style="display:none" class="mb-2"></div>

<!-- Domain cards + drilldown -->
<div id="view1">
  <div class="section-label">Domain Overview &mdash; click any card to expand, then click a subdomain to view capabilities</div>
  <div class="row g-2 mb-3" id="domain-grid"></div>

  <!-- Subdomain panel -->
  <div id="drilldown" class="mb-4">
    <div class="d-flex align-items-center gap-2 mb-3">
      <div id="dd-dot" class="rounded-circle" style="width:10px;height:10px;flex-shrink:0"></div>
      <span id="dd-title" class="fw-bold" style="font-size:.95rem"></span>
      <span id="dd-badge" class="badge rounded-pill ms-1" style="font-size:.65rem"></span>
      <button class="btn btn-sm ms-auto" id="dd-close"
              style="background:#f0f2f5;border:1px solid #e0e4ea;color:#5a6570;font-size:.7rem">
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
          <span id="modal-subdomain-badge" class="badge" style="background:#f0f2f5;color:#5a6570;font-size:.65rem"></span>
        </div>
        <h6 class="fw-bold" id="modal-cap-name" style="color:#1a1a2e;font-size:.95rem;margin:0"></h6>
      </div>
      <div class="d-flex align-items-center gap-3 ms-auto me-3">
        <div class="text-center">
          <div class="maturity-current" id="modal-maturity-val" style="color:var(--accent)">-</div>
          <div style="font-size:.62rem;color:#8a929a;text-transform:uppercase;letter-spacing:.06em">Avg Maturity</div>
        </div>
      </div>
      <button type="button" class="overlay-close" id="overlay-close-x">&#x2715;</button>
    </div>
    <div class="modal-body">
      <p id="modal-cap-desc" style="font-size:.8rem;color:#5a6570;margin-bottom:1rem"></p>
      <div id="modal-owner" class="mb-3"></div>
      <div class="section-label">Maturity Level Descriptors</div>
      <ul class="nav nav-tabs" id="levelTabs" role="tablist"></ul>
      <div class="tab-content" id="levelTabContent"></div>
    </div>
    <div class="modal-footer">
      <button type="button" class="btn btn-sm" id="overlay-close-btn"
              style="background:#f0f2f5;border:1px solid #e0e4ea;color:#5a6570;font-size:.75rem">
        Close
      </button>
    </div>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
<script>
const DOMAIN_COLORS = ['#0066cc','#d04830','#c09030','#1a8a7a','#7c3aed','#d07020','#2563eb','#0891b2','#9333ea','#be185d','#059669','#6366f1'];
const DEP_COLORS    = ['#d04830','#c09030','#1a8a7a','#0066cc'];
const LEVEL_COLORS  = ['#d04830','#c09030','#d07020','#1a8a7a','#0066cc'];
const LEVEL_NAMES   = ['Ad Hoc','Defined','Integrated','Intelligent','Adaptive'];

// lookup maps
const domainColorMap = {};
DATA.domains.forEach((d,i) => { domainColorMap[d.domain_name] = DOMAIN_COLORS[i % DOMAIN_COLORS.length]; });
const domainById = Object.fromEntries(DATA.domains.map(d => [d.id, d]));
const sdById     = Object.fromEntries(DATA.subdomains.map(s => [s.id, s]));
const capLevelMap = {};
DATA.cap_levels.forEach(cl => {
  if (!capLevelMap[cl.capability_id]) capLevelMap[cl.capability_id] = [];
  capLevelMap[cl.capability_id].push(cl);
});
Object.values(capLevelMap).forEach(arr => arr.sort((a,b) => a.level - b.level));

// state
let activeDomainId   = null;
let activeSubdomainId = null;

// helpers
function fmt(v) {
  const n = parseFloat(v);
  return (!v && v !== 0) || isNaN(n) ? '-' : n.toFixed(1);
}
function renderPips(avg, color) {
  const s = parseFloat(avg) || 0;
  let h = '<div class="pip-track">';
  for (let i = 1; i <= 5; i++) h += `<div class="pip" style="background:${i <= Math.round(s) ? color : '#e0e4ea'}"></div>`;
  return h + '</div>';
}

// Domain cards
const domainGrid = document.getElementById('domain-grid');
DATA.domains.forEach((d,i) => {
  const col   = document.createElement('div');
  col.className = 'col-6 col-md-3';
  const color = DOMAIN_COLORS[i % DOMAIN_COLORS.length];
  col.innerHTML = `<div class="domain-card" id="dc-${d.id}" style="border-top:3px solid ${color}" onclick="toggleDomain(${d.id},'${color}')">
    <div class="domain-id" style="color:${color}">D${d.id}</div>
    <div class="domain-name">${d.domain_name}</div>
    <div class="d-flex gap-3">
      <div><div class="stat-val" style="color:${color}">${d.subdomains}</div><div class="stat-lbl">Subdomains</div></div>
      <div><div class="stat-val" style="color:#1a1a2e">${d.capabilities}</div><div class="stat-lbl">Capabilities</div></div>
      <div><div class="stat-val" style="color:#8a929a">${d.dependencies}</div><div class="stat-lbl">Deps</div></div>
    </div>
  </div>`;
  domainGrid.appendChild(col);
});

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

  const domain = DATA.domains.find(d => d.id === id);
  document.getElementById('dd-dot').style.cssText        = `width:10px;height:10px;flex-shrink:0;background:${color}`;
  document.getElementById('dd-title').textContent        = domain.domain_name;
  document.getElementById('dd-title').style.color        = color;
  document.getElementById('dd-badge').textContent        = `${domain.subdomains} subdomains \u00b7 ${domain.capabilities} capabilities`;
  document.getElementById('dd-badge').style.background   = color + '22';
  document.getElementById('dd-badge').style.color        = color;

  const sds  = DATA.subdomains.filter(s => s.domain_id === id);
  const grid = document.getElementById('sd-grid');
  grid.innerHTML = '';
  sds.forEach(sd => {
    const col = document.createElement('div');
    col.className = 'col-6 col-md-4 col-lg-3';
    col.innerHTML = `<div class="sd-card" id="sdc-${sd.id}" style="border-top:2px solid ${color}" onclick="selectSubdomain(${sd.id},'${color}')">
      <div class="sd-name" style="color:${color}">${sd.subdomain_name}</div>
      <div class="mono" style="font-size:.7rem;color:#8a929a">${sd.cap_count} capabilities</div>
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
  const caps   = DATA.capabilities.filter(c => c.subdomain_id === sdId);
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
    <span style="color:#1a1a2e">${sdName}</span>`;

  const grid = document.getElementById('cap-grid');
  grid.innerHTML = '';
  caps.forEach(cap => {
    const col = document.createElement('div');
    col.className = 'col-6 col-md-4 col-lg-3';
    col.innerHTML = `<div class="cap-card" style="border-top:2px solid ${color}" onclick="openCapModal(${cap.id})">
      <div class="cap-name">${cap.capability_name}</div>
      ${renderPips(cap.avg_maturity, color)}
      <div class="cap-meta">Maturity: <span class="mono" style="color:${color}">${fmt(cap.avg_maturity)}</span></div>
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
  const cap    = DATA.capabilities.find(c => c.id === capId);
  if (!cap) return;
  const domain = domainById[cap.domain_id];
  const sd     = sdById[cap.subdomain_id];
  const color  = domain ? DOMAIN_COLORS[(domain.id - 1) % DOMAIN_COLORS.length] : '#8a929a';
  const levels = capLevelMap[capId] || [];

  document.getElementById('modal-cap-name').textContent      = cap.capability_name;
  document.getElementById('modal-cap-desc').textContent      = cap.capability_description || 'No description available.';
  document.getElementById('modal-maturity-val').textContent  = fmt(cap.avg_maturity);
  document.getElementById('modal-maturity-val').style.color  = color;

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
    content.innerHTML = '<p style="color:#8a929a;font-size:.8rem">No maturity level data available.</p>';
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
        ${indHtml ? `<div style="font-size:.72rem;color:#8a929a;text-transform:uppercase;letter-spacing:.08em;margin-bottom:.4rem">Key Indicators</div>
        <ul style="padding-left:1.2rem;margin:0" class="level-indicators">${indHtml}</ul>` : ''}
      </div>`;
    });
  }

  // Show overlay
  var overlay = document.getElementById('capOverlay');
  overlay.classList.add('show');
  document.getElementById('capOverlayContent').scrollTop = 0;
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