(() => {
  const storageKey = "party-menu-basket-v1";
  const maximumDistinctItems = 25;
  const maximumQuantity = 20;
  const maximumTotalItems = 50;

  function normalize(items) {
    if (!items || typeof items !== "object" || Array.isArray(items)) return {};

    const normalized = {};
    let remaining = maximumTotalItems;
    for (const [rawId, rawQuantity] of Object.entries(items)) {
      if (Object.keys(normalized).length >= maximumDistinctItems || remaining <= 0) break;
      if (!/^\d+$/.test(rawId) || Number(rawId) <= 0) continue;

      const quantity = Math.min(
        Number.parseInt(rawQuantity, 10),
        maximumQuantity,
        remaining,
      );
      if (!Number.isFinite(quantity) || quantity <= 0) continue;
      normalized[String(Number(rawId))] = quantity;
      remaining -= quantity;
    }
    return normalized;
  }

  function read() {
    try {
      return normalize(JSON.parse(window.localStorage.getItem(storageKey) || "{}"));
    } catch (_error) {
      return {};
    }
  }

  function write(items) {
    const normalized = normalize(items);
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(normalized));
    } catch (_error) {
      return read();
    }
    window.dispatchEvent(new CustomEvent("party-basket-change"));
    return normalized;
  }

  function setQuantity(id, quantity) {
    const items = read();
    const itemId = String(id);
    if (quantity > 0) items[itemId] = Math.min(quantity, maximumQuantity);
    else delete items[itemId];
    return write(items);
  }

  window.partyBasket = Object.freeze({
    add(id) {
      const items = read();
      const itemId = String(id);
      return setQuantity(itemId, (items[itemId] || 0) + 1);
    },
    clear() {
      return write({});
    },
    count() {
      return Object.values(read()).reduce((total, quantity) => total + quantity, 0);
    },
    read,
    setQuantity,
    write,
  });
})();
