const basketForm = document.querySelector("#basket-order-form");
const basketItemsElement = document.querySelector("#basket-items");
const basketItemsInput = document.querySelector("#basket-items-input");
const basketEmpty = document.querySelector("#basket-empty");
const basketTotal = document.querySelector("#basket-total");
const basketSubmit = document.querySelector("#basket-submit");
const basketNameRequired = document.querySelector("#basket-name-required");
const guestNameInput = document.querySelector("#guest_name");
const noteInput = document.querySelector("#note");
const catalogElement = document.querySelector("#basket-catalog");
const catalog = JSON.parse(catalogElement?.textContent || "[]");
const catalogById = new Map(catalog.map((item) => [String(item.id), item]));
const recipientDrafts = new Map();

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
    if (input.dataset.defaultRecipient === "true") {
      recipientDrafts.delete(input.dataset.assignmentKey);
    } else {
      recipientDrafts.set(input.dataset.assignmentKey, input.value);
    }
  });
}

function recipientInputFor(key) {
  return Array.from(basketItemsElement.querySelectorAll(".basket-recipient-input"))
    .find((input) => input.dataset.assignmentKey === key);
}

function updateBasketSubmissionState() {
  const items = checkoutState();
  const submittedItems = [];
  let totalQuantity = 0;
  let allRecipientsAssigned = true;

  Object.entries(items).forEach(([id, quantity]) => {
    totalQuantity += quantity;
    const recipients = [];
    for (let index = 0; index < quantity; index += 1) {
      const recipientName = trimmedName(recipientInputFor(assignmentKey(id, index))?.value);
      recipients.push(recipientName);
      if (!recipientName) allRecipientsAssigned = false;
    }
    submittedItems.push({ id: Number(id), quantity, recipients });
  });

  basketItemsInput.value = JSON.stringify(submittedItems);
  basketSubmit.disabled = totalQuantity === 0 || !allRecipientsAssigned;
  basketNameRequired.hidden = totalQuantity === 0 || allRecipientsAssigned;
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

function recipientInput(id, index, itemName, shouldPrefill) {
  const key = assignmentKey(id, index);
  const label = document.createElement("label");
  label.className = "basket-recipient";
  label.setAttribute("for", `recipient-${id}-${index}`);

  const labelText = document.createElement("span");
  labelText.textContent = `#${index + 1}`;

  const input = document.createElement("input");
  const hasDraft = recipientDrafts.has(key);
  const draft = hasDraft ? recipientDrafts.get(key) : "";
  const isDefaultRecipient = shouldPrefill && !hasDraft;
  input.id = `recipient-${id}-${index}`;
  input.type = "text";
  input.maxLength = 80;
  input.autocomplete = "name";
  input.required = true;
  input.placeholder = shouldPrefill && currentGuestName() ? currentGuestName() : "Name";
  input.value = isDefaultRecipient ? currentGuestName() : draft;
  input.dataset.assignmentKey = key;
  input.dataset.defaultRecipient = isDefaultRecipient ? "true" : "false";
  input.dataset.nameAutocomplete = "";
  input.className = "basket-recipient-input";
  input.addEventListener("input", () => {
    input.dataset.defaultRecipient = "false";
    recipientDrafts.set(key, input.value);
    updateBasketSubmissionState();
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
  const totalQuantity = Object.values(items)
    .reduce((total, quantity) => total + quantity, 0);
  const shouldPrefillRecipient = totalQuantity === 1;

  Object.entries(items).forEach(([id, quantity]) => {
    const item = catalogById.get(id);

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
      recipientsWrap.append(
        recipientInput(id, index, item.name, shouldPrefillRecipient),
      );
    }
    row.append(recipientsWrap);
    basketItemsElement.append(row);
  });

  basketEmpty.hidden = totalQuantity > 0;
  basketTotal.textContent = totalQuantity
    ? `${totalQuantity} item${totalQuantity === 1 ? "" : "s"}`
    : "";
  window.partyNameSuggestions?.enhance(basketItemsElement);
  updateBasketSubmissionState();
}

basketForm.addEventListener("submit", (event) => {
  renderBasket();
  if (!basketItemsInput.value || basketItemsInput.value === "[]") {
    event.preventDefault();
  }
});

guestNameInput.addEventListener("input", () => {
  const nextGuestName = currentGuestName();
  const shouldPrefillRecipient = window.partyBasket.count() === 1;
  basketItemsElement.querySelectorAll(".basket-recipient-input").forEach((input) => {
    input.placeholder = shouldPrefillRecipient && nextGuestName ? nextGuestName : "Name";
    if (input.dataset.defaultRecipient === "true") {
      input.value = nextGuestName;
    }
  });
  updateBasketSubmissionState();
});

basketItemsElement.addEventListener("party-name-selected", (event) => {
  const input = event.target.closest(".basket-recipient-input");
  if (input) focusNextRecipient(input);
});

window.addEventListener("storage", renderBasket);
renderBasket();
