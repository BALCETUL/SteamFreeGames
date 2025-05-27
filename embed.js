// embed.js
window.SteamFreeEmbed = {
  /**
   * Инициализация виджета.
   * @param {Object} config 
   * @param {string} config.selector — CSS-селектор контейнера
   * @param {number} [config.maxItems=3] — сколько карточек показывать
   * @param {boolean} [config.showImages=false] — показывать мини-обложки
   * @param {string} [config.locale='ru'] — язык (не используется сейчас)
   */
  init({ selector, maxItems = 3, showImages = false, locale = 'ru' }) {
    const container = document.querySelector(selector);
    if (!container) return;
    fetch('https://raw.githubusercontent.com/BALCETUL/SteamFreeGames/main/free_goods_detail.json')
      .then(r => r.json())
      .then(data => {
        const list = (data.free_list || []).slice(0, maxItems);
        if (list.length === 0) {
          container.innerHTML = '<p>Сейчас нет бесплатных предложений.</p>';
          return;
        }
        const ul = document.createElement('ul');
        ul.style.listStyle = 'none';
        ul.style.padding = '0';
        ul.style.margin = '0';
        list.forEach(([name, link]) => {
          const li = document.createElement('li');
          li.style.margin = '0.5em 0';
          let html = '';
          if (showImages) {
            // определяем ID для мини-обложки
            const match = link.match(/\/app\/(\d+)|\/sub\/(\d+)/);
            const id = match ? (match[1] || match[2]) : null;
            if (id) {
              html += `<img src="https://cdn.akamai.steamstatic.com/steam/apps/${id}/capsule_sm_120.jpg" ` +
                      `style="vertical-align:middle;margin-right:8px;"/>`;
            }
          }
          html += `<a href="${link}" target="_blank" rel="noopener">${name}</a>`;
          li.innerHTML = html;
          ul.appendChild(li);
        });
        container.appendChild(ul);
      })
      .catch(err => {
        console.error('SteamFreeEmbed error:', err);
        container.innerHTML = '<p>Не удалось загрузить виджет.</p>';
      });
  }
};
