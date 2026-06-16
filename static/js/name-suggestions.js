const guestNamesData = document.querySelector("#guest-names-data");
const guestNameOptions = JSON.parse(guestNamesData?.textContent || "[]");

function normalizeName(value) {
  return String(value || "").trim().toLocaleLowerCase();
}

function createSuggestionButton(name, input, panel) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = name;
  button.addEventListener("click", () => {
    input.value = name;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    panel.hidden = true;
    input.focus();
  });
  return button;
}

function enhanceNameInput(input) {
  if (input.dataset.nameSuggestionsReady === "true") return;
  input.dataset.nameSuggestionsReady = "true";

  const panel = document.createElement("div");
  panel.className = "name-suggestions";
  panel.hidden = true;
  input.insertAdjacentElement("afterend", panel);

  function renderSuggestions() {
    const query = normalizeName(input.value);
    const matches = guestNameOptions
      .filter((name) => {
        const option = normalizeName(name);
        return option && option !== query && (!query || option.includes(query));
      })
      .slice(0, 5);

    panel.replaceChildren();
    matches.forEach((name) => {
      panel.append(createSuggestionButton(name, input, panel));
    });
    panel.hidden = matches.length === 0;
  }

  input.addEventListener("input", renderSuggestions);
  input.addEventListener("focus", renderSuggestions);
  input.addEventListener("blur", () => {
    window.setTimeout(() => {
      panel.hidden = true;
    }, 120);
  });
}

function enhanceNameSuggestions(root = document) {
  root.querySelectorAll("[data-name-autocomplete]").forEach(enhanceNameInput);
}

window.partyNameSuggestions = { enhance: enhanceNameSuggestions };
enhanceNameSuggestions();
