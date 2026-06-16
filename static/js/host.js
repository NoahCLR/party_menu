const items = new Map(
  JSON.parse(document.querySelector("#menu-data")?.textContent || "[]").map((item) => [String(item.id), item]),
);

const itemDialog = document.querySelector("#item-dialog");
const categoryDialog = document.querySelector("#category-dialog");
const categoryRemoveDialog = document.querySelector("#category-remove-dialog");
const categoryRemoveForm = document.querySelector("#category-remove-form");
const bulkDialog = document.querySelector("#bulk-dialog");
const bulkImportForm = document.querySelector("#bulk-import-form");
const recipeList = document.querySelector("#recipe-list");
const addRecipeIngredientButton = document.querySelector("#add-recipe-ingredient");
const imageFileInput = document.querySelector("#image-file");
const imageUrlInput = document.querySelector("#image-url");
const existingImageInput = document.querySelector("#existing-image");
const imageFocusX = document.querySelector("#image-focus-x");
const imageFocusY = document.querySelector("#image-focus-y");
const imageFocusPreview = document.querySelector("#image-focus-preview");
const imageFocusPreviewImage = document.querySelector("#image-focus-preview-image");
const imageFocusMarker = document.querySelector("#image-focus-marker");
const imageFocusValue = document.querySelector("#image-focus-value");
const imageFocusEmpty = document.querySelector("#image-focus-empty");
const hostSearchInput = document.querySelector("#host-search-input");
const hostSearchClear = document.querySelector("#host-search-clear");
const hostSearchStatus = document.querySelector("#host-search-status");
const hostSearchEmpty = document.querySelector("#host-search-empty");
const hostFilterEmpty = document.querySelector("#host-filter-empty");
const hostRows = Array.from(document.querySelectorAll("[data-host-row]"));
let previewObjectUrl = "";

const normalizeHostSearchText = (value) =>
  value
    .normalize("NFKD")
    .replace(/\p{Diacritic}/gu, "")
    .toLocaleLowerCase()
    .trim();

function recipeSearchText(item) {
  if (!Array.isArray(item?.recipe)) return "";
  return item.recipe.map((ingredient) => ingredient.name || "").join(" ");
}

const searchableHostRows = hostRows.map((row) => {
  const item = items.get(row.dataset.id);
  const availability = item?.available ? "available" : "out";
  return {
    row,
    text: normalizeHostSearchText(
      `${item?.name || ""} ${item?.description || ""} ${item?.category || ""} ${availability} ${recipeSearchText(item)}`,
    ),
  };
});

function filterHostRows() {
  const rawQuery = hostSearchInput.value.trim();
  const query = normalizeHostSearchText(rawQuery);
  let resultCount = 0;

  searchableHostRows.forEach((item) => {
    const matches = !query || item.text.includes(query);
    item.row.hidden = !matches;
    if (matches) resultCount += 1;
  });

  hostSearchClear.hidden = !query;
  if (hostFilterEmpty) hostFilterEmpty.hidden = Boolean(query);
  hostSearchEmpty.hidden = !query || resultCount > 0;
  hostSearchStatus.textContent = query
    ? `${resultCount} result${resultCount === 1 ? "" : "s"} for "${rawQuery}"`
    : `${searchableHostRows.length} item${searchableHostRows.length === 1 ? "" : "s"} in this view`;
}

hostSearchInput.addEventListener("input", filterHostRows);
hostSearchInput.addEventListener("search", filterHostRows);
hostSearchClear.addEventListener("click", () => {
  hostSearchInput.value = "";
  filterHostRows();
  hostSearchInput.focus();
});

function clampFocus(value) {
  return Math.min(100, Math.max(0, Number(value) || 0));
}

function setImageFocus(x, y) {
  const focusX = Math.round(clampFocus(x) * 10) / 10;
  const focusY = Math.round(clampFocus(y) * 10) / 10;
  imageFocusX.value = focusX;
  imageFocusY.value = focusY;
  imageFocusPreviewImage.style.objectPosition = `${focusX}% ${focusY}%`;
  imageFocusMarker.style.left = `${focusX}%`;
  imageFocusMarker.style.top = `${focusY}%`;
  imageFocusValue.textContent = `${focusX}% · ${focusY}%`;
}

function setImagePreview(source) {
  imageFocusPreview.hidden = !source;
  imageFocusEmpty.hidden = Boolean(source);
  imageFocusPreviewImage.src = source || "";
}

