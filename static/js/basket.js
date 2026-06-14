const basketForm = document.querySelector("#basket-order-form");
const basketItemsElement = document.querySelector("#basket-items");
const basketItemsInput = document.querySelector("#basket-items-input");
const basketEmpty = document.querySelector("#basket-empty");
const basketTotal = document.querySelector("#basket-total");
const basketSubmit = document.querySelector("#basket-submit");
const catalogElement = document.querySelector("#basket-catalog");
const catalog = JSON.parse(catalogElement?.textContent || "[]");
const catalogById = new Map(catalog.map((item) => [String(item.id), item]));

function checkoutState() {
  return Object.fromEntries(
    Object.entries(window.partyBasket.read()).filter(([id]) => catalogById.has(id)),
  );
}

function quantityButton(label, ariaLabel, onClick) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "basket-quantity-button";
  button.textContent = label;
  button.setAttribute("aria-label", ariaLabel);
  button.addEventListener("click", onClick);
  return button;
}

function renderBasket() {
  const items = checkoutState();
  const storedItems = window.partyBasket.read();
  if (JSON.stringify(items) !== JSON.stringify(storedItems)) {
    window.partyBasket.write(items);
  }

  basketItemsElement.replaceChildren();
  let totalQuantity = 0;
  const submittedItems = [];

  Object.entries(items).forEach(([id, quantity]) => {
    const item = catalogById.get(id);
    totalQuantity += quantity;
    submittedItems.push({ id: Number(id), quantity });

    const row = document.createElement("article");
    row.className = "basket-checkout-item";

    const itemCopy = document.createElement("div");
    itemCopy.className = "basket-checkout-copy";
    const name = document.createElement("h3");
    name.textContent = item.name;
    const category = document.createElement("p");
    category.textContent = item.category;
    itemCopy.append(name, category);

    const controls = document.createElement("div");
    controls.className = "basket-item-controls";
    const quantityControls = document.createElement("div");
    quantityControls.className = "basket-quantity-controls";
    quantityControls.append(
      quantityButton("−", `Remove one ${item.name}`, () => {
        window.partyBasket.setQuantity(id, quantity - 1);
        renderBasket();
      }),
    );
    const quantityValue = document.createElement("span");
    quantityValue.textContent = quantity;
    quantityValue.setAttribute("aria-label", `Quantity ${quantity}`);
    quantityControls.append(quantityValue);
    quantityControls.append(
      quantityButton("+", `Add one ${item.name}`, () => {
        window.partyBasket.setQuantity(id, quantity + 1);
        renderBasket();
      }),
    );

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "basket-remove-button";
    remove.textContent = "Remove";
    remove.addEventListener("click", () => {
      window.partyBasket.setQuantity(id, 0);
      renderBasket();
    });
    controls.append(quantityControls, remove);
    row.append(itemCopy, controls);
    basketItemsElement.append(row);
  });

  basketItemsInput.value = JSON.stringify(submittedItems);
  basketEmpty.hidden = totalQuantity > 0;
  basketSubmit.disabled = totalQuantity === 0;
  basketTotal.textContent = totalQuantity
    ? `${totalQuantity} item${totalQuantity === 1 ? "" : "s"}`
    : "";
}

basketForm.addEventListener("submit", (event) => {
  renderBasket();
  if (!basketItemsInput.value || basketItemsInput.value === "[]") {
    event.preventDefault();
  }
});

window.addEventListener("storage", renderBasket);
renderBasket();
