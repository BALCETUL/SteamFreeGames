import requests
from bs4 import BeautifulSoup
import json
import datetime
import pytz
from concurrent.futures import ThreadPoolExecutor, wait, ALL_COMPLETED
import queue
import time

# Для SteamDB
STEAMDB_URL = "https://steamdb.info/upcoming/free/"
# Для стандартного поиска Steam (как резерв)
STEAM_URL_TEMPLATE = "https://store.steampowered.com/search/results/?query&start={pos}&count=100&maxprice=free&specials=1&infinite=1"
THREAD_CNT = 8

free_list = queue.Queue()

def fetch_html(url, steamdb=False):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    if steamdb:
        headers["Referer"] = "https://steamdb.info/"
    
    while True:
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.text
        except Exception as e:
            print(f"Ошибка запроса: {e}. Повтор через 10 сек...")
            time.sleep(10)

def parse_steamdb():
    html = fetch_html(STEAMDB_URL, steamdb=True)
    soup = BeautifulSoup(html, "html.parser")
    
    games = []
    for item in soup.select(".app-history-row"):
        try:
            name = item.select_one(".panel-sale-name b").text.strip()
            store_link = item.select_one(".app-history-type a[href*='store.steampowered.com']")["href"]
            install_link = f"steam://install/{item['data-appid']}" if "data-appid" in item.attrs else None
            
            # Определяем тип (Free to Keep / Play For Free)
            promo_type = "Free to Keep"
            if "Play For Free" in item.select_one(".cat").text:
                promo_type = "Play For Free"
            
            # Время начала/окончания
            time_elements = item.select(".panel-sale-time relative-time")
            start_time = time_elements[0]["datetime"] if len(time_elements) > 0 else ""
            end_time = time_elements[1]["datetime"] if len(time_elements) > 1 else ""
            
            games.append({
                "name": name,
                "url": store_link,
                "install": install_link,
                "type": promo_type,
                "start": start_time,
                "end": end_time
            })
        except Exception as e:
            print(f"Ошибка парсинга элемента: {e}")
            continue
    
    return games

def parse_steam_backup():
    # Ваш существующий код для Steam Search (как резерв)
    pass

if __name__ == "__main__":
    # Парсим SteamDB как основной источник
    steamdb_games = parse_steamdb()
    
    # Добавляем резервный парсинг Steam если нужно
    if not steamdb_games:
        print("SteamDB не вернул игры, используем резервный Steam Search")
        steamdb_games = parse_steam_backup()
    
    # Сохраняем в JSON
    with open("free_goods_detail.json", "w", encoding="utf-8") as f:
        json.dump({
            "total_count": len(steamdb_games),
            "free_list": steamdb_games,
            "update_time": datetime.datetime.now(
                tz=pytz.timezone("Europe/Kiev")
            ).strftime('%Y-%m-%d %H:%M:%S'),
            "source": "steamdb"
        }, f, ensure_ascii=False, indent=2)
