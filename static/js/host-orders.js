const ordersList = document.querySelector("#orders-list");
const ordersEmpty = document.querySelector("#orders-empty");
const refreshStatus = document.querySelector("#queue-refresh-status");
const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || "";
const filterButtons = Array.from(document.querySelectorAll("[data-order-filter]"));
const clearButtons = Array.from(document.querySelectorAll("[data-clear-orders]"));
let activeFilter = "active";
let pendingDeleteOrderId = null;
let orders = JSON.parse(document.querySelector("#orders-data")?.textContent || "[]");

const timeFormatter = new Intl.DateTimeFormat(undefined, {
  hour: "2-digit",
  minute: "2-digit",
});

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatSubmittedAt(value) {
  if (!value) return "";
  return timeFormatter.format(new Date(value));
}

function formatElapsed(value) {
  if (!value) return "";
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
  if (seconds < 60) return `${seconds}s waiting`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m waiting`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m waiting`;
}

function recipeLine(ingredient) {
  const amount = ingredient.ml ? `${escapeHtml(ingredient.ml)} ml ` : "";
  const abv = ingredient.abv ? ` <span>${escapeHtml(ingredient.abv)}% ABV</span>` : "";
  return `<li>${amount}${escapeHtml(ingredient.name)}${abv}</li>`;
}

function orderItem(item) {
  const recipe = item.recipe?.length
    ? `<ul class="order-recipe">${item.recipe.map(recipeLine).join("")}</ul>`
    : '<p class="order-no-recipe">No recipe saved for this item.</p>';
  const alcohol = item.alcohol_ml > 0
    ? `<span>${Number(item.alcohol_ml).toFixed(1)} ml alcohol</span>`
    : "";
  const recipientClass = item.recipient_is_unassigned
    ? "order-recipient is-unassigned"
    : "order-recipient";
  const completedClass = item.completed ? " is-completed" : "";
  const checked = item.completed ? "checked" : "";
  return `
    <div class="order-item${completedClass}">
      <label class="order-item-check">
        <input type="checkbox" data-complete-item="${item.id}" ${checked} aria-label="Mark ${escapeHtml(item.name)} for ${escapeHtml(item.recipient_name)} complete">
        <span>Done</span>
      </label>
      <div class="order-item-main">
        <strong>${item.quantity}x ${escapeHtml(item.name)}</strong>
        <small>${escapeHtml(item.category)}</small>
        <em class="${recipientClass}">For ${escapeHtml(item.recipient_name)}</em>
      </div>
      ${alcohol}
      ${recipe}
    </div>
  `;
}

function orderCard(order) {
  const orderId = String(order.id);
  const isPendingDelete = pendingDeleteOrderId === orderId;
  const recipientSummary = order.recipient_summary || order.guest_name;
  const completedItems = order.items.filter((item) => item.completed).length;
  const progressLabel = `${completedItems}/${order.items.length} done`;
  const ordererDetail = recipientSummary
    && recipientSummary.toLocaleLowerCase() !== String(order.guest_name || "").toLocaleLowerCase()
    ? `From ${escapeHtml(order.guest_name)} · `
    : "";
  const completeButton = order.status === "new"
    ? `<button class="button button-dark" type="button" data-complete-order="${order.id}">Mark complete</button>`
    : `<span class="status-chip">Completed ${formatSubmittedAt(order.completed_at)}</span>`;
  const deleteButton = `
    <button class="button button-outline button-danger" type="button" data-delete-order="${order.id}" data-confirm-delete="${isPendingDelete}">
      ${isPendingDelete ? "Confirm delete" : "Delete"}
    </button>
  `;
  const note = order.note
    ? `<p class="order-note">${escapeHtml(order.note)}</p>`
    : "";
  const alcohol = order.total_alcohol_ml > 0
    ? `<span>${Number(order.total_alcohol_ml).toFixed(1)} ml pure alcohol</span>`
    : "<span>No alcohol data</span>";
  return `
    <article class="order-card" data-order-id="${order.id}">
      <div class="order-card-heading">
        <div>
          <h2>${escapeHtml(recipientSummary)}</h2>
          <p>${ordererDetail}${formatSubmittedAt(order.submitted_at)} · ${formatElapsed(order.submitted_at)} · ${order.item_count} item${order.item_count === 1 ? "" : "s"}</p>
        </div>
        <div class="order-card-actions">
          <span class="status-chip">${escapeHtml(order.status)}</span>
          <span class="status-chip status-progress">${escapeHtml(progressLabel)}</span>
          ${completeButton}
          ${deleteButton}
        </div>
      </div>
      ${note}
      <div class="order-card-meta">${alcohol}</div>
      <div class="order-items">${order.items.map(orderItem).join("")}</div>
    </article>
  `;
}

