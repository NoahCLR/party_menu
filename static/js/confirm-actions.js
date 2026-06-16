document.querySelectorAll("[data-confirm-message]").forEach((element) => {
  element.addEventListener("submit", (event) => {
    if (!window.confirm(element.dataset.confirmMessage)) {
      event.preventDefault();
    }
  });
});
