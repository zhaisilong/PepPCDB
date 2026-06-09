const API_BASE = (() => {
  const path = window.location.pathname;
  if (path.endsWith(".html")) return path.slice(0, path.lastIndexOf("/"));
  if (path.endsWith("/")) return path.slice(0, -1);
  return "";
})();

const state = {
  page: 1,
  pageSize: 20,
  total: 0,
  q: "",
  date_from: "",
  date_to: "",
  has_nonstd: "",
  has_affinity: "",
  is_cyclic: "",
  sortBy: "date",
  sortDir: "desc",
  currentEntryKey: "",
  activeTab: "overview",
  selectedPairId: "",
  af3Form: {
    pairId: "",
    chainIds: [],
    seeds: "42",
    jobId: "",
    includePeptideBonds: true,
    includeProteinBonds: false,
  },
  detail: {
    base: null,
    annotations: null,
    interfaces: null,
    structure: null,
    interfaceDetails: {},
    af3Options: null,
    af3Result: null,
  },
};

const statsEl = document.getElementById("stats");
const tableEl = document.getElementById("entryTable");
const detailTitleEl = document.getElementById("detailTitle");
const detailBodyEl = document.getElementById("detailBody");
const pageInfoEl = document.getElementById("pageInfo");
const dbDateEl = document.getElementById("dbDate");
const copyrightYearEl = document.getElementById("copyrightYear");
const dateFromFilterEl = document.getElementById("dateFromFilter");
const dateToFilterEl = document.getElementById("dateToFilter");
const searchInputEl = document.getElementById("searchInput");
const nonstdFilterEl = document.getElementById("nonstdFilter");
const affinityFilterEl = document.getElementById("affinityFilter");
const cyclicFilterEl = document.getElementById("cyclicFilter");
const gotoPageInputEl = document.getElementById("gotoPageInput");
let molstarViewer = null;
let molstarLoadToken = 0;
let molstarScriptPromise = null;
const popoverEl = document.createElement("div");
popoverEl.className = "mod-popover";
popoverEl.style.display = "none";
document.body.appendChild(popoverEl);
let popoverPinned = false;
const SORT_LABELS = {
  date: "Date",
  res: "Res(Å)",
  chains: "Chains",
  peptides: "Peptides",
  nonstd_chains: "Nonstd Chains",
  clusters: "Clusters",
  interfaces: "Interfaces",
};

function fmtNum(n) {
  return Number(n || 0).toLocaleString();
}