function focusFromPointer(event) {
  const bounds = imageFocusPreview.getBoundingClientRect();
  setImageFocus(
    ((event.clientX - bounds.left) / bounds.width) * 100,
    ((event.clientY - bounds.top) / bounds.height) * 100,
  );
}

function applyStoredImageFocus(image) {
  image.style.objectPosition = `${clampFocus(image.dataset.focusX)}% ${clampFocus(image.dataset.focusY)}%`;
}

document.querySelectorAll("img[data-focus-x][data-focus-y]").forEach(applyStoredImageFocus);

imageFileInput.addEventListener("change", () => {
  if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl);
  previewObjectUrl = imageFileInput.files[0]
    ? URL.createObjectURL(imageFileInput.files[0])
    : "";
  setImagePreview(
    previewObjectUrl || imageUrlInput.value.trim() || existingImageInput.value,
  );
});

imageUrlInput.addEventListener("change", () => {
  if (!imageFileInput.files.length) {
    setImagePreview(imageUrlInput.value.trim() || existingImageInput.value);
  }
});

imageFocusPreview.addEventListener("pointerdown", (event) => {
  imageFocusPreview.setPointerCapture(event.pointerId);
  focusFromPointer(event);
});

imageFocusPreview.addEventListener("pointermove", (event) => {
  if (imageFocusPreview.hasPointerCapture(event.pointerId)) focusFromPointer(event);
});

imageFocusPreview.addEventListener("keydown", (event) => {
  const movement = {
    ArrowLeft: [-2, 0],
    ArrowRight: [2, 0],
    ArrowUp: [0, -2],
    ArrowDown: [0, 2],
  }[event.key];
  if (!movement) return;
  event.preventDefault();
  setImageFocus(
    Number(imageFocusX.value) + movement[0],
    Number(imageFocusY.value) + movement[1],
  );
});

document.querySelector("#image-focus-center").addEventListener("click", () => {
  setImageFocus(50, 50);
  imageFocusPreview.focus();
});

function updateRecipeAddButton() {
  addRecipeIngredientButton.disabled = recipeList.children.length >= 20;
}

function addRecipeRow(ingredient = { name: "", ml: "" }) {
  const row = document.createElement("div");
  row.className = "recipe-row";

  const nameLabel = document.createElement("label");
  const nameText = document.createElement("span");
  nameText.textContent = "Ingredient";
  const nameInput = document.createElement("input");
  nameInput.name = "recipe_name";
  nameInput.value = ingredient.name || "";
  nameInput.maxLength = 80;
  nameInput.autocomplete = "off";
  nameInput.placeholder = "e.g. Vodka or ice";
  nameLabel.append(nameText, nameInput);

  const amountLabel = document.createElement("label");
  amountLabel.className = "recipe-amount";
  const amountText = document.createElement("span");
  amountText.textContent = "Amount (ml)";
  const amountInput = document.createElement("input");
  amountInput.name = "recipe_ml";
  amountInput.type = "number";
  amountInput.inputMode = "decimal";
  amountInput.min = "0.01";
  amountInput.max = "10000";
  amountInput.step = "0.01";
  amountInput.value = ingredient.ml || "";
  amountInput.placeholder = "Optional";
  amountLabel.append(amountText, amountInput);

  const removeButton = document.createElement("button");
  removeButton.type = "button";
  removeButton.className = "recipe-remove-button";
  removeButton.textContent = "Remove";
  removeButton.setAttribute("aria-label", `Remove ${ingredient.name || "ingredient"}`);
  removeButton.addEventListener("click", () => {
    row.remove();
    if (!recipeList.children.length) addRecipeRow();
    updateRecipeAddButton();
  });

  row.append(nameLabel, amountLabel, removeButton);
  recipeList.append(row);
  updateRecipeAddButton();
}

function renderRecipe(recipe = []) {
  recipeList.replaceChildren();
  (recipe.length ? recipe : [{ name: "", ml: "" }]).forEach(addRecipeRow);
}

