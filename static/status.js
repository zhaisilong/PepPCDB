const API_BASE = (() => {
  const path = window.location.pathname;
  if (path.endsWith(".html")) return path.slice(0, path.lastIndexOf("/"));
  if (path.endsWith("/")) return path.slice(0, -1);
  return "";
})();

function esc(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function fmtNum(n) {
  return Number(n || 0).toLocaleString();
}

async function fetchJson(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`Request failed: ${res.status}`);
  return res.json();
}

function metric(label, value) {
  return `
    <div class="status-metric">
      <div class="status-label">${esc(label)}</div>
      <div class="status-value">${fmtNum(value)}</div>
    </div>
  `;
}

function renderStatus(stats) {
  const grid = document.getElementById("statusGrid");
  if (!grid) return;
  const groups = [
    {
      title: "Dataset Release",
      note: `PepPCDB release date: ${stats.db_update_date || "-"} | PDB source snapshot: ${stats.pdb_source_snapshot_date || "-"}`,
      metrics: [
        ["Entries", stats.entries],
        ["Clusters", stats.clusters],
        ["CIF Files", stats.cif_files],
      ],
    },
    {
      title: "Structure Index",
      note: "Current SQLite index built from the local filtered_peppi release.",
      metrics: [
        ["Peptide Chains", stats.peptide_chains],
        ["Nonpoly Records", stats.nonpoly],
        ["Connect Records", stats.connect],
      ],
    },
    {
      title: "Interfaces",
      note: "PepPI counts refer to peptide-protein interface pairs.",
      metrics: [
        ["PepPI Interfaces", stats.peppi_interface_pairs],
        ["All Interface Pairs", stats.interface_pairs],
        ["Cyclic Entries", stats.cyclic_pdb_ids],
      ],
    },
    {
      title: "Functional Annotation",
      note: "Manual annotation records merged with the structure index at runtime.",
      metrics: [
        ["Target Cards", stats.target_cards],
        ["Pep Annotations", stats.pep_annotations],
        ["Affinity Entries", stats.affinity_entries],
        ["Affinity Annotations", stats.affinity_annotations],
      ],
    },
  ];
  grid.innerHTML = groups
    .map(
      (group) => `
        <section class="detail status-card">
          <h2>${esc(group.title)}</h2>
          <p class="muted">${esc(group.note)}</p>
          <div class="status-metrics">
            ${group.metrics.map(([label, value]) => metric(label, value)).join("")}
          </div>
        </section>
      `
    )
    .join("");
}

function renderUsage(data) {
  const usageEl = document.getElementById("statusUsage");
  const updatedEl = document.getElementById("statusUsageUpdated");
  if (!usageEl) return;
  usageEl.innerHTML = [
    ["Today Visits", data?.visit_today],
    ["Total Daily Visits", data?.visit_total],
    ["Today Downloads", data?.download_today],
    ["Total Daily Downloads", data?.download_total],
  ]
    .map(
      ([label, value]) => `
        <div class="usage-card">
          <div class="usage-label">${esc(label)}</div>
          <div class="usage-value">${fmtNum(value)}</div>
        </div>
      `
    )
    .join("");
  if (updatedEl) updatedEl.textContent = data?.updated_at ? `Updated at ${data.updated_at}` : "";
}

async function init() {
  const copyrightYearEl = document.getElementById("copyrightYear");
  if (copyrightYearEl) copyrightYearEl.textContent = String(new Date().getFullYear());
  const [stats, usage] = await Promise.all([fetchJson("/api/stats"), fetchJson("/api/usage-stats")]);
  renderStatus(stats);
  renderUsage(usage);
}

init().catch((err) => {
  console.error(err);
  const grid = document.getElementById("statusGrid");
  if (grid) grid.innerHTML = `<section class="detail"><p>Failed to load status: ${esc(err.message)}</p></section>`;
});
