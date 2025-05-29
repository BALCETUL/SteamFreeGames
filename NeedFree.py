import requests
from bs4 import BeautifulSoup
import json
import datetime
import pytz

def fetch_steamdb_free_games():
    url = "https://steamdb.info/upcoming/free/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Referer": "https://steamdb.info/"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        games = []
        for item in soup.select('.app-history-row'):
            try:
                # Основная информация
                name = item.select_one('.panel-sale-name b').text.strip()
                store_url = item.select_one('.app-history-type a[href*="store.steampowered.com"]')['href']
                
                # Определяем appid/subid
                if 'data-appid' in item.attrs:
                    appid = item['data-appid']
                    install_url = f'steam://install/{appid}'
                else:
                    install_url = None
                
                # Тип предложения
                promo_type = item.select_one('.cat').text.strip()
                
                # Время действия
                time_elements = item.select('.panel-sale-time relative-time')
                start_time = time_elements[0]['datetime'] if len(time_elements) > 0 else ""
                end_time = time_elements[1]['datetime'] if len(time_elements) > 1 else ""
                
                # Изображение
                img_url = item.select_one('.sale-image')['src']
                
                games.append({
                    "name": name,
                    "url": store_url,
                    "install": install_url,
                    "type": promo_type,
                    "start": start_time,
                    "end": end_time,
                    "image": img_url
                })
            except Exception as e:
                print(f"Ошибка парсинга элемента: {e}")
                continue
        
        return games
    except Exception as e:
        print(f"Ошибка запроса к SteamDB: {e}")
        return []

def save_to_json(games):
    data = {
        "total_count": len(games),
        "free_list": games,
        "update_time": datetime.datetime.now(
            tz=pytz.timezone("Europe/Kiev")
        ).strftime('%Y-%m-%d %H:%M:%S'),
        "source": "steamdb"
    }
    
    with open("free_goods_detail.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    games = fetch_steamdb_free_games()
    save_to_json(games)
    print(f"Найдено {len(games)} бесплатных предложений. Данные сохранены в free_goods_detail.json")