function openItemDialog(item = null) {
  const categorySelect = document.querySelector("#item-category");
  document.querySelector("#item-dialog-title").textContent = item ? "Edit item" : "Add item";
  document.querySelector("#item-id").value = item?.id || "";
  document.querySelector("#item-name").value = item?.name || "";
  document.querySelector("#item-description").value = item?.description || "";
  categorySelect.value = item?.category || categorySelect.dataset.defaultCategory || categorySelect.options[0]?.value || "";
  document.querySelector("#item-available").value = item ? String(item.available) : "1";
  existingImageInput.value = item?.image || "";
  imageUrlInput.value = item?.image?.startsWith("http") ? item.image : "";
  imageFileInput.value = "";
  if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl);
  previewObjectUrl = "";
  setImageFocus(item?.image_focus_x ?? 50, item?.image_focus_y ?? 50);
  setImagePreview(item?.image || "");
  renderRecipe(item?.recipe || []);
  itemDialog.showModal();
  document.querySelector("#item-name").focus();
}

document.querySelectorAll(".js-add-item").forEach((button) => {
  button.addEventListener("click", () => openItemDialog());
});

addRecipeIngredientButton.addEventListener("click", () => {
  addRecipeRow();
  recipeList.lastElementChild.querySelector('input[name="recipe_name"]').focus();
});

function openCategoryDialog() {
  categoryDialog.showModal();
  categoryDialog.scrollTop = 0;
  if (window.matchMedia("(min-width: 761px)").matches) {
    document.querySelector("#category-name").focus({ preventScroll: true });
  }
}

document.querySelectorAll(".js-add-category").forEach((button) => {
  button.addEventListener("click", openCategoryDialog);
});

if (new URLSearchParams(window.location.search).get("manage_categories") === "1") {
  openCategoryDialog();
}

document.querySelectorAll(".js-edit-item").forEach((button) => {
  button.addEventListener("click", () => openItemDialog(items.get(button.dataset.id)));
});

document.querySelectorAll(".js-bulk-import").forEach((button) => {
  button.addEventListener("click", () => bulkDialog.showModal());
});

bulkImportForm.addEventListener("submit", (event) => {
  const replacesMenu = bulkImportForm.querySelector('input[name="import_mode"]:checked')?.value === "replace";
  if (replacesMenu && !window.confirm("Replace the entire current menu with this import? This cannot be undone unless you have an export.")) {
    event.preventDefault();
  }
});

function updateCategoryRemovalFields() {
  const action = categoryRemoveForm.querySelector('input[name="item_action"]:checked')?.value;
  const targetSelect = document.querySelector("#remove-target-category");
  const newCategoryInput = document.querySelector("#remove-new-category");
  targetSelect.disabled = action !== "existing";
  newCategoryInput.disabled = action !== "new";
  if (action === "new") newCategoryInput.focus();
}

document.querySelectorAll(".js-remove-category").forEach((button) => {
  button.addEventListener("click", () => {
    const itemCount = Number(button.dataset.itemCount);
    const targetSelect = document.querySelector("#remove-target-category");
    const existingRadio = categoryRemoveForm.querySelector('input[value="existing"]');

    categoryRemoveForm.action = button.dataset.action;
    document.querySelector("#remove-category-name").textContent = button.dataset.categoryName;
    document.querySelector("#remove-category-count").textContent = `${itemCount} item${itemCount === 1 ? "" : "s"}`;
    document.querySelector("#category-removal-options").hidden = itemCount === 0;
    document.querySelector("#empty-category-removal").hidden = itemCount !== 0;

    let firstDestination = "";
    Array.from(targetSelect.options).forEach((option) => {
      option.disabled = option.value.toLocaleLowerCase() === button.dataset.categoryName.toLocaleLowerCase();
      if (!option.disabled && !firstDestination) firstDestination = option.value;
    });
    targetSelect.value = firstDestination;
    existingRadio.disabled = !firstDestination;

    const defaultAction = itemCount === 0 ? "delete" : "unassigned";
    categoryRemoveForm.querySelector(`input[value="${defaultAction}"]`).checked = true;
    document.querySelector("#remove-new-category").value = "";
    updateCategoryRemovalFields();

    categoryDialog.close();
    categoryRemoveDialog.showModal();
  });
});

categoryRemoveForm.querySelectorAll('input[name="item_action"]').forEach((radio) => {
  radio.addEventListener("change", updateCategoryRemovalFields);
});

document.querySelectorAll(".js-delete-form").forEach((form) => {
  form.addEventListener("submit", (event) => {
    const message = form.dataset.confirm || `Delete ${form.dataset.name}?`;
    if (!window.confirm(message)) event.preventDefault();
  });
});

document.querySelectorAll("[data-close-dialog]").forEach((button) => {
  button.addEventListener("click", () => button.closest("dialog").close());
});

document.querySelectorAll("dialog").forEach((dialog) => {
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
});
