import requests
from bs4 import BeautifulSoup
import json
import datetime
import pytz

def fetch_steamdb_free_games():
    """Парсит бесплатные игры с SteamDB"""
    url = "https://steamdb.info/upcoming/free/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Referer": "https://steamdb.info/"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        games = []
        for item in soup.select('.panel-sale'):
            try:
                # Основная информация
                name = item.select_one('.panel-sale-name b').text.strip()
                store_url = item.select_one('.app-history-type a[href*="store.steampowered.com"]')['href']
                
                # Определяем appid/subid
                appid = item.get('data-appid')
                install_url = f'steam://install/{appid}' if appid else None
                
                # Тип предложения
                promo_type = "Free to Keep"
                if item.select_one('.cat-play-for-free'):
                    promo_type = "Play For Free"
                
                # Время действия
                time_elements = item.select('relative-time')
                start_time = time_elements[0]['datetime'] if time_elements else ""
                end_time = time_elements[1]['datetime'] if len(time_elements) > 1 else ""
                
                # Изображение (используем прямое URL из SteamDB)
                img_tag = item.select_one('.sale-image')
                img_url = img_tag['src'] if img_tag else ""
                
                games.append({
                    "name": name,
                    "url": store_url,
                    "install": install_url,
                    "type": promo_type,
                    "start": start_time,
                    "end": end_time,
                    "image": img_url,
                    "appid": appid
                })
            except Exception as e:
                print(f"[Ошибка] Не удалось распарсить элемент: {str(e)}")
                continue
        
        return games
    except requests.exceptions.RequestException as e:
        print(f"[Ошибка] Запрос к SteamDB не удался: {str(e)}")
        return []
    except Exception as e:
        print(f"[Ошибка] Неожиданная ошибка: {str(e)}")
        return []

def save_to_json(data, filename="free_goods_detail.json"):
    """Сохраняет данные в JSON файл"""
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Данные успешно сохранены в {filename}")
    except Exception as e:
        print(f"[Ошибка] Не удалось сохранить файл: {str(e)}")

if __name__ == "__main__":
    print("Начинаем парсинг SteamDB...")
    games = fetch_steamdb_free_games()
    
    result = {
        "total_count": len(games),
        "free_list": games,
        "update_time": datetime.datetime.now(tz=pytz.timezone("Europe/Kiev")).strftime('%Y-%m-%d %H:%M:%S'),
        "source": "steamdb"
    }
    
    save_to_json(result)
    print(f"Парсинг завершен. Найдено {len(games)} предложений.")
