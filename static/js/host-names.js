const guestNameRows = Array.from(document.querySelectorAll("[data-guest-row]"));
const guestNameSearchInput = document.querySelector("#guest-name-search-input");
const guestNameSearchClear = document.querySelector("#guest-name-search-clear");
const guestNameSearchStatus = document.querySelector("#guest-name-search-status");
const guestNameSearchEmpty = document.querySelector("#guest-name-search-empty");
const guestNameSortButtons = Array.from(document.querySelectorAll("[data-guest-sort]"));
let activeGuestSort = "name";
let guestSortDirection = "asc";

function normalizeGuestSearch(value) {
  return String(value || "")
    .normalize("NFKD")
    .replace(/\p{Diacritic}/gu, "")
    .toLocaleLowerCase()
    .trim();
}

function guestValue(row, key) {
  if (key === "name") return normalizeGuestSearch(row.dataset.name);
  return Number(row.dataset[key] || 0);
}

function compareGuestRows(left, right) {
  const leftValue = guestValue(left, activeGuestSort);
  const rightValue = guestValue(right, activeGuestSort);
  let result = 0;
  if (typeof leftValue === "number") {
    result = leftValue - rightValue;
  } else {
    result = leftValue.localeCompare(rightValue);
  }
  return guestSortDirection === "asc" ? result : -result;
}

function renderGuestNameRows() {
  if (!guestNameSearchInput || !guestNameSearchStatus) return;
  const query = normalizeGuestSearch(guestNameSearchInput.value);
  const visibleRows = [];
  guestNameRows.sort(compareGuestRows).forEach((row) => {
    const matches = !query || normalizeGuestSearch(row.dataset.name).includes(query);
    row.hidden = !matches;
    row.parentElement.append(row);
    if (matches) visibleRows.push(row);
  });
  if (guestNameSearchEmpty) {
    guestNameSearchEmpty.hidden = !query || visibleRows.length > 0;
    guestNameSearchEmpty.parentElement.append(guestNameSearchEmpty);
  }
  guestNameSearchClear.hidden = !query;
  guestNameSearchStatus.textContent = query
    ? `${visibleRows.length} result${visibleRows.length === 1 ? "" : "s"} for "${guestNameSearchInput.value.trim()}"`
    : `${guestNameRows.length} name${guestNameRows.length === 1 ? "" : "s"}`;
}

function updateGuestSortButtons() {
  guestNameSortButtons.forEach((sortButton) => {
    const active = sortButton.dataset.guestSort === activeGuestSort;
    sortButton.classList.toggle("active", active);
    sortButton.setAttribute("aria-pressed", active ? "true" : "false");
    sortButton.dataset.sortDirection = active ? guestSortDirection : "";
  });
}

guestNameSearchInput?.addEventListener("input", renderGuestNameRows);
guestNameSearchInput?.addEventListener("search", renderGuestNameRows);
guestNameSearchClear?.addEventListener("click", () => {
  guestNameSearchInput.value = "";
  renderGuestNameRows();
  guestNameSearchInput.focus();
});

guestNameSortButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const nextSort = button.dataset.guestSort;
    if (activeGuestSort === nextSort) {
      guestSortDirection = guestSortDirection === "asc" ? "desc" : "asc";
    } else {
      activeGuestSort = nextSort;
      guestSortDirection = nextSort === "name" ? "asc" : "desc";
    }
    updateGuestSortButtons();
    renderGuestNameRows();
  });
});

updateGuestSortButtons();
renderGuestNameRows();
