const choose = (items) => {
  items.map(item => item || fallback);
  return items[0] ?? fallback;
};