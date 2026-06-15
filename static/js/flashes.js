const flashMessages = Array.from(
  document.querySelectorAll(".public-flash, .order-flash, .flash"),
);

flashMessages.forEach((message) => {
  window.setTimeout(() => {
    message.classList.add("is-dismissing");
    message.addEventListener(
      "transitionend",
      () => {
        const container = message.parentElement;
        message.remove();
        if (container?.classList.contains("public-flashes") && !container.children.length) {
          container.remove();
        }
      },
      { once: true },
    );

    window.setTimeout(() => {
      if (!message.isConnected) return;
      const container = message.parentElement;
      message.remove();
      if (container?.classList.contains("public-flashes") && !container.children.length) {
        container.remove();
      }
    }, 400);
  }, 6000);
});
