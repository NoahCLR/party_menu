const basketForm = document.querySelector("#basket-order-form");
const basketItemsElement = document.querySelector("#basket-items");
const basketItemsInput = document.querySelector("#basket-items-input");
const basketEmpty = document.querySelector("#basket-empty");
const basketTotal = document.querySelector("#basket-total");
const basketSubmit = document.querySelector("#basket-submit");
const guestNameInput = document.querySelector("#guest_name");
const noteInput = document.querySelector("#note");
const catalogElement = document.querySelector("#basket-catalog");
const catalog = JSON.parse(catalogElement?.textContent || "[]");
const catalogById = new Map(catalog.map((item) => [String(item.id), item]));
const recipientDrafts = new Map();
let lastGuestName = "";

function checkoutState() {
  return Object.fromEntries(
    Object.entries(window.partyBasket.read()).filter(([id]) => catalogById.has(id)),
  );
}

function assignmentKey(id, index) {
  return `${id}:${index}`;
}

function trimmedName(value) {
  return String(value || "").trim();
}

function currentGuestName() {
  return trimmedName(guestNameInput.value);
}

function captureRecipientInputs() {
  basketItemsElement.querySelectorAll(".basket-recipient-input").forEach((input) => {
    recipientDrafts.set(input.dataset.assignmentKey, input.value);
  });
}

function focusNextRecipient(input) {
  const inputs = Array.from(basketItemsElement.querySelectorAll(".basket-recipient-input"));
  const nextInput = inputs[inputs.indexOf(input) + 1];
  const target = nextInput || noteInput || basketSubmit;
  target?.focus();
  target?.select?.();
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

function recipientInput(id, index, itemName) {
  const key = assignmentKey(id, index);
  const label = document.createElement("label");
  label.className = "basket-recipient";
  label.setAttribute("for", `recipient-${id}-${index}`);

  const labelText = document.createElement("span");
  labelText.textContent = `#${index + 1}`;

  const input = document.createElement("input");
  const draft = recipientDrafts.get(key);
  const isDefaultRecipient = !recipientDrafts.has(key)
    || trimmedName(draft) === ""
    || trimmedName(draft) === lastGuestName;
  input.id = `recipient-${id}-${index}`;
  input.type = "text";
  input.maxLength = 80;
  input.autocomplete = "name";
  input.placeholder = currentGuestName() || "Name";
  input.value = isDefaultRecipient ? currentGuestName() : draft;
  input.dataset.assignmentKey = key;
  input.dataset.defaultRecipient = isDefaultRecipient ? "true" : "false";
  input.dataset.nameAutocomplete = "";
  input.className = "basket-recipient-input";
  input.addEventListener("input", () => {
    input.dataset.defaultRecipient =
      trimmedName(input.value) === "" || trimmedName(input.value) === currentGuestName()
        ? "true"
        : "false";
    recipientDrafts.set(key, input.value);
  });
  input.addEventListener("focus", () => {
    input.select();
  });
  input.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    focusNextRecipient(input);
  });

  label.append(labelText, input);
  return label;
}

function renderBasket() {
  captureRecipientInputs();
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
    const recipients = [];

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

    const recipientsWrap = document.createElement("div");
    recipientsWrap.className = "basket-recipients";
    const recipientHeading = document.createElement("div");
    recipientHeading.className = "basket-recipient-heading";
    const recipientTitle = document.createElement("span");
    recipientTitle.textContent = quantity === 1 ? `For ${item.name}` : `For each ${item.name}`;
    recipientHeading.append(recipientTitle);
    recipientsWrap.append(recipientHeading);
    for (let index = 0; index < quantity; index += 1) {
      const key = assignmentKey(id, index);
      recipientsWrap.append(recipientInput(id, index, item.name));
      recipients.push(trimmedName(recipientDrafts.get(key)) || currentGuestName());
    }
    row.append(recipientsWrap);
    basketItemsElement.append(row);
    submittedItems.push({ id: Number(id), quantity, recipients });
  });

  basketItemsInput.value = JSON.stringify(submittedItems);
  basketEmpty.hidden = totalQuantity > 0;
  basketSubmit.disabled = totalQuantity === 0;
  basketTotal.textContent = totalQuantity
    ? `${totalQuantity} item${totalQuantity === 1 ? "" : "s"}`
    : "";
  window.partyNameSuggestions?.enhance(basketItemsElement);
}

basketForm.addEventListener("submit", (event) => {
  renderBasket();
  if (!basketItemsInput.value || basketItemsInput.value === "[]") {
    event.preventDefault();
  }
});

guestNameInput.addEventListener("input", () => {
  const nextGuestName = currentGuestName();
  basketItemsElement.querySelectorAll(".basket-recipient-input").forEach((input) => {
    input.placeholder = nextGuestName || "Name";
    if (input.dataset.defaultRecipient === "true") {
      input.value = nextGuestName;
      recipientDrafts.set(input.dataset.assignmentKey, nextGuestName);
      input.dispatchEvent(new Event("input", { bubbles: true }));
    }
  });
  lastGuestName = nextGuestName;
});

basketItemsElement.addEventListener("party-name-selected", (event) => {
  const input = event.target.closest(".basket-recipient-input");
  if (input) focusNextRecipient(input);
});

window.addEventListener("storage", renderBasket);
lastGuestName = currentGuestName();
renderBasket();
