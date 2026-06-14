const searchInput = document.querySelector("#menu-search-input");
const clearButton = document.querySelector("#menu-search-clear");
const searchStatus = document.querySelector("#menu-search-status");
const emptyState = document.querySelector("#menu-search-empty");
const sections = Array.from(document.querySelectorAll("[data-menu-section]"));
const menuTitles = Array.from(document.querySelectorAll(".item-copy h3"));
const mobileMenu = window.matchMedia("(max-width: 760px)");
const basketSummary = document.querySelector("#basket-summary");
const basketCount = document.querySelector("#basket-count");
const basketCountLabel = document.querySelector("#basket-count-label");
const basketButtons = Array.from(document.querySelectorAll("[data-basket-add]"));

const normalizeSearchText = (value) =>
  value
    .normalize("NFKD")
    .replace(/\p{Diacritic}/gu, "")
    .toLocaleLowerCase()
    .trim();

const searchableItems = sections.flatMap((section) =>
  Array.from(section.querySelectorAll(".menu-item")).map((item) => ({
    element: item,
    section,
    text: normalizeSearchText(
      `${item.querySelector("h3")?.textContent || ""} ${item.querySelector(".item-copy > p")?.textContent || ""}`,
    ),
  })),
);

function fitMenuTitle(title) {
  title.style.removeProperty("font-size");
  title.classList.remove("is-forced-wrap");
  if (
    !mobileMenu.matches ||
    !title.clientWidth ||
    title.scrollWidth <= title.clientWidth
  ) {
    return;
  }

  const startingSize = Number.parseFloat(getComputedStyle(title).fontSize);
  const scale = title.clientWidth / title.scrollWidth;
  let fittedSize = Math.max(16, Math.floor(startingSize * scale * 10) / 10);
  title.style.fontSize = `${fittedSize}px`;

  while (title.scrollWidth > title.clientWidth && fittedSize > 16) {
    fittedSize = Math.max(16, fittedSize - 0.5);
    title.style.fontSize = `${fittedSize}px`;
  }

  title.classList.toggle("is-forced-wrap", title.scrollWidth > title.clientWidth);
}

function fitMenuTitles() {
  menuTitles.forEach(fitMenuTitle);
}

let resizeFrame;
window.addEventListener("resize", () => {
  window.cancelAnimationFrame(resizeFrame);
  resizeFrame = window.requestAnimationFrame(fitMenuTitles);
});

fitMenuTitles();
document.fonts?.ready.then(fitMenuTitles);

function filterMenu() {
  const rawQuery = searchInput.value.trim();
  const query = normalizeSearchText(rawQuery);
  let resultCount = 0;

  sections.forEach((section) => {
    let sectionMatches = 0;
    searchableItems
      .filter((item) => item.section === section)
      .forEach((item) => {
        const matches = !query || item.text.includes(query);
        item.element.hidden = !matches;
        if (matches) sectionMatches += 1;
      });

    const sectionHidden = Boolean(query) && sectionMatches === 0;
    section.hidden = sectionHidden;
    const categoryLink = document.querySelector(`.category-nav a[href="#${section.id}"]`);
    if (categoryLink) categoryLink.hidden = sectionHidden;
    resultCount += sectionMatches;
  });

  clearButton.hidden = !query;
  emptyState.hidden = !query || resultCount > 0;
  searchStatus.textContent = query
    ? `${resultCount} result${resultCount === 1 ? "" : "s"} for “${rawQuery}”`
    : `${searchableItems.length} menu item${searchableItems.length === 1 ? "" : "s"}`;
  fitMenuTitles();
}

searchInput.addEventListener("input", filterMenu);
searchInput.addEventListener("search", filterMenu);
clearButton.addEventListener("click", () => {
  searchInput.value = "";
  filterMenu();
  searchInput.focus();
});

function updateBasketSummary() {
  const count = window.partyBasket.count();
  basketCount.textContent = count;
  basketCountLabel.textContent = count === 1 ? "item" : "items";
  basketSummary.hidden = count === 0;
}

const menuParameters = new URLSearchParams(window.location.search);
if (menuParameters.get("basket_sent") === "1") {
  window.partyBasket.clear();
  menuParameters.delete("basket_sent");
  const cleanQuery = menuParameters.toString();
  window.history.replaceState(
    {},
    "",
    `${window.location.pathname}${cleanQuery ? `?${cleanQuery}` : ""}${window.location.hash}`,
  );
}

basketButtons.forEach((button) => {
  button.addEventListener("click", () => {
    window.partyBasket.add(button.dataset.basketAdd);
    const originalLabel = button.textContent;
    button.textContent = "Added";
    window.setTimeout(() => {
      button.textContent = originalLabel;
    }, 700);
    updateBasketSummary();
  });
});

window.addEventListener("party-basket-change", updateBasketSummary);
window.addEventListener("storage", updateBasketSummary);
updateBasketSummary();