function updateSummary(summary) {
  document.querySelector("#summary-active").textContent = summary.active_orders;
  document.querySelector("#summary-total").textContent = summary.total_orders;
  document.querySelector("#summary-items").textContent = summary.total_items;
  document.querySelector("#summary-drinks").textContent = Number(summary.total_alcohol_ml).toFixed(1);
}

function renderOrders() {
  ordersList.innerHTML = orders.map(orderCard).join("");
  ordersEmpty.hidden = orders.length > 0;
  refreshStatus.textContent = `Live refresh on · ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
}

async function refreshOrders() {
  const response = await fetch(`/host/orders.json?status=${encodeURIComponent(activeFilter)}`, {
    credentials: "same-origin",
  });
  if (!response.ok) throw new Error("Could not refresh orders.");
  const payload = await response.json();
  orders = payload.orders;
  updateSummary(payload.summary);
  renderOrders();
}

async function postQueueAction(url, body = null) {
  const response = await fetch(url, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      "X-CSRF-Token": csrfToken,
    },
    body,
  });
  if (!response.ok) throw new Error("Queue action failed.");
  await refreshOrders();
}

filterButtons.forEach((button) => {
  button.addEventListener("click", async () => {
    activeFilter = button.dataset.orderFilter;
    pendingDeleteOrderId = null;
    filterButtons.forEach((filterButton) => {
      filterButton.classList.toggle("active", filterButton === button);
    });
    try {
      await refreshOrders();
    } catch {
      refreshStatus.textContent = "Live refresh paused";
    }
  });
});

ordersList.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-complete-order], [data-delete-order]");
  if (!button) return;
  const deleteOrderId = button.dataset.deleteOrder;
  if (deleteOrderId && pendingDeleteOrderId !== deleteOrderId) {
    pendingDeleteOrderId = deleteOrderId;
    renderOrders();
    return;
  }
  button.disabled = true;
  try {
    if (button.dataset.completeOrder) {
      await postQueueAction(`/host/orders/${button.dataset.completeOrder}/complete`);
      return;
    }
    await postQueueAction(`/host/orders/${deleteOrderId}/delete`);
    pendingDeleteOrderId = null;
  } catch {
    button.disabled = false;
    refreshStatus.textContent = "Queue action failed";
  }
});

ordersList.addEventListener("change", async (event) => {
  const input = event.target.closest("[data-complete-item]");
  if (!input) return;
  const orderCard = input.closest("[data-order-id]");
  if (!orderCard) return;
  input.disabled = true;
  try {
    await postQueueAction(
      `/host/orders/${orderCard.dataset.orderId}/items/${input.dataset.completeItem}/complete`,
      `completed=${input.checked ? "1" : "0"}`,
    );
  } catch {
    input.checked = !input.checked;
    input.disabled = false;
    refreshStatus.textContent = "Queue action failed";
  }
});

clearButtons.forEach((button) => {
  button.addEventListener("click", async () => {
    const action = button.dataset.clearOrders;
    const message = action === "all"
      ? "Clear the entire order history? This removes active and completed orders."
      : "Clear completed orders from the history?";
    if (!window.confirm(message)) return;
    try {
      await postQueueAction("/host/orders/clear", `action=${encodeURIComponent(action)}`);
    } catch {
      refreshStatus.textContent = "Queue action failed";
    }
  });
});

renderOrders();
window.setInterval(() => {
  refreshOrders().catch(() => {
    refreshStatus.textContent = "Live refresh paused";
  });
}, 3000);
window.setInterval(renderOrders, 30000);