function fmtSize(bytes) {
  const n = Number(bytes || 0);
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(2)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

function esc(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatAffinityText(text) {
  const raw = String(text || "").trim();
  if (!raw) return "";
  return raw.replace(
    /(^|[\s(=<>~])([+-]?\d{4,})(\.\d+)?(?=\s*nM\b)/g,
    (match, prefix, intPart, decimalPart = "") => {
      const formatted = Number(intPart).toLocaleString();
      return `${prefix}${formatted}${decimalPart}`;
    }
  );
}

function publicDownloadName(pdbId, fileName) {
  const raw = String(fileName || "").trim();
  const prefix = String(pdbId || "").trim().toLowerCase();
  if (!raw || !prefix) return raw;
  const lower = raw.toLowerCase();
  if (lower === "annotations.json") return `${prefix}_annotations.json`;
  if (lower === "interface.jsonl") return `${prefix}_interface.jsonl`;
  if (lower === "function.json") return `${prefix}_function.json`;
  return raw;
}

function publicDownloadPath(pdbId, fileName) {
  return publicDownloadName(pdbId, fileName);
}

function getUrlEntryKey() {
  try {
    const params = new URLSearchParams(window.location.search);
    const pdbId = params.get("pdb_id") || "";
    if (pdbId) return pdbId;
    return params.get("entry_key") || "";
  } catch {
    return "";
  }
}

function setUrlEntryKey(entryKey) {
  try {
    const url = new URL(window.location.href);
    if (entryKey) url.searchParams.set("pdb_id", entryKey);
    else url.searchParams.delete("pdb_id");
    url.searchParams.delete("entry_key");
    window.history.replaceState({}, "", url.toString());
  } catch {
    // ignore URL update failures
  }
}

function normalizeDoi(raw) {
  let v = String(raw ?? "").trim();
  if (!v) return "";
  v = v.replace(/^doi:\s*/i, "").trim();
  v = v.replace(/^['"]+|['"]+$/g, "").trim();
  return v;
}

function normalizePmid(raw) {
  let v = String(raw ?? "").trim();
  if (!v) return "";
  v = v.replace(/^pmid:\s*/i, "").trim();
  v = v.replace(/^['"]+|['"]+$/g, "").trim();
  return v;
}

function normalizeCitationText(raw) {
  let v = String(raw ?? "").trim();
  if (!v) return "";
  v = v.replace(/^['"]+|['"]+$/g, "").trim();
  v = v.replace(/\s+/g, " ");
  return v;
}

async function fetchJson(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`Request failed: ${res.status}`);
  return res.json();
}

async function fetchJsonPost(path, payload) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    let detail = `Request failed: ${res.status}`;
    try {
      const data = await res.json();
      detail = data.detail || data.error || detail;
    } catch {
      // keep the HTTP status as the fallback message
    }
    throw new Error(detail);
  }
  return res.json();
}

function renderStats(data) {
  if (dbDateEl) {
    const dbDate = data.db_update_date || "-";
    const pdbSnapshotDate = data.pdb_source_snapshot_date || "-";
    dbDateEl.textContent = `PepPCDB Release Date: ${dbDate} | PDB Source Snapshot: ${pdbSnapshotDate}`;
  }
  statsEl.innerHTML = [
    ["Entries", fmtNum(data.entries)],
    ["Peptides", fmtNum(data.peptide_chains)],
    ["Clusters", fmtNum(data.clusters)],
    ["Interfaces", fmtNum(data.peppi_interface_pairs)],
    ["Cyclic", fmtNum(data.cyclic_pdb_ids)],
    ["Affinity", fmtNum(data.affinity_annotations)],
  ]
    .map(
      ([label, value]) =>
        `<div class="stat-card"><div class="stat-label">${label}</div><div class="stat-val">${value}</div></div>`
    )
    .join("");
}

function shortClusterId(clusterId) {
  const v = String(clusterId || "");
  if (!v) return "-";
  return v.length > 10 ? `${v.slice(0, 10)}...` : v;
}

function entryRow(item) {
  const res = item.d_res_high ? Number(item.d_res_high).toFixed(2) : "-";
  const hasPepNonstd = Number(item.nonstd_chain_count || 0) > 0;
  const flag = hasPepNonstd ? '<span class="tag">nonstd</span>' : "";
  const affinity = item.has_affinity ? '<span class="tag">Yes</span>' : "No";
  const cyclic = item.is_cyclic ? "Yes" : "No";
  const cycTypes = (item.cyclic_types || []).join(", ") || "-";
  const clusterTitle = esc(item.cluster_id || "-");
  const clusterLabel = esc(shortClusterId(item.cluster_id));
  const clusterSize = fmtNum(item.cluster_member_count);

  return `
    <tr>
      <td><button class="pdb-btn" data-entry-key="${esc(item.entry_key)}">${esc(item.pdb_id.toUpperCase())}</button>${flag}</td>
      <td>${esc(item.deposition_date || "-")}</td>
      <td>${res}</td>
      <td>${fmtNum(item.chain_count)}</td>
      <td>${fmtNum(item.peptide_chain_count)}</td>
      <td>${fmtNum(item.nonstd_chain_count)}</td>
      <td>${affinity}</td>
      <td><span class="cluster-chip" title="${clusterTitle}">${clusterLabel}</span> (${clusterSize})</td>
      <td>${esc(cyclic)}</td>
      <td>${esc(cycTypes)}</td>
      <td>${fmtNum(item.peppi_interface_pair_count)}</td>
    </tr>
  `;
}

function renderEntries(payload) {
  state.total = payload.total;
  tableEl.innerHTML = payload.items.map(entryRow).join("");

  if (!payload.items.length) {
    tableEl.innerHTML = '<tr><td colspan="11">No result found.</td></tr>';
  }

  const totalPages = Math.max(1, Math.ceil(payload.total / state.pageSize));
  pageInfoEl.textContent = `Page ${state.page} / ${totalPages}`;

  renderSortHeaders();
}

function renderSortHeaders() {
  const sortBtns = document.querySelectorAll(".sort-btn");
  for (const btn of sortBtns) {
    const sortKey = btn.getAttribute("data-sort");
    if (!sortKey) continue;
    const base = SORT_LABELS[sortKey] || sortKey;
    let icon = "↕";
    if (sortKey === state.sortBy) {
      icon = state.sortDir === "asc" ? "↑" : "↓";
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
    btn.innerHTML = `<span>${esc(base)}</span><span class="sort-indicator">${icon}</span>`;
  }
}

function cycleTags(chain) {
  const tags = [];
  if (chain.cyclic_head2tail) tags.push("Head-to-Tail");
  if (chain.cyclic_head2side) tags.push("Head-to-Side");
  if (chain.cyclic_side2tail) tags.push("Side-to-Tail");
  if (chain.cyclic_side2side) tags.push("Side-to-Side");
  if (chain.cyclic_has_cyc_linker) tags.push("Cyclic Linker");
  if (!tags.length && Number(chain.n_cyclic || 0) > 0) tags.push("Cyclic");
  return tags;
}

function renderDetailShell(base) {
  const tabs = [
    ["overview", "Overview"],
    ["annotations", "Annotations"],
    ["structure", "3D Structure"],
    ["interfaces", "Interfaces"],
    ["af3", "AF3 Input"],
  ];

  detailBodyEl.innerHTML = `
    <div class="detail-top">
      <div class="detail-meta">
        <span class="badge">${esc((base.pdb_id || "").toUpperCase())}</span>
        <span class="db-chip">DB ${esc(base.db_update_date || "-")}</span>
      </div>
      <div class="detail-links">
        <a class="ext-link" href="${esc(base.pdb_url || "#")}" target="_blank" rel="noopener noreferrer">RCSB PDB</a>
        <a class="dl-link" href="${API_BASE}/api/download/${esc(base.entry_key)}.zip">Download ZIP</a>
      </div>
    </div>
    <div class="tab-row">
      ${tabs
        .map(
          ([id, label]) =>
            `<button class="tab-btn ${state.activeTab === id ? "active" : ""}" data-tab="${id}">${label}</button>`
        )
        .join("")}
    </div>
    <div id="tabContent" class="tab-content"></div>
  `;
}

function renderFunctionBlocks(base) {
  const renderSemicolonBullets = (text) => {
    const raw = String(text || "").trim();
    if (!raw) return '<div class="muted">-</div>';
    const items = raw
      .split(";")
      .map((x) => x.trim())
      .filter(Boolean);
    if (!items.length) return `<div>${esc(raw)}</div>`;
    return `<ul>${items.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`;
  };
  const blocks = Array.isArray(base.peptide_functions)
    ? base.peptide_functions
    : (Array.isArray(base.function_blocks) ? base.function_blocks : []);
  if (!blocks.length) {
    return '<div class="muted">No peptide functions.</div>';
  }
  return blocks
    .map((b) => {
      const kindRaw = String(b.ligand_kind || "").trim();
      const kindParts = kindRaw ? kindRaw.split(",").map((x) => x.trim()).filter(Boolean) : [];
      const kindUnique = [...new Set(kindParts)];
      const kindLabel =
        kindUnique.length === 1 && kindUnique[0].toLowerCase() === "peptide" ? "" : kindUnique.join(",");
      const chainIds = Array.isArray(b.ligand_chain_ids) ? b.ligand_chain_ids : [];
      const chainLinks = chainIds.length
        ? chainIds
            .map((id) => `<button type="button" class="cluster-member-btn chain-jump-btn" data-chain-id="${esc(id)}">${esc(id)}</button>`)
            .join(" ")
        : esc(b.ligand_chain_id || "-");
      const targets = Array.isArray(b.linked_targets) ? b.linked_targets : [];
      const tags = Array.isArray(b.target_tags) ? b.target_tags : [];
      const targetsHtml = targets.length
        ? targets
            .map((t) => {
              const otLink = t.opentarget_url
                ? `<a class="ext-link" href="${esc(t.opentarget_url)}" target="_blank" rel="noopener noreferrer">OpenTargets</a>`
                : "";
              const targetName = String(t.target_name || "").trim();
              const targetId = String(t.target_id || "").trim();
              const targetLabel = targetName && targetId
                ? `${esc(targetName)} | ${esc(targetId)}`
                : esc(targetName || targetId || "-");
              const canonical = [t.canonical_target_name, t.canonical_target_id].filter(Boolean).join(" | ");
              const canonicalHtml = canonical
                ? `<div><span class="kv">Canonical Target:</span> ${esc(canonical)}</div>`
                : "";
              const targetMetaHtml = t.status || t.updated_at
                ? `<div><span class="kv">Status:</span> ${esc(t.status || "-")} | <span class="kv">Updated:</span> ${esc(t.updated_at || "-")}</div>`
                : "";
              return `<div style="padding:6px 0;border-top:1px dashed var(--line);">
                <div><strong>Target: ${targetLabel}</strong> ${otLink}</div>
                ${canonicalHtml}
                <div><span class="kv">Mechanism:</span> ${renderSemicolonBullets(t.mechanism_text)}</div>
                <div><span class="kv">Notes:</span> ${renderSemicolonBullets(t.notes)}</div>
                ${targetMetaHtml}
              </div>`;
            })
            .join("")
        : `<div><span class="kv">Target Tags:</span> ${esc(tags.join(", ") || "-")}</div>`;
      return `
        <div class="chain-panel">
          <div class="chain-panel-head">
            <strong>Ligand: ${esc(b.ligand_id || "-")} ${kindLabel ? `| ${esc(kindLabel)}` : ""}</strong>
          </div>
          <div><span class="kv">Chains:</span> ${chainLinks}</div>
          <div><span class="kv">Length:</span> ${b.ligand_length ?? "-"} | <span class="kv">Source:</span> ${esc(b.source || "-")}</div>
          <div><span class="kv">Function:</span> ${renderSemicolonBullets(b.function_text)}</div>
          <div><span class="kv">Notes:</span> ${renderSemicolonBullets(b.notes)}</div>
          <div><span class="kv">Affinity:</span> ${esc(formatAffinityText(b.affinity_text) || "-")}</div>
          <div><span class="kv">Status:</span> ${esc(b.status || "-")} | <span class="kv">Updated:</span> ${esc(b.updated_at || "-")}</div>
          ${targetsHtml}
        </div>
      `;
    })
    .join("");
}

function renderOverview() {
  const base = state.detail.base;
  const contentEl = document.getElementById("tabContent");
  if (!base || !contentEl) return;

  const citationsRows = (base.citations || [])
    .map((c) => {
      const doiValue = normalizeDoi(c.doi);
      const pmidValue = normalizePmid(c.pubmed);
      const titleValue = normalizeCitationText(c.title) || "-";
      const journalValue = normalizeCitationText(c.journal) || "-";
      const yearValue = normalizeCitationText(c.year) || "-";
      const doi = doiValue
        ? `<a class="ext-link" target="_blank" rel="noopener noreferrer" href="https://doi.org/${encodeURI(doiValue)}">${esc(doiValue)}</a>`
        : "-";
      const pmid = pmidValue
        ? `<a class="ext-link" target="_blank" rel="noopener noreferrer" href="https://pubmed.ncbi.nlm.nih.gov/${encodeURIComponent(pmidValue)}/">${esc(pmidValue)}</a>`
        : "-";
      return `<tr><td>${esc(titleValue)}</td><td>${esc(journalValue)}</td><td>${esc(yearValue)}</td><td>${doi}</td><td>${pmid}</td></tr>`;
    })
    .join("");

  const filesRows = (base.files || [])
    .map(
      (f) => {
        const displayName = publicDownloadName(base.pdb_id || base.entry_key, f.file_name);
        const downloadPath = publicDownloadPath(base.pdb_id || base.entry_key, f.file_name);
        return `<tr><td><a class="dl-link" href="${API_BASE}/api/download/${esc(base.entry_key)}/${encodeURIComponent(downloadPath)}">${esc(
          displayName
        )}</a></td><td>${esc(f.file_type)}</td><td>${fmtSize(f.size_bytes)}</td></tr>`;
      }
    )
    .join("");
  const functionDownloadName = publicDownloadName(base.pdb_id || base.entry_key, "function.json");
  const functionDownloadRow = `<tr><td><a class="dl-link" href="${API_BASE}/api/download/${esc(base.entry_key)}/${encodeURIComponent(functionDownloadName)}">${esc(functionDownloadName)}</a></td><td>json</td><td>generated</td></tr>`;
  const members = base.cluster_members || [];
  const currentKey = String(base.entry_key || "");
  const memberItems = members
    .map((m) => {
      const isCurrent = String(m.entry_key || "") === currentKey;
      return `<button class="cluster-member-btn ${isCurrent ? "active" : ""}" data-entry-key="${esc(m.entry_key || "")}" type="button">${esc(
        String(m.pdb_id || "").toUpperCase()
      )}${isCurrent ? " (current)" : ""}</button>`;
    })
    .join("");

  contentEl.innerHTML = `
    <p class="tab-intro">Overview of structural metadata and entry-level annotations.</p>
    <div class="detail-grid">
      <div><span class="kv">Method:</span> ${esc(base.exptl_method || "-")}</div>
      <div><span class="kv">Resolution:</span> ${base.d_res_high ? Number(base.d_res_high).toFixed(2) : "-"} Å</div>
      <div><span class="kv">R work / R free:</span> ${base.r_work ?? "-"} / ${base.r_free ?? "-"}</div>
      <div><span class="kv">Chains:</span> ${fmtNum(base.chain_count)}</div>
      <div><span class="kv">Peptide Chains:</span> ${fmtNum(base.peptide_chain_count)}</div>
      <div><span class="kv">Nonstd Chains:</span> ${fmtNum(base.nonstd_chain_count)}</div>
      <div><span class="kv">Nonstd Count:</span> ${fmtNum(base.nonstd_mod_count)}</div>
      <div><span class="kv">Is Cyclic:</span> ${base.is_cyclic ? "Yes" : "No"}</div>
      <div><span class="kv">Cyclic Types:</span> ${esc((base.cyclic_types || []).join(", ") || "-")}</div>
      <div><span class="kv">PepPI Interfaces:</span> ${fmtNum(base.peppi_interface_pair_count)}</div>
      <div><span class="kv">Interface Pairs:</span> ${fmtNum(base.interface_pair_count)}</div>
      <div><span class="kv">PDB Deposition Date:</span> ${esc(base.deposition_date || "-")}</div>
      <div><span class="kv">Cluster Members:</span> ${fmtNum(base.cluster_member_count)}</div>
      <div class="detail-grid-full hash-list"><span class="kv">Cluster ID:</span> <code title="${esc(base.cluster_id || "-")}">${esc(
        base.cluster_id || "-"
      )}</code></div>
      <div class="detail-grid-full hash-list"><span class="kv">All Clusters:</span> ${
        Array.isArray(base.cluster_ids) && base.cluster_ids.length
          ? base.cluster_ids.map((cid) => `<code title="${esc(cid)}">${esc(cid)}</code>`).join(" ")
          : "-"
      }</div>
    </div>

    <h3>Function Annotation & Affinity</h3>
    ${renderFunctionBlocks(base)}

    <h3>Cluster Members</h3>
    <div class="cluster-members">${memberItems || '<span class="muted">-</span>'}</div>

    <h3>Citations</h3>
    <div class="table-wrap">
      <table class="dense-table cite-table">
        <thead><tr><th>Title</th><th>Journal</th><th>Year</th><th>DOI</th><th>PubMed</th></tr></thead>
        <tbody>${citationsRows || '<tr><td colspan="5">-</td></tr>'}</tbody>
      </table>
    </div>

    <h3>Files</h3>
    <div class="table-wrap">
      <table class="dense-table files-table">
        <thead><tr><th>File</th><th>Type</th><th>Size</th></tr></thead>
        <tbody>${filesRows}${functionDownloadRow}</tbody>
      </table>
    </div>
  `;
}

function renderAnnotations() {
  const data = state.detail.annotations;
  const contentEl = document.getElementById("tabContent");
  if (!contentEl) return;
  if (!data) {
    contentEl.innerHTML = '<p class="muted">Loading annotations...</p>';
    return;
  }

  const chains = data.chains
    .map((c) => {
      const cyc = cycleTags(c)
        .map((x) => `<span class="chip">${esc(x)}</span>`)
        .join(" ");
      const modTypes = Array.isArray(c.mod_types) ? c.mod_types : [];
      const modPositions = Array.isArray(c.mod_positions) ? c.mod_positions : [];
      const mods = modTypes.length ? modTypes.join(", ") : "None";
      const pos = modPositions.length ? modPositions.join(", ") : "-";
      return `
        <tr id="chain-row-${esc(c.chain_id)}">
          <td>${esc(c.chain_id)}</td>
          <td>${fmtNum(c.length)}</td>
          <td><code>${esc(c.sequence || "")}</code></td>
          <td>${c.has_nonstd ? "Yes" : "No"}</td>
          <td>${c.mod_has_linker ? "Yes" : "No"}</td>
          <td>${c.cyclic_has_cyc_linker ? "Yes" : "No"}</td>
          <td>${esc(mods)}</td>
          <td>${esc(pos)}</td>
          <td>${cyc || "-"}</td>
        </tr>
      `;
    })
    .join("");

  const nonpoly = data.nonpoly
    .map((x) => `<tr><td>${esc(x.entity_id || "")}</td><td>${esc(x.comp_id || "")}</td><td>${esc(x.name || "")}</td></tr>`)
    .join("");

  const connect = data.connect
    .map(
      (x) => `
      <tr>
        <td>${esc(x.connect_id || "")}</td>
        <td>${esc(x.connect_type || "")}</td>
        <td>${esc(x.leaving_atom || "")}</td>
        <td>${esc(x.ptnr1_chain || "")}:${esc(x.ptnr1_comp || "")}:${esc(x.ptnr1_seq ?? "")}:${esc(x.ptnr1_atom || "")}</td>
        <td>${esc(x.ptnr2_chain || "")}:${esc(x.ptnr2_comp || "")}:${esc(x.ptnr2_seq ?? "")}:${esc(x.ptnr2_atom || "")}</td>
      </tr>
    `
    )
    .join("");

  contentEl.innerHTML = `
    <p class="tab-intro">Annotation summary for peptide chains, nonpoly entities, and connect records.</p>
    <h3>Peptide Chains</h3>
    <div class="table-wrap">
      <table class="dense-table">
        <thead>
          <tr>
            <th>Chain</th><th>Length</th><th>Sequence</th><th>Nonstd</th><th>Linker</th><th>Cyclic Linker</th><th>Mod Types</th><th>Positions</th><th>Cyclic Type</th>
          </tr>
        </thead>
        <tbody>${chains || '<tr><td colspan="9">-</td></tr>'}</tbody>
      </table>
    </div>
    <h3>Nonpoly</h3>
    <div class="table-wrap">
      <table class="dense-table"><thead><tr><th>Entity</th><th>Comp</th><th>Name</th></tr></thead><tbody>${nonpoly || '<tr><td colspan="3">-</td></tr>'}</tbody></table>
    </div>
    <h3>Connect</h3>
    <div class="table-wrap">
      <table class="dense-table"><thead><tr><th>ID</th><th>Type</th><th>Leaving Atom</th><th>Partner 1</th><th>Partner 2</th></tr></thead><tbody>${connect || '<tr><td colspan="5">-</td></tr>'}</tbody></table>
    </div>
  `;
}

function getModMap(chainInfo) {
  const map = new Map();
  if (!chainInfo) return map;
  const positions = chainInfo.mod_positions || [];
  const types = chainInfo.mod_types || [];
  for (let i = 0; i < positions.length; i += 1) {
    const pos = Number(positions[i]);
    if (!Number.isFinite(pos)) continue;
    const t = types[i] || "NONSTD";
    if (!map.has(pos)) map.set(pos, []);
    map.get(pos).push(t);
  }
  return map;
}

function ssClass(ch) {
  if (ch === "H") return "ss-h";
  if (ch === "E") return "ss-e";
  if (ch === "C") return "ss-c";
  return "ss-x";
}

function renderResidueTrack(seqChunk, maskChunk, ssChunk, modMap, startPos) {
  const out = [];
  for (let i = 0; i < seqChunk.length; i += 1) {
    const aa = seqChunk[i] || "";
    const mask = maskChunk[i] || "_";
    const ss = ssChunk[i] || "X";
    const pos = startPos + i;
    const modTypes = modMap.get(pos) || [];
    const classes = ["aa", ssClass(ss)];
    if (mask === "-") classes.push("contact");
    let extra = "";
    if (modTypes.length) {
      classes.push("mod-aa");
      extra = ` data-tip="NONSTD MOD: ${esc(modTypes.join(", "))} @ ${pos}"`;
    }
    out.push(`<span class="${classes.join(" ")}"${extra}>${esc(aa)}</span>`);
  }
  return out.join("");
}

function showModPopover(target, text) {
  if (!target) return;
  popoverEl.textContent = text;
  popoverEl.style.display = "block";
  const rect = target.getBoundingClientRect();
  const x = Math.min(window.innerWidth - popoverEl.offsetWidth - 12, Math.max(8, rect.left));
  const y = Math.min(window.innerHeight - popoverEl.offsetHeight - 12, rect.bottom + 8);
  popoverEl.style.left = `${x}px`;
  popoverEl.style.top = `${y}px`;
}

function hideModPopover(force = false) {
  if (!force && popoverPinned) return;
  popoverEl.style.display = "none";
  popoverPinned = false;
}

function renderChainContinuous(chainLabel, seq, mask, ss, modMap) {
  const seqChunks = splitByLine(seq || "", 80);
  const maskChunks = splitByLine(mask || "", 80);
  const ssChunks = splitByLine(ss || "", 80);
  const rows = seqChunks
    .map((chunk, i) => {
      const start = i * 80 + 1;
      const end = i * 80 + chunk.length;
      return `
        <div class="seq-row">
          <span class="seq-range">${start}-${end}</span>
          <div class="aa-scroll"><div class="aa-track">${renderResidueTrack(
            chunk,
            maskChunks[i] || "",
            ssChunks[i] || "",
            modMap,
            start
          )}</div></div>
        </div>
      `;
    })
    .join("");

  return `
    <div class="align-block">
      <div class="align-title">${esc(chainLabel)}</div>
      ${rows}
    </div>
  `;
}

function renderInterfaceLegend() {
  return `Legend: see <a class="ext-link" href="./about.html#legend-details">About / Legend Details</a>.`;
}

function renderInterfaces() {
  const data = state.detail.interfaces;
  const annotations = state.detail.annotations;
  const contentEl = document.getElementById("tabContent");
  if (!contentEl) return;
  if (!data || !annotations) {
    contentEl.innerHTML = '<p class="muted">Loading interfaces...</p>';
    return;
  }

  const sortedPairs = [...(data.pairs || [])].sort((a, b) => String(a.pair_id || "").localeCompare(String(b.pair_id || "")));
  const pairCards = sortedPairs
    .map(
      (p) => `
      <button class="pair-card ${state.selectedPairId === p.pair_id ? "active" : ""}" data-pair-id="${esc(p.pair_id)}">
        <div class="pair-id">${esc(p.pair_id)}</div>
      </button>
    `
    )
    .join("");

  let detailHtml = '<p class="muted">Select one interface pair to view embedded sequence annotations.</p>';
  if (state.selectedPairId && state.detail.interfaceDetails[state.selectedPairId]) {
    const detail = state.detail.interfaceDetails[state.selectedPairId];
    const activePair = sortedPairs.find((x) => x.pair_id === detail.pair_id) || {};
    const kind = activePair.interface_kind || "other";
    const chainMap = new Map((annotations.chains || []).map((c) => [c.chain_id, c]));
    const c1 = renderChainContinuous(
      `Chain ${detail.chain1_id}`,
      detail.chain1_sequence || "",
      detail.interface_mask1_sequence || "",
      detail.ss1 || "",
      getModMap(chainMap.get(detail.chain1_id))
    );
    const c2 = renderChainContinuous(
      `Chain ${detail.chain2_id}`,
      detail.chain2_sequence || "",
      detail.interface_mask2_sequence || "",
      detail.ss2 || "",
      getModMap(chainMap.get(detail.chain2_id))
    );

    detailHtml = `
      <div class="interface-detail-head">
        <div>
          <strong>${esc(detail.pair_id)}</strong>
          <span class="chip">${esc(kind)}</span>
        </div>
        <div class="pair-meta">
          ${esc(detail.chain1_id)}-${esc(detail.chain2_id)} | Interface: ${fmtNum(activePair.interface_residues1)}/${fmtNum(
            activePair.interface_residues2
          )} | Length: ${fmtNum(activePair.chain1_len)}/${fmtNum(activePair.chain2_len)}
        </div>
      </div>
      <div class="chain-panel">
        ${c1}
      </div>
      <div class="chain-panel">
        ${c2}
      </div>
    `;
  }

  contentEl.innerHTML = `
    <p class="tab-intro">Interface pair view with chain-level sequence coloring and embedded contact/mod annotations. ${renderInterfaceLegend()}</p>
    <div class="pair-layout">
      <div class="pair-list pair-list-horizontal">${pairCards || '<p class="muted">No interface pairs.</p>'}</div>
      <div class="pair-detail">${detailHtml}</div>
    </div>
  `;
}

function renderStructure() {
  const data = state.detail.structure;
  const contentEl = document.getElementById("tabContent");
  if (!contentEl) return;
  if (!data) {
    contentEl.innerHTML = '<p class="muted">Loading structure...</p>';
    return;
  }

  const pdbId = (data.pdb_id || "").toLowerCase();
  if (!pdbId) {
    contentEl.innerHTML = '<p class="muted">No valid PDB ID for Mol* viewer.</p>';
    return;
  }
  const pdbUpper = pdbId.toUpperCase();
  const cifUrl = `${API_BASE}${data.download_url}`;

  contentEl.innerHTML = `
    <p class="tab-intro">Interactive local Mol* rendering from the entry mmCIF file served by PepPCDB.</p>
    <div class="viewer-toolbar">
      <div class="viewer-actions-left">
        <span class="viewer-status" id="molstarStatus">Loading local 3D viewer...</span>
      </div>
      <div class="viewer-actions-right">
        <a class="dl-link" href="${API_BASE}${esc(data.download_url)}">Download CIF</a>
        <a class="ext-link" href="${esc(data.pdb_url || "#")}" target="_blank" rel="noopener noreferrer">RCSB PDB</a>
      </div>
    </div>
    <div class="viewer3d viewer3d-local" id="molstarHost" aria-label="${esc(pdbUpper)} local 3D structure viewer"></div>
    <p class="muted">The viewer loads locally served mmCIF data. Rotate, zoom, and change styles directly in the Mol* controls.</p>
  `;
  window.requestAnimationFrame(() => loadLocalMolstar({ cifUrl, pdbUpper }));
}

function resetAf3Form(options) {
  const defaults = options?.defaults || {};
  state.af3Form = {
    pairId: defaults.pair_id || "",
    chainIds: Array.isArray(defaults.chain_ids) ? [...defaults.chain_ids] : [],
    seeds: Array.isArray(defaults.seeds) ? defaults.seeds.join(",") : "42",
    jobId: defaults.job_id || "",
    includePeptideBonds: defaults.include_peptide_bonds !== false,
    includeProteinBonds: defaults.include_protein_bonds === true,
  };
}

function af3PairById(pairId) {
  const options = state.detail.af3Options;
  return (options?.pairs || []).find((pair) => pair.pair_id === pairId) || null;
}

function af3DefaultChainsForPair(pairId) {
  const pair = af3PairById(pairId);
  return pair && Array.isArray(pair.default_chain_ids) ? [...pair.default_chain_ids] : [];
}

function updateAf3FormFromDom() {
  const pairSelect = document.getElementById("af3PairSelect");
  const seedsInput = document.getElementById("af3SeedsInput");
  const jobInput = document.getElementById("af3JobInput");
  const peptideBondInput = document.getElementById("af3PeptideBonds");
  const proteinBondInput = document.getElementById("af3ProteinBonds");
  const chainInputs = Array.from(document.querySelectorAll(".af3-chain-checkbox"));
  if (pairSelect instanceof HTMLSelectElement) state.af3Form.pairId = pairSelect.value;
  if (seedsInput instanceof HTMLInputElement) state.af3Form.seeds = seedsInput.value.trim();
  if (jobInput instanceof HTMLInputElement) state.af3Form.jobId = jobInput.value.trim();
  if (peptideBondInput instanceof HTMLInputElement) state.af3Form.includePeptideBonds = peptideBondInput.checked;
  if (proteinBondInput instanceof HTMLInputElement) state.af3Form.includeProteinBonds = proteinBondInput.checked;
  state.af3Form.chainIds = chainInputs
    .filter((input) => input instanceof HTMLInputElement && input.checked)
    .map((input) => input.getAttribute("data-chain-id"))
    .filter(Boolean);
}

function af3PayloadFromForm() {
  updateAf3FormFromDom();
  const seeds = state.af3Form.seeds
    .split(/[,\s;]+/)
    .map((x) => x.trim())
    .filter(Boolean)
    .map((x) => Number(x));
  return {
    pair_id: state.af3Form.pairId || null,
    chain_ids: state.af3Form.chainIds,
    seeds: seeds.length ? seeds : [42],
    job_id: state.af3Form.jobId || state.detail.af3Options?.defaults?.job_id || state.currentEntryKey,
    include_peptide_bonds: state.af3Form.includePeptideBonds,
    include_protein_bonds: state.af3Form.includeProteinBonds,
  };
}

function af3ChainBadges(chain) {
  const tags = [chain.role || "protein"];
  if (chain.has_nonstd) tags.push("nonstd");
  if (chain.is_cyclic) tags.push("cyclic");
  if (chain.mod_has_linker) tags.push("linker");
  return tags.map((tag) => `<span class="chip">${esc(tag)}</span>`).join(" ");
}

function af3ChainCard(chain) {
  const checked = state.af3Form.chainIds.includes(chain.chain_id) ? "checked" : "";
  const modTypes = Array.isArray(chain.mod_types) && chain.mod_types.length ? chain.mod_types.join(", ") : "-";
  const modPositions =
    Array.isArray(chain.mod_positions) && chain.mod_positions.length ? chain.mod_positions.join(", ") : "-";
  return `
    <label class="af3-chain-option">
      <input class="af3-chain-checkbox" type="checkbox" data-chain-id="${esc(chain.chain_id)}" ${checked} />
      <span class="af3-chain-body">
        <span class="af3-chain-title">Chain ${esc(chain.chain_id)} ${af3ChainBadges(chain)}</span>
        <span class="af3-chain-meta">Length ${fmtNum(chain.length)} | ${esc(chain.polymer_type || "-")}</span>
        <span class="af3-chain-meta">Mods: ${esc(modTypes)} | Positions: ${esc(modPositions)}</span>
      </span>
    </label>
  `;
}

function renderAf3Input() {
  const contentEl = document.getElementById("tabContent");
  if (!contentEl) return;
  const options = state.detail.af3Options;
  if (!options) {
    contentEl.innerHTML = '<p class="muted">Loading AF3 input options...</p>';
    return;
  }

  const pairs = options.pairs || [];
  const chains = options.chains || [];
  const result = state.detail.af3Result;
  const pairOptions = pairs
    .map((pair) => {
      const selected = state.af3Form.pairId === pair.pair_id ? "selected" : "";
      const label = `${pair.pair_id} (${pair.chain1_id}-${pair.chain2_id}, ${pair.interface_kind})`;
      return `<option value="${esc(pair.pair_id)}" ${selected}>${esc(label)}</option>`;
    })
    .join("");
  const summary = result?.summary
    ? `<div class="af3-summary">
        <span>Chains: ${fmtNum(result.summary.chain_count)}</span>
        <span>Seeds: ${fmtNum(result.summary.seed_count)}</span>
        <span>Bonds: ${fmtNum(result.summary.bond_count)}</span>
        <span>Modifications: ${fmtNum(result.summary.modification_count)}</span>
      </div>`
    : "";
  const warnings = Array.isArray(result?.warnings) && result.warnings.length
    ? `<div class="af3-warnings">${result.warnings.map((x) => `<div>${esc(x)}</div>`).join("")}</div>`
    : "";
  const jsonText = result?.config ? JSON.stringify(result.config, null, 2) : "";

  contentEl.innerHTML = `
    <p class="tab-intro">
      Generate an AlphaFold 3 JSON input from this PepPCDB entry. See
      <a class="ext-link" href="./docs/input.md" target="_blank" rel="noopener noreferrer">AF3 input format</a>.
    </p>
    <div class="af3-layout">
      <div class="chain-panel af3-controls">
        <div class="af3-field">
          <label for="af3PairSelect">PepPI Pair</label>
          <select id="af3PairSelect">${pairOptions}</select>
        </div>
        <div class="af3-field-grid">
          <label class="af3-field" for="af3JobInput">
            <span>Job ID</span>
            <input id="af3JobInput" type="text" value="${esc(state.af3Form.jobId || options.defaults?.job_id || "")}" />
          </label>
          <label class="af3-field" for="af3SeedsInput">
            <span>Seeds</span>
            <input id="af3SeedsInput" type="text" value="${esc(state.af3Form.seeds || "42")}" placeholder="42 or 42,55" />
          </label>
        </div>
        <div class="af3-toggle-row">
          <label><input id="af3PeptideBonds" type="checkbox" ${state.af3Form.includePeptideBonds ? "checked" : ""} /> Peptide bonds</label>
          <label><input id="af3ProteinBonds" type="checkbox" ${state.af3Form.includeProteinBonds ? "checked" : ""} /> Protein bonds</label>
        </div>
        <h3>Chains</h3>
        <div class="af3-chain-grid">${chains.map(af3ChainCard).join("") || '<p class="muted">No chains available.</p>'}</div>
        <div class="af3-action-row">
          <button id="af3GenerateBtn" type="button">Generate AF3 JSON</button>
        </div>
      </div>
      <div class="chain-panel af3-output">
        <div class="chain-panel-head">
          <strong>Generated Input</strong>
          <div class="af3-output-actions">
            <button id="af3CopyBtn" type="button" ${jsonText ? "" : "disabled"}>Copy</button>
            <button id="af3DownloadBtn" type="button" ${jsonText ? "" : "disabled"}>Download</button>
          </div>
        </div>
        ${summary}
        ${warnings}
        <pre class="af3-json"><code id="af3JsonOutput">${esc(jsonText || "Select chains and generate an AF3 JSON input.")}</code></pre>
      </div>
    </div>
  `;
}

function renderActiveTab() {
  if (state.activeTab !== "structure") disposeMolstarViewer();
  if (state.activeTab === "overview") return renderOverview();
  if (state.activeTab === "annotations") return renderAnnotations();
  if (state.activeTab === "structure") return renderStructure();
  if (state.activeTab === "af3") return renderAf3Input();
  return renderInterfaces();
}

function setMolstarStatus(message, isError = false) {
  const el = document.getElementById("molstarStatus");
  if (!el) return;
  el.textContent = message;
  el.classList.toggle("viewer-status-error", isError);
}

function disposeMolstarViewer() {
  if (!molstarViewer) return;
  try {
    molstarViewer.dispose();
  } catch (err) {
    console.warn("Failed to dispose Mol* viewer:", err);
  }
  molstarViewer = null;
}

async function loadLocalMolstar({ cifUrl, pdbUpper }) {
  const host = document.getElementById("molstarHost");
  if (!host) return;
  const token = ++molstarLoadToken;
  disposeMolstarViewer();
  setMolstarStatus("Loading local Mol* assets...");
  try {
    await ensureMolstarScript();
  } catch (err) {
    setMolstarStatus(`Local Mol* assets failed to load: ${err.message || err}`, true);
    return;
  }
  if (!window.molstar || !window.molstar.Viewer) {
    setMolstarStatus("Local Mol* assets are unavailable.", true);
    return;
  }

  try {
    molstarViewer = await window.molstar.Viewer.create(host, {
      layoutIsExpanded: false,
      layoutShowControls: true,
      layoutShowRemoteState: false,
      layoutShowSequence: false,
      layoutShowLog: false,
      layoutShowLeftPanel: false,
      viewportShowExpand: true,
      viewportShowSelectionMode: false,
      viewportShowAnimation: false,
      pdbProvider: "rcsb",
      emdbProvider: "rcsb",
    });
    if (token !== molstarLoadToken) {
      disposeMolstarViewer();
      return;
    }
    await molstarViewer.loadStructureFromUrl(cifUrl, "mmcif", false, { label: pdbUpper });
    setMolstarStatus(`Loaded ${pdbUpper} from local mmCIF.`);
  } catch (err) {
    console.error(err);
    disposeMolstarViewer();
    setMolstarStatus(`Local 3D rendering failed: ${err.message || err}`, true);
  }
}

function ensureMolstarScript() {
  if (window.molstar && window.molstar.Viewer) return Promise.resolve();
  if (molstarScriptPromise) return molstarScriptPromise;
  molstarScriptPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = `${API_BASE}/vendor/molstar/molstar.js`;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("molstar.js could not be loaded"));
    document.head.appendChild(script);
  });
  return molstarScriptPromise;
}

async function loadDetail(entryKey) {
  disposeMolstarViewer();
  state.currentEntryKey = entryKey;
  setUrlEntryKey(entryKey);
  state.activeTab = "overview";
  state.selectedPairId = "";
  state.detail = {
    base: null,
    annotations: null,
    interfaces: null,
    structure: null,
    interfaceDetails: {},
    af3Options: null,
    af3Result: null,
  };

  detailTitleEl.textContent = "Loading...";
  detailBodyEl.innerHTML = '<p class="muted">Loading entry details...</p>';

  const [base, annotations, interfaces, structure, af3Options] = await Promise.all([
    fetchJson(`/api/entries/${encodeURIComponent(entryKey)}`),
    fetchJson(`/api/entries/${encodeURIComponent(entryKey)}/annotations`),
    fetchJson(`/api/entries/${encodeURIComponent(entryKey)}/interfaces`),
    fetchJson(`/api/entries/${encodeURIComponent(entryKey)}/structure`),
    fetchJson(`/api/entries/${encodeURIComponent(entryKey)}/af3-options`),
  ]);

  if (state.currentEntryKey !== entryKey) return;

  state.detail.base = base;
  state.detail.annotations = annotations;
  state.detail.interfaces = interfaces;
  state.detail.structure = structure;
  state.detail.af3Options = af3Options;
  resetAf3Form(af3Options);
  if (interfaces && interfaces.pairs && interfaces.pairs.length > 0) {
    const firstPair = [...interfaces.pairs].sort((a, b) => String(a.pair_id || "").localeCompare(String(b.pair_id || "")))[0];
    state.selectedPairId = firstPair.pair_id;
    try {
      state.detail.interfaceDetails[firstPair.pair_id] = await fetchJson(
        `/api/entries/${encodeURIComponent(state.currentEntryKey)}/interfaces/${encodeURIComponent(firstPair.pair_id)}`
      );
    } catch {
      // keep page usable if first pair detail fails
    }
  }

  detailTitleEl.textContent = `${(base.pdb_id || "").toUpperCase()} Details`;
  renderDetailShell(base);
  renderActiveTab();
}

async function loadInterfacePair(pairId) {
  if (!state.currentEntryKey) return;
  if (!state.detail.interfaceDetails[pairId]) {
    state.detail.interfaceDetails[pairId] = await fetchJson(
      `/api/entries/${encodeURIComponent(state.currentEntryKey)}/interfaces/${encodeURIComponent(pairId)}`
    );
  }
  state.selectedPairId = pairId;
  renderInterfaces();
}

async function generateAf3Input() {
  const payload = af3PayloadFromForm();
  if (!payload.chain_ids.length) {
    throw new Error("Select at least one chain.");
  }
  if (payload.seeds.some((x) => !Number.isInteger(x))) {
    throw new Error("Seeds must be integers.");
  }
  state.detail.af3Result = await fetchJsonPost(
    `/api/entries/${encodeURIComponent(state.currentEntryKey)}/af3-input`,
    payload
  );
  renderAf3Input();
}

async function copyAf3Json() {
  const config = state.detail.af3Result?.config;
  if (!config) return;
  const text = JSON.stringify(config, null, 2);
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const temp = document.createElement("textarea");
  temp.value = text;
  temp.style.position = "fixed";
  temp.style.left = "-9999px";
  document.body.appendChild(temp);
  temp.focus();
  temp.select();
  document.execCommand("copy");
  temp.remove();
}

function downloadAf3Json() {
  const config = state.detail.af3Result?.config;
  if (!config) return;
  const text = JSON.stringify(config, null, 2) + "\n";
  const name = `${config.name || state.currentEntryKey || "peppcdb"}_af3_input.json`;
  const blob = new Blob([text], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function loadStats() {
  renderStats(await fetchJson("/api/stats"));
}

async function loadEntries() {
  const params = new URLSearchParams({
    page: String(state.page),
    page_size: String(state.pageSize),
    sort_by: state.sortBy,
    sort_dir: state.sortDir,
  });
  if (state.q) params.set("q", state.q);
  if (state.date_from) params.set("date_from", state.date_from);
  if (state.date_to) params.set("date_to", state.date_to);
  if (state.has_nonstd) params.set("has_nonstd", state.has_nonstd);
  if (state.has_affinity) params.set("has_affinity", state.has_affinity);
  if (state.is_cyclic) params.set("is_cyclic", state.is_cyclic);

  renderEntries(await fetchJson(`/api/entries?${params.toString()}`));
}

async function search() {
  state.page = 1;
  state.q = searchInputEl.value.trim();
  state.date_from = dateFromFilterEl?.value?.trim() || "";
  state.date_to = dateToFilterEl?.value?.trim() || "";
  state.has_nonstd = nonstdFilterEl.value;
  state.has_affinity = affinityFilterEl.value;
  state.is_cyclic = cyclicFilterEl.value;
  await loadEntries();
}

function bindDetailEvents() {
  detailBodyEl.addEventListener("mouseover", (e) => {
    const target = e.target;
    if (!(target instanceof HTMLElement)) return;
    if (!target.classList.contains("mod-aa")) return;
    const tip = target.getAttribute("data-tip");
    if (!tip) return;
    if (!popoverPinned) showModPopover(target, tip);
  });

  detailBodyEl.addEventListener("mousemove", (e) => {
    const target = e.target;
    if (!(target instanceof HTMLElement)) return;
    if (!target.classList.contains("mod-aa")) return;
    const tip = target.getAttribute("data-tip");
    if (!tip) return;
    if (!popoverPinned) showModPopover(target, tip);
  });

  detailBodyEl.addEventListener("change", (e) => {
    const target = e.target;
    if (!(target instanceof HTMLElement)) return;
    if (target.id === "af3PairSelect" && target instanceof HTMLSelectElement) {
      updateAf3FormFromDom();
      state.af3Form.pairId = target.value;
      state.af3Form.chainIds = af3DefaultChainsForPair(target.value);
      state.detail.af3Result = null;
      renderAf3Input();
      return;
    }
    if (
      target.classList.contains("af3-chain-checkbox") ||
      target.id === "af3PeptideBonds" ||
      target.id === "af3ProteinBonds"
    ) {
      updateAf3FormFromDom();
      state.detail.af3Result = null;
      renderAf3Input();
    }
  });

  detailBodyEl.addEventListener("click", async (e) => {
    const target = e.target;
    if (target instanceof HTMLElement && target.classList.contains("mod-aa")) {
      const tip = target.getAttribute("data-tip");
      if (tip) {
        popoverPinned = !popoverPinned;
        if (popoverPinned) {
          showModPopover(target, tip);
        } else {
          hideModPopover(true);
        }
      }
      return;
    }
    hideModPopover(true);
    const target2 = e.target;
    if (!(target2 instanceof HTMLElement)) return;

    const af3GenerateBtn = target2.closest("#af3GenerateBtn");
    if (af3GenerateBtn instanceof HTMLElement) {
      af3GenerateBtn.textContent = "Generating...";
      try {
        await generateAf3Input();
      } catch (err) {
        state.detail.af3Result = {
          config: null,
          summary: null,
          warnings: [err.message || String(err)],
        };
        renderAf3Input();
      }
      return;
    }

    const af3CopyBtn = target2.closest("#af3CopyBtn");
    if (af3CopyBtn instanceof HTMLElement) {
      await copyAf3Json();
      af3CopyBtn.textContent = "Copied";
      window.setTimeout(() => {
        const btn = document.getElementById("af3CopyBtn");
        if (btn) btn.textContent = "Copy";
      }, 1200);
      return;
    }

    const af3DownloadBtn = target2.closest("#af3DownloadBtn");
    if (af3DownloadBtn instanceof HTMLElement) {
      downloadAf3Json();
      return;
    }

    const tabBtn = target2.closest(".tab-btn");
    if (tabBtn instanceof HTMLElement) {
      const tab = tabBtn.getAttribute("data-tab");
      if (!tab || !state.detail.base) return;
      state.activeTab = tab;
      renderDetailShell(state.detail.base);
      renderActiveTab();
      return;
    }

    const chainJumpBtn = target2.closest(".chain-jump-btn");
    if (chainJumpBtn instanceof HTMLElement) {
      const chainId = chainJumpBtn.getAttribute("data-chain-id");
      if (!chainId || !state.detail.base) return;
      state.activeTab = "annotations";
      renderDetailShell(state.detail.base);
      renderActiveTab();
      window.requestAnimationFrame(() => {
        const row = document.getElementById(`chain-row-${chainId}`);
        if (row) {
          row.scrollIntoView({ behavior: "smooth", block: "center" });
          row.style.outline = "2px solid rgba(78,145,255,0.55)";
          window.setTimeout(() => {
            row.style.outline = "";
          }, 1400);
        }
      });
      return;
    }

    const pairCard = target2.closest(".pair-card");
    if (pairCard instanceof HTMLElement) {
      const pairId = pairCard.getAttribute("data-pair-id");
      if (!pairId) return;
      await loadInterfacePair(pairId);
      return;
    }

    const memberBtn = target2.closest(".cluster-member-btn");
    if (memberBtn instanceof HTMLElement) {
      const entryKey = memberBtn.getAttribute("data-entry-key");
      if (!entryKey || entryKey === state.currentEntryKey) return;
      await loadDetail(entryKey);
      return;
    }

  });

  document.addEventListener("click", (e) => {
    const target = e.target;
    if (!(target instanceof HTMLElement)) return;
    if (!target.classList.contains("mod-aa")) {
      hideModPopover(true);
    }
  });
}

async function init() {
  if (copyrightYearEl) {
    copyrightYearEl.textContent = String(new Date().getFullYear());
  }
  document.getElementById("searchBtn").addEventListener("click", () => search());
  searchInputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter") search();
  });

  document.getElementById("prevBtn").addEventListener("click", async () => {
    if (state.page <= 1) return;
    state.page -= 1;
    await loadEntries();
  });

  document.getElementById("nextBtn").addEventListener("click", async () => {
    const totalPages = Math.max(1, Math.ceil(state.total / state.pageSize));
    if (state.page >= totalPages) return;
    state.page += 1;
    await loadEntries();
  });

  document.getElementById("gotoPageBtn").addEventListener("click", async () => {
    const totalPages = Math.max(1, Math.ceil(state.total / state.pageSize));
    const raw = Number(gotoPageInputEl?.value || "");
    if (!Number.isFinite(raw)) return;
    const page = Math.floor(raw);
    if (page < 1 || page > totalPages || page === state.page) return;
    state.page = page;
    await loadEntries();
  });
  gotoPageInputEl?.addEventListener("keydown", async (e) => {
    if (e.key !== "Enter") return;
    const btn = document.getElementById("gotoPageBtn");
    if (btn instanceof HTMLButtonElement) btn.click();
  });

  document.querySelector("thead")?.addEventListener("click", async (e) => {
    const target = e.target;
    if (!(target instanceof HTMLElement)) return;
    const btn = target.closest(".sort-btn");
    if (!(btn instanceof HTMLElement)) return;
    const sortKey = btn.getAttribute("data-sort");
    if (!sortKey) return;
    if (state.sortBy === sortKey) {
      state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
    } else {
      state.sortBy = sortKey;
      state.sortDir = "desc";
    }
    state.page = 1;
    await loadEntries();
  });

  tableEl.addEventListener("click", async (e) => {
    const target = e.target;
    if (!(target instanceof HTMLElement)) return;
    if (!target.classList.contains("pdb-btn")) return;
    const entryKey = target.getAttribute("data-entry-key");
    if (!entryKey) return;
    await loadDetail(entryKey);
    document.getElementById("detailPanel").scrollIntoView({ behavior: "smooth", block: "start" });
  });

  bindDetailEvents();
  await loadStats();
  await loadEntries();
  const initialEntryKey = getUrlEntryKey().trim();
  if (initialEntryKey) {
    try {
      await loadDetail(initialEntryKey);
      document.getElementById("detailPanel")?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
      console.warn("Failed to open entry from URL:", initialEntryKey, err);
    }
  }
}

init().catch((err) => {
  console.error(err);
  detailBodyEl.innerHTML = `<p>Failed to load data from backend API: ${esc(err.message)}</p>`;
});
function splitByLine(text, width = 80) {
  const chunks = [];
  for (let i = 0; i < text.length; i += width) {
    chunks.push(text.slice(i, i + width));
  }
  return chunks;
}
