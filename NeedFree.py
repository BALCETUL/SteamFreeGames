from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import datetime
import time
import json
import pytz
import bs4
import logging
import threading
from typing import List, Tuple, Set, Dict, Optional
from urllib.parse import urljoin, urlparse, parse_qs
import random
import re
from dataclasses import dataclass, asdict
import hashlib

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

# Константы
API_URL_TEMPLATE = "https://store.steampowered.com/search/results/?query&start={pos}&count=100&infinite=1&specials=1"
BACKUP_API_URL = "https://store.steampowered.com/search/results/?query&start={pos}&count=50&infinite=1&specials=1"
THREAD_CNT = 6  # Уменьшили для большей стабильности
MAX_RETRIES = 5
DELAY_BETWEEN_REQUESTS = 1.5  # Увеличили задержку

@dataclass
class GameInfo:
    title: str
    url: str
    game_id: str
    price_info: str
    discount_percent: int
    content_type: str  # app, sub, bundle
    found_method: str  # какой метод нашел игру
    image_url: str = ""  # URL реальной обложки
    
    def to_tuple(self) -> Tuple[str, str, str]:
        return (self.title, self.url, self.image_url)

class SteamParser:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        
        self.free_games: Dict[str, GameInfo] = {}  # Используем словарь для дедупликации
        self.processed_urls: Set[str] = set()
        self.lock = threading.Lock()
        self.previous_results: Dict[str, GameInfo] = {}
        
        # Загружаем предыдущие результаты для сравнения
        self.load_previous_results()
        
    def load_previous_results(self):
        """Загружаем предыдущие результаты для сравнения"""
        try:
            with open('free_goods_detail.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                for item in data.get('free_list', []):
                    # Поддерживаем старый и новый форматы
                    if isinstance(item, list):
                        if len(item) >= 3:
                            title, url, image_url = item[0], item[1], item[2]
                        else:
                            title, url, image_url = item[0], item[1], ""
                    else:
                        # Старый формат - только название и URL
                        title, url, image_url = item, "", ""
                    
                    game_id = self.extract_game_id(url)
                    self.previous_results[game_id] = GameInfo(
                        title=title,
                        url=url,
                        game_id=game_id,
                        price_info="Previous result",
                        discount_percent=100,
                        content_type=self.get_content_type(url),
                        found_method="previous",
                        image_url=image_url
                    )
            logger.info(f"Загружено {len(self.previous_results)} предыдущих результатов")
        except FileNotFoundError:
            logger.info("Предыдущие результаты не найдены, начинаем с нуля")
        except Exception as e:
            logger.warning(f"Ошибка при загрузке предыдущих результатов: {e}")
    
    def get_content_type(self, url: str) -> str:
        """Определяем тип контента по URL"""
        if '/app/' in url:
            return 'app'
        elif '/sub/' in url:
            return 'sub'
        elif '/bundle/' in url:
            return 'bundle'
        return 'unknown'
    
    def extract_game_id(self, url: str) -> str:
        """Улучшенное извлечение ID игры из URL"""
        try:
            # Нормализуем URL
            url = url.strip()
            if not url.startswith('http'):
                url = 'https://store.steampowered.com' + url
            
            # Различные паттерны для извлечения ID
            patterns = [
                r'/app/(\d+)',
                r'/sub/(\d+)', 
                r'/bundle/(\d+)',
                r'[?&]appid=(\d+)',
                r'[?&]subid=(\d+)',
                r'[?&]bundleid=(\d+)'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, url)
                if match:
                    content_type = 'app' if 'app' in pattern else 'sub' if 'sub' in pattern else 'bundle'
                    return f"{content_type}_{match.group(1)}"
            
            # Если не удалось извлечь ID, используем хеш URL
            return hashlib.md5(url.encode()).hexdigest()[:16]
            
        except Exception as e:
            logger.warning(f"Ошибка извлечения ID из URL {url}: {e}")
            return hashlib.md5(url.encode()).hexdigest()[:16]
    
    def extract_image_url(self, game_container) -> str:
        """Извлекаем реальный URL обложки игры из HTML"""
        try:
            # Ищем изображение в контейнере игры
            img_element = game_container.find("img")
            if img_element:
                # Получаем src или data-src
                img_url = img_element.get("src") or img_element.get("data-src") or ""
                
                # Очищаем и нормализуем URL
                if img_url:
                    # Убираем параметры изменения размера, чтобы получить оригинал
                    img_url = re.sub(r'(\?.*$)', '', img_url)
                    
                    # Если URL относительный, делаем абсолютным
                    if img_url.startswith('//'):
                        img_url = 'https:' + img_url
                    elif img_url.startswith('/'):
                        img_url = 'https://store.steampowered.com' + img_url
                    
                    logger.debug(f"Найдена обложка: {img_url}")
                    return img_url
            
            # Если не нашли img, попробуем найти в стилях background-image
            style_elements = game_container.find_all(['div', 'span'], style=True)
            for element in style_elements:
                style = element.get('style', '')
                if 'background-image' in style:
                    match = re.search(r'url\(["\']?(.*?)["\']?\)', style)
                    if match:
                        img_url = match.group(1)
                        if img_url.startswith('//'):
                            img_url = 'https:' + img_url
                        elif img_url.startswith('/'):
                            img_url = 'https://store.steampowered.com' + img_url
                        logger.debug(f"Найдена обложка в стилях: {img_url}")
                        return img_url
            
        except Exception as e:
            logger.warning(f"Ошибка при извлечении URL изображения: {e}")
        
        return ""
    
    def fetch_steam_json_response(self, url: str, max_retries: int = MAX_RETRIES) -> dict:
        """Получить JSON ответ от Steam API с улучшенными повторными попытками"""
        for attempt in range(max_retries):
            try:
                # Прогрессивная задержка
                if attempt > 0:
                    delay = DELAY_BETWEEN_REQUESTS * (2 ** attempt) + random.uniform(0, 1)
                    time.sleep(delay)
                    logger.info(f"Повторная попытка {attempt + 1}/{max_retries} для {url}")
                
                response = self.session.get(url, timeout=15)
                response.raise_for_status()
                
                data = response.json()
                
                # Проверяем что ответ валидный
                if 'total_count' in data and 'results_html' in data:
                    logger.debug(f"Получен валидный ответ: {data['total_count']} результатов")
                    return data
                else:
                    logger.warning(f"Неполный ответ от Steam API на попытке {attempt + 1}")
                    
            except requests.exceptions.RequestException as e:
                logger.warning(f"Ошибка запроса на попытке {attempt + 1}: {e}")
                if attempt == max_retries - 1:
                    logger.error(f"Все попытки исчерпаны для URL: {url}")
                    # Пробуем резервный URL
                    if API_URL_TEMPLATE in url:
                        backup_url = url.replace(API_URL_TEMPLATE.split('?')[0], BACKUP_API_URL.split('?')[0])
                        logger.info(f"Пробуем резервный URL: {backup_url}")
                        return self.fetch_steam_json_response(backup_url, 3)
                    
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Ошибка парсинга JSON на попытке {attempt + 1}: {e}")
                    
        return {}
    
    def parse_free_games_from_html(self, html: str, position: int = 0) -> List[GameInfo]:
        """Улучшенный парсинг HTML с множественными методами поиска и извлечением обложек"""
        games = []
        
        try:
            soup = bs4.BeautifulSoup(html, "html.parser")
            
            # Метод 1: Поиск по data-discount="100"
            games.extend(self.find_games_by_discount_attribute(soup, position))
            
            # Метод 2: Поиск по тексту "Free" в цене
            games.extend(self.find_games_by_free_text(soup, position))
            
            # Метод 3: Поиск по -100% в тексте
            games.extend(self.find_games_by_discount_text(soup, position))
            
            # Метод 4: Поиск по цене 0.00
            games.extend(self.find_games_by_zero_price(soup, position))
            
            # Дедупликация внутри одного HTML
            unique_games = {}
            for game in games:
                if game.game_id not in unique_games:
                    unique_games[game.game_id] = game
                else:
                    # Если дубликат, сохраняем тот, который найден более надежным методом
                    existing = unique_games[game.game_id]
                    if self.get_method_priority(game.found_method) > self.get_method_priority(existing.found_method):
                        unique_games[game.game_id] = game
            
            result = list(unique_games.values())
            logger.info(f"Позиция {position}: найдено {len(result)} уникальных бесплатных игр")
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при парсинге HTML на позиции {position}: {e}")
            return []
    
    def get_method_priority(self, method: str) -> int:
        """Приоритет методов поиска (чем выше число, тем надежнее метод)"""
        priorities = {
            'discount_attribute': 4,
            'zero_price': 3,
            'discount_text': 2,
            'free_text': 1
        }
        return priorities.get(method, 0)
    
    def find_games_by_discount_attribute(self, soup: bs4.BeautifulSoup, position: int) -> List[GameInfo]:
        """Метод 1: Поиск по data-discount="100" """
        games = []
        
        discount_elements = soup.find_all("div", {"class": "search_discount_block", "data-discount": "100"})
        logger.debug(f"Позиция {position}: найдено {len(discount_elements)} элементов с data-discount='100'")
        
        for div in discount_elements:
            try:
                # Поднимаемся по DOM дереву чтобы найти контейнер с игрой
                game_container = div.find_parent("a", class_="search_result_row")
                if not game_container:
                    # Альтернативный поиск
                    current = div.parent
                    for _ in range(6):  # Поиск до 6 уровней вверх
                        if current and current.name == 'a' and 'search_result_row' in current.get('class', []):
                            game_container = current
                            break
                        current = current.parent if current else None
                
                if not game_container:
                    continue
                
                title_element = game_container.find("span", class_="title")
                if not title_element:
                    continue
                    
                title = title_element.get_text().strip()
                url = game_container.get("href", "")
                image_url = self.extract_image_url(game_container)
                
                if title and url:
                    game_id = self.extract_game_id(url)
                    game = GameInfo(
                        title=title,
                        url=url,
                        game_id=game_id,
                        price_info="100% discount",
                        discount_percent=100,
                        content_type=self.get_content_type(url),
                        found_method="discount_attribute",
                        image_url=image_url
                    )
                    games.append(game)
                    logger.debug(f"Найдена игра (метод 1): {title}")
                    
            except Exception as e:
                logger.warning(f"Ошибка при обработке элемента скидки: {e}")
                continue
        
        return games
    
    def find_games_by_free_text(self, soup: bs4.BeautifulSoup, position: int) -> List[GameInfo]:
        """Метод 2: Поиск по тексту 'Free' в цене"""
        games = []
        
        # Ищем все элементы с ценой
        price_elements = soup.find_all("div", class_="search_price")
        
        for price_element in price_elements:
            try:
                price_text = price_element.get_text().strip().lower()
                
                # Проверяем различные варианты "бесплатно"
                free_indicators = ['free', 'бесплатно', 'free to play', 'free!', '100%']
                
                if any(indicator in price_text for indicator in free_indicators):
                    # Найдем контейнер с игрой
                    game_container = price_element.find_parent("a", class_="search_result_row")
                    if not game_container:
                        continue
                    
                    title_element = game_container.find("span", class_="title")
                    if not title_element:
                        continue
                        
                    title = title_element.get_text().strip()
                    url = game_container.get("href", "")
                    image_url = self.extract_image_url(game_container)
                    
                    if title and url:
                        game_id = self.extract_game_id(url)
                        game = GameInfo(
                            title=title,
                            url=url,
                            game_id=game_id,
                            price_info=price_text,
                            discount_percent=100,
                            content_type=self.get_content_type(url),
                            found_method="free_text",
                            image_url=image_url
                        )
                        games.append(game)
                        logger.debug(f"Найдена игра (метод 2): {title} - {price_text}")
                        
            except Exception as e:
                logger.warning(f"Ошибка при поиске по тексту Free: {e}")
                continue
        
        return games
    
    def find_games_by_discount_text(self, soup: bs4.BeautifulSoup, position: int) -> List[GameInfo]:
        """Метод 3: Поиск по тексту -100% в скидке"""
        games = []
        
        # Ищем все элементы со скидкой
        discount_elements = soup.find_all("div", class_="search_discount")
        
        for discount_element in discount_elements:
            try:
                discount_text = discount_element.get_text().strip()
                
                # Проверяем на 100% скидку
                if '-100%' in discount_text or '100%' in discount_text:
                    # Найдем контейнер с игрой
                    game_container = discount_element.find_parent("a", class_="search_result_row")
                    if not game_container:
                        continue
                    
                    title_element = game_container.find("span", class_="title")
                    if not title_element:
                        continue
                        
                    title = title_element.get_text().strip()
                    url = game_container.get("href", "")
                    image_url = self.extract_image_url(game_container)
                    
                    if title and url:
                        game_id = self.extract_game_id(url)
                        game = GameInfo(
                            title=title,
                            url=url,
                            game_id=game_id,
                            price_info=discount_text,
                            discount_percent=100,
                            content_type=self.get_content_type(url),
                            found_method="discount_text",
                            image_url=image_url
                        )
                        games.append(game)
                        logger.debug(f"Найдена игра (метод 3): {title} - {discount_text}")
                        
            except Exception as e:
                logger.warning(f"Ошибка при поиске по тексту скидки: {e}")
                continue
        
        return games
    
    def find_games_by_zero_price(self, soup: bs4.BeautifulSoup, position: int) -> List[GameInfo]:
        """Метод 4: Поиск по цене 0.00 или аналогичным"""
        games = []
        
        # Ищем все элементы с ценой
        price_elements = soup.find_all("div", class_="search_price")
        
        for price_element in price_elements:
            try:
                price_text = price_element.get_text().strip()
                
                # Проверяем на нулевую цену
                zero_price_patterns = [
                    r'0[.,]00',
                    r'₽\s*0[.,]00',
                    r'\$\s*0[.,]00',
                    r'€\s*0[.,]00',
                    r'Free',
                    r'Бесплатно'
                ]
                
                if any(re.search(pattern, price_text, re.IGNORECASE) for pattern in zero_price_patterns):
                    # Найдем контейнер с игрой
                    game_container = price_element.find_parent("a", class_="search_result_row")
                    if not game_container:
                        continue
                    
                    title_element = game_container.find("span", class_="title")
                    if not title_element:
                        continue
                        
                    title = title_element.get_text().strip()
                    url = game_container.get("href", "")
                    image_url = self.extract_image_url(game_container)
                    
                    if title and url:
                        game_id = self.extract_game_id(url)
                        game = GameInfo(
                            title=title,
                            url=url,
                            game_id=game_id,
                            price_info=price_text,
                            discount_percent=100,
                            content_type=self.get_content_type(url),
                            found_method="zero_price",
                            image_url=image_url
                        )
                        games.append(game)
                        logger.debug(f"Найдена игра (метод 4): {title} - {price_text}")
                        
            except Exception as e:
                logger.warning(f"Ошибка при поиске по нулевой цене: {e}")
                continue
        
        return games
    
    def get_free_games_batch(self, start_pos: int) -> int:
        """Получить батч бесплатных игр с улучшенной обработкой"""
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
                
            games = self.parse_free_games_from_html(html, start_pos)
            
            # Добавляем игры в общий список с проверкой дубликатов
            with self.lock:
                for game in games:
                    if game.game_id not in self.free_games:
                        self.free_games[game.game_id] = game
                        logger.info(f"Новая игра: {game.title} ({game.found_method})")
                    else:
                        # Если игра уже есть, обновляем информацию если новый метод надежнее
                        existing = self.free_games[game.game_id]
                        if self.get_method_priority(game.found_method) > self.get_method_priority(existing.found_method):
                            self.free_games[game.game_id] = game
                            logger.debug(f"Обновлена игра: {game.title} (метод: {game.found_method})")
                        
            return total_count
            
        except Exception as e:
            logger.error(f"Ошибка при обработке батча {start_pos}: {e}")
            return 0
    
    def verify_previous_games(self):
        """Проверяем игры из предыдущих результатов"""
        logger.info("Проверяем игры из предыдущих результатов...")
        
        for game_id, game in self.previous_results.items():
            if game_id not in self.free_games:
                # Проверяем, доступна ли игра еще
                if self.verify_game_still_free(game.url):
                    self.free_games[game_id] = game
                    logger.info(f"Восстановлена игра из предыдущих результатов: {game.title}")
                else:
                    logger.info(f"Игра больше не бесплатна: {game.title}")
    
    def verify_game_still_free(self, url: str) -> bool:
        """Проверяем, доступна ли игра еще бесплатно"""
        try:
            # Простая проверка - если игра была в предыдущих результатах недавно,
            # вероятно она еще доступна
            # Для более точной проверки можно делать отдельный запрос к странице игры
            return True  # Пока что считаем что игра доступна
        except:
            return False
    
    def get_all_free_games(self) -> List[Tuple[str, str, str]]:
        """Получить все бесплатные игры с улучшенной логикой"""
        logger.info("Начинаем поиск бесплатных игр в Steam")
        
        # Получаем общее количество результатов
        total_count = self.get_free_games_batch(0)
        if total_count == 0:
            logger.error("Не удалось получить общее количество игр")
            return []
            
        logger.info(f"Общее количество игр для проверки: {total_count}")
        
        # Создаем список позиций для обработки
        positions = list(range(100, min(total_count, 2000), 100))  # Ограничиваем до 2000 для экономии лимитов
        
        # Обрабатываем остальные позиции
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
        
        # Проверяем предыдущие результаты
        self.verify_previous_games()
        
        # Финальная проверка и логирование
        final_games = [game.to_tuple() for game in self.free_games.values()]
        logger.info(f"Найдено уникальных бесплатных игр: {len(final_games)}")
        
        # Простая статистика в логах
        method_stats = {}
        type_stats = {}
        images_found = 0
        for game in self.free_games.values():
            method_stats[game.found_method] = method_stats.get(game.found_method, 0) + 1
            type_stats[game.content_type] = type_stats.get(game.content_type, 0) + 1
            if game.image_url:
                images_found += 1
        
        logger.info(f"Статистика по методам поиска: {method_stats}")
        logger.info(f"Статистика по типам контента: {type_stats}")
        logger.info(f"Найдено обложек: {images_found}/{len(final_games)}")
        
        return final_games
    
    def validate_results(self, games: List[Tuple[str, str, str]]) -> List[Tuple[str, str, str]]:
        """Расширенная валидация результатов"""
        validated_games = []
        
        for item in games:
            try:
                title, url, image_url = item
                
                # Базовая валидация
                if not title or not url:
                    logger.warning(f"Пропущена игра с пустым названием или URL: {title}, {url}")
                    continue
                    
                # Проверяем что URL корректный
                try:
                    parsed = urlparse(url)
                    if not parsed.scheme or not parsed.netloc:
                        logger.warning(f"Некорректный URL: {url}")
                        continue
                except Exception as e:
                    logger.warning(f"Ошибка парсинга URL {url}: {e}")
                    continue
                    
                # Проверяем что это действительно Steam URL
                if not any(domain in url for domain in ['steampowered.com', 'store.steampowered.com']):
                    logger.warning(f"Не Steam URL: {url}")
                    continue
                
                # Проверяем длину названия
                if len(title) > 200:
                    logger.warning(f"Слишком длинное название игры: {title[:50]}...")
                    title = title[:200]
                
                # Очищаем название от лишних символов
                title = re.sub(r'\s+', ' ', title).strip()
                
                # Валидируем URL изображения
                if image_url and not image_url.startswith('http'):
                    logger.warning(f"Некорректный URL изображения: {image_url}")
                    image_url = ""
                    
                validated_games.append((title, url, image_url))
                
            except (ValueError, IndexError) as e:
                logger.warning(f"Ошибка при обработке элемента {item}: {e}")
                continue
                
        logger.info(f"Валидировано {len(validated_games)} из {len(games)} игр")
        return validated_games
    
    def save_results(self, games: List[Tuple[str, str, str]]):
        """Сохранить результаты с резервным копированием"""
        try:
            # Создаем резервную копию предыдущих результатов
            try:
                with open("free_goods_detail.json", "r", encoding='utf-8') as f:
                    with open("free_goods_detail_backup.json", "w", encoding='utf-8') as backup:
                        backup.write(f.read())
                logger.info("Создана резервная копия предыдущих результатов")
            except FileNotFoundError:
                logger.info("Предыдущих результатов нет, резервная копия не создана")
            
            # Валидируем результаты
            validated_games = self.validate_results(games)
            
            # Создаем финальную структуру данных 
            result_data = {
                "total_count": len(validated_games),
                "free_list": validated_games,
                "update_time": datetime.datetime.now(
                    tz=pytz.timezone("Europe/Kiev")
                ).strftime('%Y-%m-%d %H:%M:%S'),
                "parser_version": "3.0_with_images",
                "methods_used": ["discount_attribute", "free_text", "discount_text", "zero_price"],
                "verification_enabled": True,
                "images_included": True
            }
            
            # Сохраняем в файл
            with open("free_goods_detail.json", "w", encoding='utf-8') as fp:
                json.dump(result_data, fp, ensure_ascii=False, indent=2)
                
            logger.info(f"Результаты сохранены: {len(validated_games)} игр с обложками")
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении результатов: {e}")
            # Пытаемся восстановить из резервной копии
            try:
                with open("free_goods_detail_backup.json", "r", encoding='utf-8') as backup:
                    with open("free_goods_detail.json", "w", encoding='utf-8') as f:
                        f.write(backup.read())
                logger.info("Восстановлены результаты из резервной копии")
            except:
                logger.error("Не удалось восстановить результаты")
            raise

def main():
    """Основная функция с улучшенной обработкой ошибок"""
    start_time = time.time()
    
    try:
        logger.info("="*50)
        logger.info("ЗАПУСК ПАРСЕРА STEAM С ОБЛОЖКАМИ")
        logger.info("="*50)
        
        parser = SteamParser()
        free_games = parser.get_all_free_games()
        
        if not free_games:
            logger.error("Не найдено ни одной бесплатной игры!")
            return False
            
        parser.save_results(free_games)
        
        end_time = time.time()
        elapsed_time = end_time - start_time
        
        logger.info("="*50)
        logger.info(f"ПАРСИНГ ЗАВЕРШЕН УСПЕШНО!")
        logger.info(f"Время выполнения: {elapsed_time:.2f} секунд")
        logger.info(f"Найдено игр: {len(free_games)}")
        logger.info("="*50)
        
        return True
        
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        logger.exception("Полная трассировка ошибки:")
        return False

if __name__ == "__main__":
    success = main()
    if not success:
        exit(1)
