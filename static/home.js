const API_BASE = (() => {
  const path = window.location.pathname;
  if (path.endsWith(".html")) return path.slice(0, path.lastIndexOf("/"));
  if (path.endsWith("/")) return path.slice(0, -1);
  return "";
})();
const GITHUB_REPO_API = "https://api.github.com/repos/zhaisilong/PepPCDB";

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

async function fetchExternalJson(url) {
  const res = await fetch(url, {
    headers: {
      Accept: "application/vnd.github+json",
    },
  });
  if (!res.ok) throw new Error(`Request failed: ${res.status}`);
  return res.json();
}

function renderHomeStats(data) {
  const statsEl = document.getElementById("homeStats");
  const dateEl = document.getElementById("homeDbDate");
  if (dateEl) {
    const releaseDate = data.db_update_date || "-";
    const sourceDate = data.pdb_source_snapshot_date || "-";
    dateEl.textContent = `PepPCDB release date: ${releaseDate} | PDB source snapshot: ${sourceDate}`;
  }
  if (!statsEl) return;
  statsEl.innerHTML = [
    ["Entries", data.entries],
    ["Peptides", data.peptide_chains],
    ["Interfaces", data.peppi_interface_pairs],
    ["Targets", data.target_cards],
    ["Affinity", data.affinity_annotations],
    ["Clusters", data.clusters],
  ]
    .map(
      ([label, value]) =>
        `<div class="stat-card"><div class="stat-label">${esc(label)}</div><div class="stat-val">${fmtNum(value)}</div></div>`
    )
    .join("");
}

async function renderGithubStars() {
  const starsEl = document.getElementById("githubStars");
  if (!starsEl) return;
  try {
    const data = await fetchExternalJson(GITHUB_REPO_API);
    const stars = Number(data.stargazers_count);
    if (!Number.isFinite(stars)) return;
    starsEl.textContent = fmtNum(stars);
    starsEl.classList.remove("is-hidden");
  } catch (err) {
    console.warn("Failed to load GitHub stars", err);
  }
}

async function init() {
  const copyrightYearEl = document.getElementById("copyrightYear");
  if (copyrightYearEl) copyrightYearEl.textContent = String(new Date().getFullYear());
  const hintEl = document.getElementById("entryLinkHint");
  const params = new URLSearchParams(window.location.search);
  const requestedEntry = (params.get("pdb_id") || params.get("entry_key") || "").trim();
  if (hintEl && requestedEntry) {
    const url = `./browse.html?pdb_id=${encodeURIComponent(requestedEntry)}`;
    hintEl.innerHTML = `Looking for ${esc(requestedEntry.toUpperCase())}? <a href="${url}">Open it in Browse</a>.`;
  }
  renderGithubStars();
  renderHomeStats(await fetchJson("/api/stats"));
}

init().catch((err) => {
  console.error(err);
  const statsEl = document.getElementById("homeStats");
  if (statsEl) statsEl.innerHTML = `<p class="muted">Failed to load dataset snapshot: ${esc(err.message)}</p>`;
});
