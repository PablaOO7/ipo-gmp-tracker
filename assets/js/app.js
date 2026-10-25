const $ = (selector) => document.querySelector(selector);
const money = (n) => n == null ? "—" : `₹${Number(n).toLocaleString("en-IN")}`;
const date = (s) => {
  if (!s) return "—";
  return new Date(`${s}T00:00:00Z`).toLocaleDateString("en-IN", {
    day: "numeric", month: "short", year: "numeric", timeZone: "UTC"
  });
};
const escapeHTML = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
}[c]));

let ipos = [], statusData = {}, expandedId = null, chart = null;

async function loadData() {
  const [ipoResponse, statusResponse] = await Promise.all([
    fetch("data/ipos.json", { cache: "no-store" }),
    fetch("data/status.json", { cache: "no-store" })
  ]);
  if (!ipoResponse.ok || !statusResponse.ok) throw new Error("Could not load JSON data");
  const ipoData = await ipoResponse.json();
  statusData = await statusResponse.json();
  if (!Array.isArray(ipoData.ipos)) throw new Error("Invalid IPO dataset");
  ipos = ipoData.ipos;
  $("#demoNotice").hidden = !ipoData.demo;
  $("#updatedAt").textContent = ipoData.demo ? "Illustrative sample dataset" : (ipos.length ? "Data loaded" : "Waiting for first successful collection");
  renderAll();
}
function currentGmp(ipo) { return Number(ipo.gmpHistory?.at(-1)?.value ?? ipo.gmp ?? 0); }
function gmpPercent(ipo) {
  const price = Number(ipo.issuePriceHigh || ipo.issuePriceLow || 0);
  return price > 0 ? currentGmp(ipo) / price * 100 : 0;
}
function dailyChange(ipo) {
  const history = ipo.gmpHistory || [];
  return history.length < 2 ? null : Number(history.at(-1).value) - Number(history.at(-2).value);
}
function changeClass(change) { return change == null ? "flat" : change > 0 ? "up" : change < 0 ? "down" : "flat"; }
function statsMarkup() {
  const active = ipos.filter(i => ["Open", "Upcoming"].includes(i.status)).length;
  const qualifying = ipos.filter(i => gmpPercent(i) > 20).length;
  const highest = ipos.length ? Math.max(...ipos.map(gmpPercent)) : 0;
  return [
    ["Tracked IPOs", ipos.length, "Across Mainboard and SME"],
    ["Open / Upcoming", active, "Issue calendar"],
    ["GMP above 20%", qualifying, "Latest sample observation"],
    ["Highest GMP", `${highest.toFixed(1)}%`, "Against upper issue price"]
  ].map(([label, value, note]) => `<div class="stat"><span>${label}</span><strong>${value}</strong><small>${note}</small></div>`).join("");
}
function filteredIpos() {
  const query = $("#searchInput").value.trim().toLowerCase();
  const category = $("#categoryFilter").value, status = $("#statusFilter").value;
  const onlyHigh = $("#gmpFilter").checked, sort = $("#sortFilter").value;
  const rows = ipos.filter(i => i.company.toLowerCase().includes(query) &&
    (category === "All" || i.category === category) &&
    (status === "All" || i.status === status) && (!onlyHigh || gmpPercent(i) > 20));
  rows.sort((a, b) => {
    if (sort === "change") return (dailyChange(b) ?? -Infinity) - (dailyChange(a) ?? -Infinity);
    if (sort === "date") return (a.closeDate || "9999").localeCompare(b.closeDate || "9999");
    if (sort === "name") return a.company.localeCompare(b.company);
    return gmpPercent(b) - gmpPercent(a);
  });
  return rows;
}
function cardMarkup(ipo) {
  const gmp = currentGmp(ipo), pct = gmpPercent(ipo), change = dailyChange(ipo);
  const klass = changeClass(change), expanded = expandedId === ipo.id, history = ipo.gmpHistory || [];
  const max = Math.max(1, ...history.map(h => Number(h.value)));
  const price = Number(ipo.issuePriceHigh || ipo.issuePriceLow || 0), estimate = price + gmp;
  return `<article class="ipo-card">
    <div class="ipo-main" role="button" tabindex="0" data-expand="${escapeHTML(ipo.id)}" aria-expanded="${expanded}">
      <div><div class="company-line"><h3>${escapeHTML(ipo.company)}</h3><span class="tag">${escapeHTML(ipo.category)}</span></div>
      <p class="muted">${escapeHTML(ipo.status)} · Closes ${date(ipo.closeDate)}</p><p class="muted">Issue price ${money(ipo.issuePriceLow)}–${money(ipo.issuePriceHigh)}</p></div>
      <div><div class="gmp-value">${money(gmp)}</div><div class="${klass}">${pct.toFixed(1)}% · ${change == null ? "—" : `${change > 0 ? "+" : ""}${money(change)}`}</div></div>
      <div><div class="muted">Daily GMP magnitude</div><div class="bar-track"><div class="bar-fill ${klass}" style="width:${Math.min(100, gmp / max * 100)}%"></div></div><p class="muted">Latest recorded value</p></div>
      <div class="expand-indicator">${expanded ? "−" : "+"}</div>
    </div>
    ${expanded ? `<div class="ipo-details"><div class="detail-grid">
      <div class="detail-item"><span>Estimated listing price*</span><strong>${money(estimate)}</strong></div>
      <div class="detail-item"><span>Estimated gain*</span><strong>${pct.toFixed(1)}%</strong></div>
      <div class="detail-item"><span>Issue size</span><strong>${ipo.issueSizeCr == null ? "—" : `₹${ipo.issueSizeCr} Cr`}</strong></div>
      <div class="detail-item"><span>Lot size</span><strong>${ipo.lotSize ?? "—"}</strong></div>
      <div class="detail-item"><span>Open date</span><strong>${date(ipo.openDate)}</strong></div>
      <div class="detail-item"><span>Close date</span><strong>${date(ipo.closeDate)}</strong></div>
      <div class="detail-item"><span>Allotment</span><strong>${date(ipo.allotmentDate)}</strong></div>
      <div class="detail-item"><span>Expected listing</span><strong>${date(ipo.listingDate)}</strong></div></div>
      <p class="muted">*Illustrative estimate uses the upper issue price plus the latest GMP. It is not a prediction or guarantee.</p>
      <h3 class="history-title">Daily GMP bars</h3><div class="bar-history">${history.map((h, idx) => {
        const prev = idx ? Number(history[idx - 1].value) : null;
        const delta = prev == null ? null : Number(h.value) - prev, c = changeClass(delta);
        return `<div class="history-row"><span class="history-date">${date(h.date)}</span><div class="bar-track"><div class="bar-fill ${c}" style="width:${Math.max(1, Number(h.value) / max * 100)}%"></div></div><span class="history-value">${money(h.value)}</span></div>`;
      }).join("")}</div><h3 class="history-title">GMP trend</h3><div class="chart-wrap"><canvas id="chart-${escapeHTML(ipo.id)}" aria-label="Daily GMP line chart"></canvas></div>
    </div>` : ""}</article>`;
}
function renderCards() {
  const rows = filteredIpos();
  $("#resultCount").textContent = `${rows.length} IPO${rows.length === 1 ? "" : "s"}`;
  $("#emptyState").hidden = rows.length !== 0;
  $("#ipoList").innerHTML = rows.map(cardMarkup).join("");
  if (expandedId && rows.some(i => i.id === expandedId)) renderChart(rows.find(i => i.id === expandedId));
  else if (chart) { chart.destroy(); chart = null; }
}
function renderChart(ipo) {
  const canvas = document.getElementById(`chart-${ipo.id}`);
  if (!canvas || typeof Chart === "undefined") return;
  if (chart) chart.destroy();
  const history = ipo.gmpHistory || [];
  chart = new Chart(canvas, {
    type: "line",
    data: { labels: history.map(h => date(h.date)), datasets: [{
      label: "GMP", data: history.map(h => Number(h.value)), borderColor: "#36c5a0",
      backgroundColor: "#36c5a0", pointRadius: 4, pointHoverRadius: 6, borderWidth: 2, tension: 0.2
    }] },
    options: { responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: ctx => `GMP: ${money(ctx.raw)}` } } },
      scales: { x: { grid: { display: false }, ticks: { color: "#9aabc2", maxRotation: 0, autoSkip: true } },
        y: { beginAtZero: true, grid: { color: "#293951" }, ticks: { color: "#9aabc2", callback: v => `₹${v}` } } }
    },
    plugins: [{ id: "pointLabelsAndGuides", afterDatasetsDraw(c) {
      const ctx = c.ctx, meta = c.getDatasetMeta(0); ctx.save(); ctx.font = "12px system-ui"; ctx.textAlign = "center";
      meta.data.forEach((point, index) => {
        const p = point.getProps(["x", "y"], true);
        ctx.setLineDash([3, 4]); ctx.strokeStyle = "#70819a"; ctx.beginPath();
        ctx.moveTo(p.x, p.y + 5); ctx.lineTo(p.x, c.chartArea.bottom); ctx.stroke(); ctx.setLineDash([]);
        ctx.fillStyle = "#edf3fb"; ctx.fillText(money(history[index].value), p.x, p.y - 10);
      }); ctx.restore();
    }}]
  });
}
function renderTables() {
  $("#calendarContent").innerHTML = `<table><thead><tr><th>Company</th><th>Type</th><th>Status</th><th>Opens</th><th>Closes</th><th>Listing</th></tr></thead><tbody>${ipos.map(i => `<tr><td>${escapeHTML(i.company)}</td><td>${escapeHTML(i.category)}</td><td>${escapeHTML(i.status)}</td><td>${date(i.openDate)}</td><td>${date(i.closeDate)}</td><td>${date(i.listingDate)}</td></tr>`).join("")}</tbody></table>`;
  $("#subscriptionContent").innerHTML = `<table><thead><tr><th>Company</th><th>Retail</th><th>NII</th><th>QIB</th><th>As of</th></tr></thead><tbody>${ipos.map(i => `<tr><td>${escapeHTML(i.company)}</td><td>${i.subscription?.retail ?? "—"}</td><td>${i.subscription?.nii ?? "—"}</td><td>${i.subscription?.qib ?? "—"}</td><td>${date(i.subscription?.asOf)}</td></tr>`).join("")}</tbody></table>`;
  $("#performanceContent").innerHTML = [["Verified listings","0","No verified results in demo data"],["Mean prediction error","—","Requires actual listing prices"],["Positive listings","—","Requires a completed sample"]].map(([a,b,c]) => `<div class="stat"><span>${a}</span><strong>${b}</strong><small>${c}</small></div>`).join("");
}
function renderStatus() {
  $("#pipelineStatus").textContent = statusData.status || "Unknown";
  $("#pipelineMessage").textContent = statusData.message || "";
  $("#lastAttempt").textContent = statusData.lastAttemptUtc || "—";
  $("#lastSuccess").textContent = statusData.lastSuccessUtc || "—";
  $("#sourceObserved").textContent = statusData.sourceObservedAt || "—";
  $("#nextRun").textContent = statusData.nextScheduledRunUtc || "—";
}
function renderAll() { $("#stats").innerHTML = statsMarkup(); renderCards(); renderTables(); renderStatus(); }

document.querySelectorAll(".filters input, .filters select").forEach(el => el.addEventListener("input", renderCards));
$("#ipoList").addEventListener("click", e => {
  const trigger = e.target.closest("[data-expand]"); if (!trigger) return;
  const id = trigger.dataset.expand; expandedId = expandedId === id ? null : id; renderCards();
});
$("#ipoList").addEventListener("keydown", e => {
  if ((e.key === "Enter" || e.key === " ") && e.target.matches("[data-expand]")) { e.preventDefault(); e.target.click(); }
});
document.querySelectorAll(".tab").forEach(button => button.addEventListener("click", () => {
  document.querySelectorAll(".tab").forEach(b => b.classList.toggle("active", b === button));
  document.querySelectorAll(".view").forEach(v => v.hidden = v.id !== `${button.dataset.view}View`);
}));
$("#refreshButton").addEventListener("click", async () => {
  $("#refreshButton").disabled = true;
  try { await loadData(); } catch (err) { alert(`Could not reload data: ${err.message}`); }
  finally { $("#refreshButton").disabled = false; }
});
loadData().catch(err => { $("#ipoList").innerHTML = `<p class="empty-state">Unable to load dashboard data: ${escapeHTML(err.message)}. Run a local web server and try again.</p>`; });
