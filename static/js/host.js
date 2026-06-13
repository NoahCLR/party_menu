const items = new Map(
  JSON.parse(document.querySelector("#menu-data")?.textContent || "[]").map((item) => [String(item.id), item]),
);

const itemDialog = document.querySelector("#item-dialog");
const categoryDialog = document.querySelector("#category-dialog");
const bulkDialog = document.querySelector("#bulk-dialog");

function openItemDialog(item = null) {
  const categorySelect = document.querySelector("#item-category");
  document.querySelector("#item-dialog-title").textContent = item ? "Edit item" : "Add item";
  document.querySelector("#item-id").value = item?.id || "";
  document.querySelector("#item-name").value = item?.name || "";
  document.querySelector("#item-description").value = item?.description || "";
  categorySelect.value = item?.category || categorySelect.dataset.defaultCategory || categorySelect.options[0]?.value || "";
  document.querySelector("#item-available").value = item ? String(item.available) : "1";
  document.querySelector("#existing-image").value = item?.image || "";
  document.querySelector("#image-url").value = item?.image?.startsWith("http") ? item.image : "";
  itemDialog.showModal();
  document.querySelector("#item-name").focus();
}

document.querySelectorAll(".js-add-item").forEach((button) => {
  button.addEventListener("click", () => openItemDialog());
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

document.querySelectorAll(".js-delete-form").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!window.confirm(`Delete ${form.dataset.name}?`)) event.preventDefault();
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
