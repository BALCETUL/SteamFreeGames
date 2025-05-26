# SteamFreeGames 🎮

**SteamFreeGames** — это автоматизированный проект по сбору и отображению игр со 100% скидкой в Steam.  
Проект автоматически обновляется каждый день и отображает список бесплатных игр на веб-странице.

🔗 **Сайт:** [SteamFreeGames](https://balcetul.github.io/SteamFreeGames/)  
🔁 Обновление: каждый день в 00:00 (по UTC)  
📄 JSON-данные: [free_goods_detail.json](./free_goods_detail.json)

## Возможности

- Автоматический парсинг бесплатных игр из Steam
- Современный интерфейс на Bootstrap 5
- Обновление данных через GitHub Actions

## Автор

BALCETUL — [GitHub профайл](https://github.com/BALCETUL)

---

# SteamFreeGames

**Парсер бесплатных (100% скидка) игр Steam**  
Полностью в браузере, с автозапуском на GitHub Actions и тёмным дизайном на Pages.

## Структура

- `.github/workflows/python-app.yml` — автозапуск каждый день и вручную  
- `NeedFree.py` — многопоточный краулер Steam  
- `requirements.txt` — зависимости  
- `free_goods_detail.json` — результат (генерится автоматически)  
- `index.html` — фронтенд со стильной тёмной темой  

## Как пользоваться

1. Push в репозиторий — Actions запустится автоматически.  
2. JSON обновится в `free_goods_detail.json`.  
3. GitHub Pages покажет список на `index.html`.

Автор: **BALCETUL**  
Ссылка: https://github.com/BALCETUL/SteamFreeGames
