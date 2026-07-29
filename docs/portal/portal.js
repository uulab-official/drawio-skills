(() => {
  const input = document.querySelector('#catalog-search');
  const cards = [...document.querySelectorAll('.portal-card')];
  const count = document.querySelector('#count');
  const empty = document.querySelector('#empty');
  const filter = () => {
    const query = input.value.trim().toLowerCase();
    let visible = 0;
    for (const card of cards) {
      const match = !query || card.dataset.search.includes(query);
      card.hidden = !match;
      if (match) visible += 1;
    }
    count.textContent = String(visible);
    empty.style.display = visible ? 'none' : 'block';
  };
  input.addEventListener('input', filter);
})();
