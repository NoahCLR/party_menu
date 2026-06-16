let stats = JSON.parse(document.querySelector("#stats-data")?.textContent || "{}");
const guestStats = document.querySelector("#guest-stats");
const itemStats = document.querySelector("#item-stats");
const timelineStats = document.querySelector("#timeline-stats");

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function drinks(value) {
  return Number(value || 0).toFixed(2);
}

function paceForGuest(guest) {
  if (!guest.first_order_at || Number(guest.standard_drinks) <= 0) return "No estimate";
  const elapsedHours = Math.max(
    0.25,
    (Date.now() - new Date(guest.first_order_at).getTime()) / 3600000,
  );
  return `${(Number(guest.standard_drinks) / elapsedHours).toFixed(2)}/hr`;
}

function updateSummary(summary) {
  document.querySelector("#stats-total-orders").textContent = summary.total_orders;
  document.querySelector("#stats-total-items").textContent = summary.total_items;
  document.querySelector("#stats-active-orders").textContent = summary.active_orders;
  document.querySelector("#stats-standard-drinks").textContent = drinks(summary.standard_drinks);
}

function renderGuests(guests) {
  guestStats.innerHTML = guests.length
    ? guests.map((guest) => `
      <tr>
        <td><strong>${escapeHtml(guest.guest_name)}</strong></td>
        <td>${guest.orders}</td>
        <td>${guest.items}</td>
        <td>${drinks(guest.standard_drinks)}</td>
        <td>${paceForGuest(guest)}</td>
      </tr>
    `).join("")
    : '<tr><td colspan="5" class="empty-table">No orders yet.</td></tr>';
}

function renderItems(items) {
  itemStats.innerHTML = items.length
    ? items.map((item, index) => `
      <div class="ranked-row">
        <span>${String(index + 1).padStart(2, "0")}</span>
        <div><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.category)}</small></div>
        <b>${item.quantity}</b>
      </div>
    `).join("")
    : '<p class="dashboard-empty">No item stats yet.</p>';
}

function renderTimeline(timeline) {
  const maxItems = Math.max(1, ...timeline.map((row) => Number(row.items || 0)));
  timelineStats.innerHTML = timeline.length
    ? timeline.map((row) => {
      const width = Math.max(4, Math.round((Number(row.items || 0) / maxItems) * 100));
      const hour = row.hour ? new Date(row.hour).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
      return `
        <div class="timeline-row">
          <span>${hour}</span>
          <div><i style="width: ${width}%"></i></div>
          <b>${row.items} item${row.items === 1 ? "" : "s"}</b>
        </div>
      `;
    }).join("")
    : '<p class="dashboard-empty">No timeline yet.</p>';
}

function renderStats() {
  updateSummary(stats.summary || {});
  renderGuests(stats.guests || []);
  renderItems(stats.items || []);
  renderTimeline(stats.timeline || []);
}

async function refreshStats() {
  const response = await fetch("/host/stats.json", { credentials: "same-origin" });
  if (!response.ok) throw new Error("Could not refresh stats.");
  const payload = await response.json();
  stats = payload.stats;
  renderStats();
}

renderStats();
window.setInterval(() => {
  refreshStats().catch(() => {});
}, 10000);
window.setInterval(renderStats, 30000);
