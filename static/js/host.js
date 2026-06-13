const items = new Map(
  JSON.parse(document.querySelector("#menu-data")?.textContent || "[]").map((item) => [String(item.id), item]),
);

const itemDialog = document.querySelector("#item-dialog");
const bulkDialog = document.querySelector("#bulk-dialog");

function openItemDialog(item = null) {
  document.querySelector("#item-dialog-title").textContent = item ? "Edit item" : "Add item";
  document.querySelector("#item-id").value = item?.id || "";
  document.querySelector("#item-name").value = item?.name || "";
  document.querySelector("#item-description").value = item?.description || "";
  document.querySelector("#item-category").value = item?.category || "Cocktails";
  document.querySelector("#item-available").value = item ? String(item.available) : "1";
  document.querySelector("#existing-image").value = item?.image || "";
  document.querySelector("#image-url").value = item?.image?.startsWith("http") ? item.image : "";
  itemDialog.showModal();
  document.querySelector("#item-name").focus();
}

document.querySelectorAll(".js-add-item").forEach((button) => {
  button.addEventListener("click", () => openItemDialog());
});

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
