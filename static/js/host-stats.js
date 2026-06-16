let stats = JSON.parse(document.querySelector("#stats-data")?.textContent || "{}");
const highlightStats = document.querySelector("#highlight-stats");
const guestStats = document.querySelector("#guest-stats");
const itemStats = document.querySelector("#item-stats");
const timelineGraph = document.querySelector("#timeline-graph");
const timelineStats = document.querySelector("#timeline-stats");
const timelineRangeButtons = Array.from(document.querySelectorAll("[data-timeline-range]"));
const guestAlcoholGraph = document.querySelector("#guest-alcohol-graph");
const categoryStats = document.querySelector("#category-stats");
const funStats = document.querySelector("#fun-stats");
let activeTimelineRange = timelineRangeButtons.find((button) => button.classList.contains("active"))
  ?.dataset.timelineRange || "4";

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

function alcoholMl(value, places = 1) {
  return `${decimal(value, places)} ml`;
}

function hourLabel(value) {
  if (!value) return "Now";
  return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function paceForGuest(guest) {
  return `${decimal(Number(guest.recent_items_4h || 0) / 4, 2)}/hr`;
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

function emptyState(message) {
  return `<p class="dashboard-empty">${escapeHtml(message)}</p>`;
}

function updateSummary(summary = {}) {
  document.querySelector("#stats-total-orders").textContent = count(summary.total_orders);
  document.querySelector("#stats-total-items").textContent = count(summary.total_items);
  document.querySelector("#stats-active-orders").textContent = count(summary.active_orders);
  document.querySelector("#stats-alcohol-ml").textContent = decimal(summary.total_alcohol_ml, 1);
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
        ? `${count(topGuest.items)} item${topGuest.items === 1 ? "" : "s"} · ${alcoholMl(topGuest.alcohol_ml)} alcohol`
        : "Waiting for the first order",
    },
    {
      label: "House favorite",
      value: topItem ? topItem.name : "No favorite yet",
      detail: topItem
        ? `${count(topItem.quantity)} ordered · ${alcoholMl(topItem.alcohol_ml)} alcohol`
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
        <td>
          <strong>${escapeHtml(guest.guest_name)}</strong>
          <small>${count(guest.recent_items_4h)} drink${guest.recent_items_4h === 1 ? "" : "s"} in last 4h</small>
        </td>
        <td>${count(guest.orders)}</td>
        <td>${count(guest.items)}</td>
        <td>${alcoholMl(guest.alcohol_ml)}</td>
        <td>${count(guest.self_items)}</td>
        <td>${count(guest.by_others_items)}</td>
        <td>${paceForGuest(guest)}</td>
      </tr>
    `).join("")
    : '<tr><td colspan="7" class="empty-table">No orders yet.</td></tr>';
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
            <small>${escapeHtml(item.category)} · ${alcoholMl(item.alcohol_ml)} pure alcohol</small>
            <i class="mini-bar ${itemWidthClass}"></i>
          </div>
          <b>${count(item.quantity)}</b>
        </div>
      `;
    }).join("")
    : emptyState("No item stats yet.");
}

function timelineInActiveRange(timeline) {
  if (activeTimelineRange === "all" || !timeline.length) return timeline;
  const rangeHours = Number(activeTimelineRange);
  const timestamps = timeline
    .map((row) => new Date(row.hour).getTime())
    .filter((value) => Number.isFinite(value));
  if (!timestamps.length) return timeline;
  const latest = Math.max(...timestamps);
  const cutoff = latest - (rangeHours * 3600000);
  return timeline.filter((row) => new Date(row.hour).getTime() >= cutoff);
}

