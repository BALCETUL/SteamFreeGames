from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import datetime
import time
import json
import pytz
import bs4
import logging
import threading
from typing import List, Tuple, Set
from urllib.parse import urljoin, urlparse
import random

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('steam_parser.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

API_URL_TEMPLATE = "https://store.steampowered.com/search/results/?query&start={pos}&count=100&infinite=1&specials=1"
THREAD_CNT = 4  # Уменьшили с 8 до 4 для стабильности

class SteamParser:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.free_games = []
        self.processed_ids = set()
        self.lock = threading.Lock()
        
    def fetch_steam_json_response(self, url: str, max_retries: int = 3) -> dict:
        """Получить JSON ответ от Steam API с повторными попытками"""
        for attempt in range(max_retries):
            try:
                # Небольшая задержка 
                if attempt > 0:
                    time.sleep(2)
                
                with self.session.get(url, timeout=10) as response:
                    response.raise_for_status()
                    data = response.json()
                    
                    # Проверяем что ответ валидный
                    if 'total_count' in data and 'results_html' in data:
                        return data
                    else:
                        logger.warning(f"Неполный ответ от Steam API на попытке {attempt + 1}")
                        
            except requests.exceptions.RequestException as e:
                logger.warning(f"Ошибка запроса на попытке {attempt + 1}: {e}")
                if attempt == max_retries - 1:
                    logger.error(f"Все попытки исчерпаны для URL: {url}")
                    
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Ошибка парсинга JSON на попытке {attempt + 1}: {e}")
                    
        return {}
    
    def extract_game_id(self, url: str) -> str:
        """Извлечь ID игры из URL для дедупликации"""
        try:
            if '/app/' in url:
                return url.split('/app/')[1].split('/')[0]
            elif '/sub/' in url:
                return 'sub_' + url.split('/sub/')[1].split('/')[0]
            elif '/bundle/' in url:
                return 'bundle_' + url.split('/bundle/')[1].split('/')[0]
            else:
                return url
        except:
            return url
    
    def parse_free_games_from_html(self, html: str) -> List[Tuple[str, str]]:
        """Парсить HTML для поиска бесплатных игр со 100% скидкой"""
        try:
            page_parser = bs4.BeautifulSoup(html, "html.parser")
            
            games = []
            
            #  ищем элементы со 100% скидкой
            discount_elements = page_parser.find_all(
                name="div",
                attrs={"class": "search_discount_block", "data-discount": "100"}
            )
            
            for div in discount_elements:
                try:
                    # Находим родительский элемент с информацией об игре
                    game_container = div.parent.parent.parent.parent
                    
                    # Извлекаем название игры
                    title_element = game_container.find(name="span", attrs={"class": "title"})
                    if not title_element:
                        continue
                        
                    title = title_element.get_text().strip()
                    url = game_container.get("href", "")
                    
                    if title and url:
                        games.append((title, url))
                        
                except Exception as e:
                    logger.warning(f"Ошибка при парсинге элемента игры: {e}")
                    continue
            
            # Дополнительно проверяем элементы с текстом "Free"
            # (это поможет найти DLC без дополнительных запросов)
            all_search_results = page_parser.find_all("a", class_="search_result_row")
            
            for result in all_search_results:
                try:
                    # Ищем цену
                    price_element = result.find("div", class_="search_price")
                    if price_element:
                        price_text = price_element.get_text().strip().lower()
                        if 'free' in price_text and '100%' in price_text:
                            title_element = result.find("span", class_="title")
                            if title_element:
                                title = title_element.get_text().strip()
                                url = result.get("href", "")
                                
                                if title and url:
                                    games.append((title, url))
                                    
                except Exception as e:
                    continue
                    
            return games
            
        except Exception as e:
            logger.error(f"Ошибка при парсинге HTML: {e}")
            return []
    
    def get_free_games_batch(self, start_pos: int) -> int:
        """Получить батч бесплатных игр начиная с позиции start_pos"""
        url = API_URL_TEMPLATE.format(pos=start_pos)
        logger.info(f"Обрабатываем позицию {start_pos}")
        
        response_data = self.fetch_steam_json_response(url)
        if not response_data:
            logger.error(f"Не удалось получить данные для позиции {start_pos}")
            return 0
            
        try:
            total_count = response_data.get("total_count", 0)
            html = response_data.get("results_html", "")
            
            if not html:
                logger.warning(f"Пустой HTML для позиции {start_pos}")
                return total_count
                
            games = self.parse_free_games_from_html(html)
            
            # Добавляем игры в общий список с проверкой дубликатов
            with self.lock:
                for title, url in games:
                    game_id = self.extract_game_id(url)
                    if game_id not in self.processed_ids:
                        self.processed_ids.add(game_id)
                        self.free_games.append((title, url))
                        logger.info(f"Найдена игра: {title}")
                        
            return total_count
            
        except Exception as e:
            logger.error(f"Ошибка при обработке батча {start_pos}: {e}")
            return 0
    
    def get_all_free_games(self) -> List[Tuple[str, str]]:
        """Получить все бесплатные игры со 100% скидкой"""
        logger.info("Начинаем поиск бесплатных игр в Steam")
        
        # Получаем общее количество результатов
        total_count = self.get_free_games_batch(0)
        if total_count == 0:
            logger.error("Не удалось получить общее количество игр")
            return []
            
        logger.info(f"Общее количество игр для проверки: {total_count}")
        
        # Создаем список позиций для обработки
        positions = list(range(100, total_count, 100))  # Начинаем с 100, так как 0 уже обработан
        
        # Обрабатываем остальные позиции в многопоточном режиме
        if positions:
            with ThreadPoolExecutor(max_workers=THREAD_CNT) as executor:
                future_to_pos = {
                    executor.submit(self.get_free_games_batch, pos): pos 
                    for pos in positions
                }
                
                for future in as_completed(future_to_pos):
                    pos = future_to_pos[future]
                    try:
                        future.result()
                        logger.info(f"Завершена обработка позиции {pos}")
                    except Exception as e:
                        logger.error(f"Ошибка при обработке позиции {pos}: {e}")
        
        logger.info(f"Найдено уникальных бесплатных игр: {len(self.free_games)}")
        return self.free_games
    
    def validate_results(self, games: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
        """Валидация результатов"""
        validated_games = []
        
        for title, url in games:
            # Базовая валидация
            if not title or not url:
                continue
                
            # Проверяем что URL корректный
            try:
                parsed = urlparse(url)
                if not parsed.scheme or not parsed.netloc:
                    continue
            except:
                continue
                
            # Проверяем что это действительно Steam URL
            if 'steampowered.com' not in url and 'store.steampowered.com' not in url:
                continue
                
            validated_games.append((title, url))
            
        return validated_games
    
    def save_results(self, games: List[Tuple[str, str]]):
        """Сохранить результаты в JSON файл"""
        try:
            # Валидируем результаты
            validated_games = self.validate_results(games)
            
            # Создаем финальную структуру данных 
            result_data = {
                "total_count": len(validated_games),
                "free_list": validated_games,
                "update_time": datetime.datetime.now(
                    tz=pytz.timezone("Europe/Kiev")
                ).strftime('%Y-%m-%d %H:%M:%S')
            }
            
            # Сохраняем в файл
            with open("free_goods_detail.json", "w", encoding='utf-8') as fp:
                json.dump(result_data, fp, ensure_ascii=False, indent=2)
                
            logger.info(f"Результаты сохранены: {len(validated_games)} игр")
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении результатов: {e}")
            raise

def main():
    """Основная функция"""
    try:
        parser = SteamParser()
        free_games = parser.get_all_free_games()
        parser.save_results(free_games)
        
        logger.info("Парсинг завершен успешно!")
        
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        raise

if __name__ == "__main__":
    main()
