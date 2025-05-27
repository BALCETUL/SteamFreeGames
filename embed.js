// embed.js
;(function(){
  const defaults = {
    selector: null,
    maxItems: 3,
    showImages: true,
    width: '100%',               // можно px или %
    theme: {
      background: '#f9fafb',
      headerText: '#222',
      text: '#111',
      link: '#3b82f6',
      linkHover: '#2563eb',
      boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
      borderRadius: '12px'
    }
  };

  function merge(a,b){
    for(let k in b){
      if(b[k] && typeof b[k]==='object' && !Array.isArray(b[k])){
        a[k] = merge(a[k]||{}, b[k]);
      } else if(b[k] !== undefined){
        a[k] = b[k];
      }
    }
    return a;
  }

  window.SteamFreeEmbed = {
    init(userConfig){
      const cfg = merge(JSON.parse(JSON.stringify(defaults)), userConfig||{});
      if(!cfg.selector) return console.error('SteamFreeEmbed: selector is required');
      const root = document.querySelector(cfg.selector);
      if(!root) return console.error('SteamFreeEmbed: container not found', cfg.selector);

      // создаём базовую разметку
      root.innerHTML = '';
      const card = document.createElement('div');
      card.style.cssText = `
        max-width: ${cfg.width};
        margin: 1em auto;
        padding: 1em;
        background: ${cfg.theme.background};
        border-radius: ${cfg.theme.borderRadius};
        box-shadow: ${cfg.theme.boxShadow};
        font-family: sans-serif;
        color: ${cfg.theme.text};
      `;
      root.appendChild(card);

      const header = document.createElement('h3');
      header.textContent = '🎮 Бесплатные раздачи Steam';
      header.style.color = cfg.theme.headerText;
      header.style.marginBottom = '.5em';
      card.appendChild(header);

      const listContainer = document.createElement('div');
      card.appendChild(listContainer);

      // спиннер
      const spinner = document.createElement('div');
      spinner.innerHTML = `<div style="
          border:4px solid rgba(0,0,0,0.1);
          border-top:4px solid ${cfg.theme.link};
          border-radius:50%;
          width:30px;height:30px;
          animation:spin 1s linear infinite;
        "></div>`;
      listContainer.appendChild(spinner);

      // стили для спина
      const style = document.createElement('style');
      style.textContent = `
        @keyframes spin { to { transform:rotate(360deg) } }
        .sfe-item { display:flex; align-items:center; margin:.5em 0; }
        .sfe-item img { width:60px; height:30px; object-fit:cover; border-radius:4px; margin-right:.5em; }
        .sfe-item a { color: ${cfg.theme.link}; text-decoration:none; }
        .sfe-item a:hover { color: ${cfg.theme.linkHover}; }
      `;
      document.head.appendChild(style);

      // подгружаем JSON
      fetch('https://raw.githubusercontent.com/BALCETUL/SteamFreeGames/main/free_goods_detail.json')
        .then(r=>r.json())
        .then(data=>{
          listContainer.innerHTML = ''; // убираем спиннер
          const list = (data.free_list||[]).slice(0, cfg.maxItems);
          if(list.length===0){
            listContainer.innerHTML = '<p>Сейчас нет бесплатных предложений.</p>';
            return;
          }
          list.forEach(([name, link])=>{
            const li = document.createElement('div');
            li.className = 'sfe-item';
            let html = '';
            if(cfg.showImages){
              const match = link.match(/\/(app|sub)\/(\d+)/);
              const type = match[1], id = match[2];
              const url = `https://cdn.akamai.steamstatic.com/steam/${type}s/${id}/capsule_sm_120.jpg`;
              html += `<img src="${url}" alt="${name}" onerror="this.src='https://via.placeholder.com/120x60?text=Нет+Image'"/>`;
            }
            html += `<a href="${link}" target="_blank" rel="noopener">${name}</a>`;
            li.innerHTML = html;
            listContainer.appendChild(li);
          });
        })
        .catch(err=>{
          listContainer.innerHTML = '<p>Ошибка загрузки виджета.</p>';
          console.error(err);
        });
    }
  };
})();