function renderTimelineGraph(timeline) {
  const visibleTimeline = timelineInActiveRange(timeline);
  if (!visibleTimeline.length) {
    timelineGraph.innerHTML = emptyState("No activity in this range.");
    return;
  }

  const width = 720;
  const height = 245;
  const padding = { top: 22, right: 26, bottom: 42, left: 44 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const maxValue = Math.max(
    1,
    ...visibleTimeline.flatMap((row) => [Number(row.items || 0), Number(row.orders || 0)]),
  );
  const xFor = (index) => {
    if (visibleTimeline.length === 1) return padding.left + plotWidth / 2;
    return padding.left + (index / (visibleTimeline.length - 1)) * plotWidth;
  };
  const yFor = (value) => padding.top + plotHeight - (Number(value || 0) / maxValue) * plotHeight;
  const pointString = (key) => visibleTimeline
    .map((row, index) => `${xFor(index)},${yFor(row[key])}`)
    .join(" ");
  const labelEvery = Math.max(1, Math.ceil(visibleTimeline.length / 5));
  const axisLabels = visibleTimeline
    .map((row, index) => ({ row, index }))
    .filter(({ index }) => index === 0 || index === visibleTimeline.length - 1 || index % labelEvery === 0)
    .map(({ row, index }) => `
      <text x="${xFor(index)}" y="${height - 15}" text-anchor="middle">${escapeHtml(hourLabel(row.hour))}</text>
    `).join("");
  const grid = [0, maxValue / 2, maxValue].map((value) => {
    const y = yFor(value);
    return `
      <line class="rush-line-grid" x1="${padding.left}" x2="${width - padding.right}" y1="${y}" y2="${y}"></line>
      <text x="${padding.left - 10}" y="${y + 4}" text-anchor="end">${decimal(value, value < 10 ? 1 : 0)}</text>
    `;
  }).join("");
  const itemPoints = visibleTimeline.map((row, index) => `
    <circle class="rush-line-point rush-line-items" cx="${xFor(index)}" cy="${yFor(row.items)}" r="4">
      <title>${count(row.items)} item${row.items === 1 ? "" : "s"} at ${escapeHtml(hourLabel(row.hour))}</title>
    </circle>
  `).join("");
  const orderPoints = visibleTimeline.map((row, index) => `
    <circle class="rush-line-point rush-line-orders" cx="${xFor(index)}" cy="${yFor(row.orders)}" r="4">
      <title>${count(row.orders)} order${row.orders === 1 ? "" : "s"} at ${escapeHtml(hourLabel(row.hour))}</title>
    </circle>
  `).join("");

  timelineGraph.innerHTML = `
    <div class="graph-legend">
      <span><i class="graph-key graph-key-items"></i>Items</span>
      <span><i class="graph-key graph-key-orders"></i>Orders</span>
    </div>
    <div class="rush-line-wrap">
      <svg class="rush-line-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Orders and items over time">
        <rect class="guest-line-bg" x="${padding.left}" y="${padding.top}" width="${plotWidth}" height="${plotHeight}"></rect>
        ${grid}
        <polyline class="rush-line rush-line-items" points="${pointString("items")}"></polyline>
        <polyline class="rush-line rush-line-orders" points="${pointString("orders")}"></polyline>
        ${itemPoints}
        ${orderPoints}
        ${axisLabels}
      </svg>
    </div>
  `;
}

function renderTimeline(timeline) {
  const visibleTimeline = timelineInActiveRange(timeline);
  timelineStats.innerHTML = visibleTimeline.length
    ? visibleTimeline.map((row) => `
      <div class="timeline-row timeline-text-row">
        <span>${hourLabel(row.hour)}</span>
        <b>${count(row.orders)} order${row.orders === 1 ? "" : "s"}</b>
        <em>${count(row.items)} item${row.items === 1 ? "" : "s"}</em>
      </div>
    `).join("")
    : "";
}

function renderGuestAlcoholGraph(timeline = {}) {
  const labels = timeline.labels || [];
  const series = (timeline.series || [])
    .filter((guest) => Number(guest.alcohol_ml || 0) > 0 && guest.points?.length);
  if (!labels.length || !series.length) {
    guestAlcoholGraph.innerHTML = emptyState("No guest alcohol timeline yet.");
    return;
  }

  const width = 720;
  const height = 270;
  const padding = { top: 24, right: 26, bottom: 44, left: 54 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const maxAlcoholMl = Math.max(
    1,
    ...series.flatMap((guest) => guest.points.map((point) => Number(point.alcohol_ml || 0))),
  );
  const xFor = (index) => {
    if (labels.length === 1) return padding.left + plotWidth / 2;
    return padding.left + (index / (labels.length - 1)) * plotWidth;
  };
  const yFor = (value) => padding.top + plotHeight - (Number(value || 0) / maxAlcoholMl) * plotHeight;
  const gridValues = [0, maxAlcoholMl / 2, maxAlcoholMl];
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
      <text x="${padding.left - 10}" y="${y + 4}" text-anchor="end">${decimal(value, 0)}</text>
    `;
  }).join("");
  const lines = series.map((guest, guestIndex) => {
    const colorIndex = guestIndex % 8;
    const points = guest.points
      .map((point, index) => `${xFor(index)},${yFor(point.alcohol_ml)}`)
      .join(" ");
    const lineAttributes = `
      data-guest-name="${escapeHtml(guest.guest_name)}"
      data-guest-value="${escapeHtml(guest.alcohol_ml)}"
      data-guest-index="${guestIndex}"
    `;
    return `
      <polyline class="guest-line guest-line-${colorIndex}" ${lineAttributes} points="${points}"></polyline>
      ${guest.points.map((point, index) => `
        <circle class="guest-line-point guest-line-${colorIndex}" ${lineAttributes}
          data-guest-hour="${escapeHtml(hourLabel(point.hour))}"
          data-guest-value="${escapeHtml(point.alcohol_ml)}"
          cx="${xFor(index)}" cy="${yFor(point.alcohol_ml)}" r="4">
          <title>${escapeHtml(guest.guest_name)}: ${alcoholMl(point.alcohol_ml)} at ${escapeHtml(hourLabel(point.hour))}</title>
        </circle>
      `).join("")}
    `;
  }).join("");
  const legend = series.map((guest, guestIndex) => `
    <button class="guest-line-legend-item guest-line-${guestIndex % 8}" type="button"
      data-guest-name="${escapeHtml(guest.guest_name)}"
      data-guest-value="${escapeHtml(guest.alcohol_ml)}"
      data-guest-index="${guestIndex}">
      <i class="guest-line-key guest-line-${guestIndex % 8}"></i>
      ${escapeHtml(guest.guest_name)}
      <b>${alcoholMl(guest.alcohol_ml)}</b>
    </button>
  `).join("");

  guestAlcoholGraph.innerHTML = `
    <div class="guest-line-wrap">
      <svg class="guest-line-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Cumulative pure alcohol ml by guest over time">
        <rect class="guest-line-bg" x="${padding.left}" y="${padding.top}" width="${plotWidth}" height="${plotHeight}"></rect>
        ${grid}
        ${lines}
        ${axisLabels}
      </svg>
    </div>
    <div class="guest-line-detail" data-guest-line-detail>Hover or click a line to inspect a guest.</div>
    <div class="guest-line-legend">${legend}</div>
  `;
}

function renderCategories(categories) {
  const totalQuantity = categories.reduce((total, category) => total + Number(category.quantity || 0), 0);
  if (!categories.length || totalQuantity <= 0) {
    categoryStats.innerHTML = emptyState("No category mix yet.");
    return;
  }

  let offset = 25;
  const slices = categories.map((category, index) => {
    const share = (Number(category.quantity || 0) / totalQuantity) * 100;
    const slice = `
      <circle class="category-pie-slice category-color-${index % 8}" cx="21" cy="21" r="15.9155"
        stroke-dasharray="${share} ${100 - share}" stroke-dashoffset="${offset}">
        <title>${escapeHtml(category.category)}: ${decimal(share, 1)}%</title>
      </circle>
    `;
    offset -= share;
    return slice;
  }).join("");
  const legend = categories.map((category, index) => {
    const share = (Number(category.quantity || 0) / totalQuantity) * 100;
    return `
      <div class="category-pie-row">
        <i class="category-color-${index % 8}"></i>
        <div>
          <strong>${escapeHtml(category.category)}</strong>
          <small>${count(category.quantity)} item${category.quantity === 1 ? "" : "s"} · ${decimal(share, 1)}% · ${alcoholMl(category.alcohol_ml)} alcohol</small>
        </div>
      </div>
    `;
  }).join("");

  categoryStats.innerHTML = `
    <div class="category-pie-wrap">
      <svg class="category-pie" viewBox="0 0 42 42" role="img" aria-label="Category mix by quantity">
        <circle class="category-pie-bg" cx="21" cy="21" r="15.9155"></circle>
        <g transform="rotate(-90 21 21)">${slices}</g>
      </svg>
      <div class="category-pie-total">
        <strong>${count(totalQuantity)}</strong>
        <span>items</span>
      </div>
    </div>
    <div class="category-pie-legend">${legend}</div>
  `;
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
      label: "Alcohol total",
      value: alcoholMl(summary.total_alcohol_ml),
      detail: "pure alcohol ordered tonight",
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

function showGuestLineDetail(target) {
  const detail = guestAlcoholGraph.querySelector("[data-guest-line-detail]");
  if (!detail || !target?.dataset?.guestName) return;
  const name = target.dataset.guestName;
  const value = target.dataset.guestValue;
  const hour = target.dataset.guestHour;
  detail.textContent = hour
    ? `${name} · ${alcoholMl(value)} by ${hour}`
    : `${name} · ${alcoholMl(value)} total`;
  const guestIndex = target.dataset.guestIndex;
  guestAlcoholGraph.classList.add("has-active");
  guestAlcoholGraph.querySelectorAll("[data-guest-index]").forEach((node) => {
    node.classList.toggle("is-active", node.dataset.guestIndex === guestIndex);
  });
}

function clearGuestLineDetail() {
  guestAlcoholGraph.classList.remove("has-active");
  guestAlcoholGraph.querySelectorAll(".is-active").forEach((node) => node.classList.remove("is-active"));
  const detail = guestAlcoholGraph.querySelector("[data-guest-line-detail]");
  if (detail) detail.textContent = "Hover or click a line to inspect a guest.";
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

timelineRangeButtons.forEach((button) => {
  button.addEventListener("click", () => {
    activeTimelineRange = button.dataset.timelineRange;
    timelineRangeButtons.forEach((rangeButton) => {
      rangeButton.classList.toggle("active", rangeButton === button);
    });
    renderTimelineGraph(stats.timeline || []);
    renderTimeline(stats.timeline || []);
  });
});

guestAlcoholGraph.addEventListener("mouseover", (event) => {
  const target = event.target.closest("[data-guest-name]");
  if (target) showGuestLineDetail(target);
});

guestAlcoholGraph.addEventListener("click", (event) => {
  const target = event.target.closest("[data-guest-name]");
  if (target) showGuestLineDetail(target);
});

guestAlcoholGraph.addEventListener("mouseleave", clearGuestLineDetail);

renderStats();
window.setInterval(() => {
  refreshStats().catch(() => {});
}, 10000);
window.setInterval(renderStats, 30000);
