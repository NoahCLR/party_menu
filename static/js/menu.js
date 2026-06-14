const searchInput = document.querySelector("#menu-search-input");
const clearButton = document.querySelector("#menu-search-clear");
const searchStatus = document.querySelector("#menu-search-status");
const emptyState = document.querySelector("#menu-search-empty");
const sections = Array.from(document.querySelectorAll("[data-menu-section]"));

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
}

searchInput.addEventListener("input", filterMenu);
searchInput.addEventListener("search", filterMenu);
clearButton.addEventListener("click", () => {
  searchInput.value = "";
  filterMenu();
  searchInput.focus();
});
