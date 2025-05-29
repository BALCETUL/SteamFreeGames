import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
from pathlib import Path
import time

# URL для поиска игр со скидкой 100% (бесплатно)
SEARCH_URL = (
    'https://store.steampowered.com/search/results/'
    '?query&start=0&count=50&filter=globaltopsellers&discount_range=100&infinite=1'
)
# Заголовки для обхода ограничений
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/90.0.4430.212 Safari/537.36'
}
JSON_PATH = Path('free_goods_detail.json')


def fetch_free_games():
    """
    Делает запрос к Steam Search API, парсит HTML-результат и собирает
    список игр/DLC со скидкой 100%.
    """
    resp = requests.get(SEARCH_URL, headers=HEADERS)
    resp.raise_for_status()
    data = resp.json()
    html = data.get('results_html', '')
    soup = BeautifulSoup(html, 'html.parser')
    free_list = []

    for idx, row in enumerate(soup.select('a.search_result_row')):
        # Иконка скидки
        disc = row.select_one('.search_discount span')
        if not disc or disc.get_text(strip=True) != '-100%':
            continue
        # Название
        name_tag = row.select_one('.search_name span')
        title = name_tag.get_text(strip=True) if name_tag else 'Без названия'
        # Ссылка на игру или DLC
        link = row.get('href', '')
        free_list.append([title, link])
    return free_list


def main():
    # Время обновления
    now = datetime.utcnow()  # UTC
    # Переводим в UTC+3
    now = now + time.timedelta(hours=3)
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')

    # Получаем список бесплатных игр
    free_list = fetch_free_games()

    # Загружаем предыдущий JSON, чтобы достать историю
    if JSON_PATH.exists():
        old_data = json.loads(JSON_PATH.read_text(encoding='utf-8'))
        history = old_data.get('update_history', [])
    else:
        history = []

    # Добавляем новое время в начало и обрезаем до 10
    history.insert(0, now_str)
    history = history[:10]

    # Собираем новый словарь для сохранения
    result = {
        'total_count': len(free_list),
        'free_list': free_list,
        'update_time': now_str,
        'update_history': history,
    }

    # Сохраняем JSON
    JSON_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"Обновлено: {now_str}. Найдено игр: {len(free_list)}")


if __name__ == '__main__':
    main()
