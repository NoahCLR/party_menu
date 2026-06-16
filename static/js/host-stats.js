let stats = JSON.parse(document.querySelector("#stats-data")?.textContent || "{}");
const highlightStats = document.querySelector("#highlight-stats");
const guestStats = document.querySelector("#guest-stats");
const itemStats = document.querySelector("#item-stats");
const timelineGraph = document.querySelector("#timeline-graph");
const timelineStats = document.querySelector("#timeline-stats");
const guestAlcoholGraph = document.querySelector("#guest-alcohol-graph");
const categoryStats = document.querySelector("#category-stats");
const funStats = document.querySelector("#fun-stats");

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function count(value) {
  return Number(value || 0).toLocaleString();
}

function decimal(value, places = 1) {
  return Number(value || 0).toFixed(places);
}

function drinks(value) {
  return decimal(value, 2);
}

function hourLabel(value) {
  if (!value) return "Now";
  return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function paceForGuest(guest) {
  if (!guest.first_order_at || Number(guest.standard_drinks) <= 0) return "No estimate";
  const elapsedHours = Math.max(
    0.25,
    (Date.now() - new Date(guest.first_order_at).getTime()) / 3600000,
  );
  return `${decimal(Number(guest.standard_drinks) / elapsedHours, 2)}/hr`;
}

function percentage(value, max, minimum = 4) {
  if (!max) return minimum;
  return Math.max(minimum, Math.round((Number(value || 0) / max) * 100));
}

function bucket(value, max, minimum = 10) {
  const raw = percentage(value, max, minimum);
  return Math.min(100, Math.max(minimum, Math.ceil(raw / 10) * 10));
}

function widthClass(value, max) {
  return `bar-w-${bucket(value, max)}`;
}

function heightClass(value, max) {
  return `graph-h-${bucket(value, max)}`;
}

function emptyState(message) {
  return `<p class="dashboard-empty">${escapeHtml(message)}</p>`;
}

function updateSummary(summary = {}) {
  document.querySelector("#stats-total-orders").textContent = count(summary.total_orders);
  document.querySelector("#stats-total-items").textContent = count(summary.total_items);
  document.querySelector("#stats-active-orders").textContent = count(summary.active_orders);
  document.querySelector("#stats-standard-drinks").textContent = drinks(summary.standard_drinks);
}

function renderHighlights(highlights = {}) {
  const topGuest = highlights.top_guest;
  const topItem = highlights.top_item;
  const topCategory = highlights.top_category;
  const peakHour = highlights.peak_hour;
  const cards = [
    {
      label: "Top guest",
      value: topGuest ? topGuest.guest_name : "No orders",
      detail: topGuest
        ? `${count(topGuest.items)} item${topGuest.items === 1 ? "" : "s"} ordered`
        : "Waiting for the first order",
    },
    {
      label: "House favorite",
      value: topItem ? topItem.name : "No favorite yet",
      detail: topItem
        ? `${count(topItem.quantity)} ordered from ${topItem.category}`
        : "Popularity appears once guests order",
    },
    {
      label: "Menu lane",
      value: topCategory ? topCategory.category : "No category yet",
      detail: topCategory
        ? `${count(topCategory.quantity)} item${topCategory.quantity === 1 ? "" : "s"} in this category`
        : "Category mix will fill in live",
    },
    {
      label: "Peak rush",
      value: peakHour ? hourLabel(peakHour.hour) : "No rush yet",
      detail: peakHour
        ? `${count(peakHour.items)} item${peakHour.items === 1 ? "" : "s"} across ${count(peakHour.orders)} order${peakHour.orders === 1 ? "" : "s"}`
        : "Hourly graph is ready",
    },
  ];

  highlightStats.innerHTML = cards.map((card) => `
    <article class="highlight-card">
      <small>${escapeHtml(card.label)}</small>
      <strong>${escapeHtml(card.value)}</strong>
      <span>${escapeHtml(card.detail)}</span>
    </article>
  `).join("");
}

function renderGuests(guests) {
  guestStats.innerHTML = guests.length
    ? guests.map((guest) => `
      <tr>
        <td><strong>${escapeHtml(guest.guest_name)}</strong></td>
        <td>${count(guest.orders)}</td>
        <td>${count(guest.items)}</td>
        <td>${drinks(guest.standard_drinks)}</td>
        <td>${paceForGuest(guest)}</td>
      </tr>
    `).join("")
    : '<tr><td colspan="5" class="empty-table">No orders yet.</td></tr>';
}

function renderItems(items) {
  const maxQuantity = Math.max(1, ...items.map((item) => Number(item.quantity || 0)));
  itemStats.innerHTML = items.length
    ? items.map((item, index) => {
      const itemWidthClass = widthClass(item.quantity, maxQuantity);
      return `
        <div class="ranked-row">
          <span>${String(index + 1).padStart(2, "0")}</span>
          <div>
            <strong>${escapeHtml(item.name)}</strong>
            <small>${escapeHtml(item.category)} · ${drinks(item.standard_drinks)} est. drinks</small>
            <i class="mini-bar ${itemWidthClass}"></i>
          </div>
          <b>${count(item.quantity)}</b>
        </div>
      `;
    }).join("")
    : emptyState("No item stats yet.");
}

function renderTimelineGraph(timeline) {
  if (!timeline.length) {
    timelineGraph.innerHTML = emptyState("No hourly activity yet.");
    return;
  }

  const maxItems = Math.max(1, ...timeline.map((row) => Number(row.items || 0)));
  const maxOrders = Math.max(1, ...timeline.map((row) => Number(row.orders || 0)));
  const columns = timeline.map((row) => {
    const itemHeightClass = heightClass(row.items, maxItems);
    const orderHeightClass = heightClass(row.orders, maxOrders);
    return `
      <div class="graph-column">
        <div class="graph-bars" aria-label="${count(row.items)} items and ${count(row.orders)} orders">
          <i class="graph-bar graph-bar-items ${itemHeightClass}"></i>
          <i class="graph-bar graph-bar-orders ${orderHeightClass}"></i>
        </div>
        <strong>${hourLabel(row.hour)}</strong>
        <small>${count(row.items)} item${row.items === 1 ? "" : "s"}</small>
      </div>
    `;
  }).join("");

  timelineGraph.innerHTML = `
    <div class="graph-legend">
      <span><i class="graph-key graph-key-items"></i>Items</span>
      <span><i class="graph-key graph-key-orders"></i>Orders</span>
    </div>
    <div class="graph-columns">${columns}</div>
  `;
}

function renderTimeline(timeline) {
  const maxItems = Math.max(1, ...timeline.map((row) => Number(row.items || 0)));
  timelineStats.innerHTML = timeline.length
    ? timeline.map((row) => {
      const timelineWidthClass = widthClass(row.items, maxItems);
      return `
        <div class="timeline-row">
          <span>${hourLabel(row.hour)}</span>
          <div><i class="${timelineWidthClass}"></i></div>
          <b>${count(row.orders)} order${row.orders === 1 ? "" : "s"}</b>
        </div>
      `;
    }).join("")
    : "";
}

function renderGuestAlcoholGraph(timeline = {}) {
  const labels = timeline.labels || [];
  const series = (timeline.series || [])
    .filter((guest) => Number(guest.standard_drinks || 0) > 0 && guest.points?.length);
  if (!labels.length || !series.length) {
    guestAlcoholGraph.innerHTML = emptyState("No guest alcohol timeline yet.");
    return;
  }

  const width = 720;
  const height = 270;
  const padding = { top: 24, right: 26, bottom: 44, left: 48 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const maxDrinks = Math.max(
    1,
    ...series.flatMap((guest) => guest.points.map((point) => Number(point.standard_drinks || 0))),
  );
  const xFor = (index) => {
    if (labels.length === 1) return padding.left + plotWidth / 2;
    return padding.left + (index / (labels.length - 1)) * plotWidth;
  };
  const yFor = (value) => padding.top + plotHeight - (Number(value || 0) / maxDrinks) * plotHeight;
  const gridValues = [0, maxDrinks / 2, maxDrinks];
  const labelEvery = Math.max(1, Math.ceil(labels.length / 5));
  const axisLabels = labels
    .map((label, index) => ({ label, index }))
    .filter(({ index }) => index === 0 || index === labels.length - 1 || index % labelEvery === 0)
    .map(({ label, index }) => `
      <text x="${xFor(index)}" y="${height - 16}" text-anchor="middle">${escapeHtml(hourLabel(label))}</text>
    `).join("");
  const grid = gridValues.map((value) => {
    const y = yFor(value);
    return `
      <line class="guest-line-grid" x1="${padding.left}" x2="${width - padding.right}" y1="${y}" y2="${y}"></line>
      <text x="${padding.left - 10}" y="${y + 4}" text-anchor="end">${drinks(value)}</text>
    `;
  }).join("");
  const lines = series.map((guest, guestIndex) => {
    const points = guest.points
      .map((point, index) => `${xFor(index)},${yFor(point.standard_drinks)}`)
      .join(" ");
    return `
      <polyline class="guest-line guest-line-${guestIndex % 6}" points="${points}"></polyline>
      ${guest.points.map((point, index) => `
        <circle class="guest-line-point guest-line-${guestIndex % 6}" cx="${xFor(index)}" cy="${yFor(point.standard_drinks)}" r="4">
          <title>${escapeHtml(guest.guest_name)}: ${drinks(point.standard_drinks)} est. drinks at ${escapeHtml(hourLabel(point.hour))}</title>
        </circle>
      `).join("")}
    `;
  }).join("");
  const legend = series.map((guest, guestIndex) => `
    <span>
      <i class="guest-line-key guest-line-${guestIndex % 6}"></i>
      ${escapeHtml(guest.guest_name)}
      <b>${drinks(guest.standard_drinks)}</b>
    </span>
  `).join("");

  guestAlcoholGraph.innerHTML = `
    <div class="guest-line-wrap">
      <svg class="guest-line-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Cumulative estimated drinks by guest over time">
        <rect class="guest-line-bg" x="${padding.left}" y="${padding.top}" width="${plotWidth}" height="${plotHeight}"></rect>
        ${grid}
        ${lines}
        ${axisLabels}
      </svg>
    </div>
    <div class="guest-line-legend">${legend}</div>
  `;
}

function renderCategories(categories) {
  const maxQuantity = Math.max(1, ...categories.map((category) => Number(category.quantity || 0)));
  categoryStats.innerHTML = categories.length
    ? categories.map((category) => {
      const categoryWidthClass = widthClass(category.quantity, maxQuantity);
      return `
        <div class="category-row">
          <div>
            <strong>${escapeHtml(category.category)}</strong>
            <small>${count(category.quantity)} item${category.quantity === 1 ? "" : "s"} · ${drinks(category.standard_drinks)} est. drinks</small>
          </div>
          <span><i class="${categoryWidthClass}"></i></span>
        </div>
      `;
    }).join("")
    : emptyState("No category mix yet.");
}

function renderFun(highlights = {}, summary = {}) {
  const biggestOrder = highlights.biggest_order;
  const totalOrders = Number(summary.total_orders || 0);
  const completedOrders = Number(summary.completed_orders || 0);
  const cards = [
    {
      label: "Guest count",
      value: count(highlights.unique_guests),
      detail: "named guests in history",
    },
    {
      label: "Average round",
      value: decimal(highlights.avg_items_per_order, 1),
      detail: "items per order",
    },
    {
      label: "Completion",
      value: `${decimal(highlights.completion_rate, 1)}%`,
      detail: `${count(completedOrders)} of ${count(totalOrders)} orders done`,
    },
    {
      label: "Biggest round",
      value: biggestOrder ? biggestOrder.guest_name : "No round yet",
      detail: biggestOrder
        ? `${count(biggestOrder.item_count)} item${biggestOrder.item_count === 1 ? "" : "s"} at ${hourLabel(biggestOrder.submitted_at)}`
        : "Shows the largest submitted order",
    },
  ];

  funStats.innerHTML = cards.map((card) => `
    <div class="fun-card">
      <small>${escapeHtml(card.label)}</small>
      <strong>${escapeHtml(card.value)}</strong>
      <span>${escapeHtml(card.detail)}</span>
    </div>
  `).join("");
}

function renderStats() {
  const summary = stats.summary || {};
  const highlights = stats.highlights || {};
  updateSummary(summary);
  renderHighlights(highlights);
  renderTimelineGraph(stats.timeline || []);
  renderGuests(stats.guests || []);
  renderGuestAlcoholGraph(stats.guest_alcohol_timeline || {});
  renderItems(stats.items || []);
  renderTimeline(stats.timeline || []);
  renderCategories(stats.categories || []);
  renderFun(highlights, summary);
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
