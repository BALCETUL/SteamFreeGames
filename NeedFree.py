from concurrent.futures import ThreadPoolExecutor, wait, ALL_COMPLETED
import requests
import datetime
import queue
import time
import json
import pytz
import bs4

API_URL_TEMPLATE = "https://store.steampowered.com/search/results/?query&start={pos}&count=100&infinite=1"
THREAD_CNT = 8
free_list = queue.Queue()

def fetch_Steam_json_response(url):
    while True:
        try:
            with requests.get(url, timeout=5) as response:
                return response.json()
        except Exception:
            time.sleep(10)
            continue

def get_free_goods(start, append_list=False):
    global free_list
    retry_time = 3
    while retry_time >= 0:
        response_json = fetch_Steam_json_response(API_URL_TEMPLATE.format(pos=start))
        try:
            goods_count = response_json["total_count"]
            goods_html = response_json["results_html"]
            page_parser = bs4.BeautifulSoup(goods_html, "html.parser")
            full_discounts_div = page_parser.find_all(
                name="div",
                attrs={"class": "search_discount_block", "data-discount": "100"}
            )
            sub_free_list = [
                [
                    div.parent.parent.parent.parent
                       .find(name="span", attrs={"class": "title"})
                       .get_text(),
                    div.parent.parent.parent.parent.get("href"),
                ]
                for div in full_discounts_div
            ]
            if append_list:
                for sub_free in sub_free_list:
                    free_list.put(sub_free)
            return goods_count
        except Exception:
            retry_time -= 1
    return 0

def get_promo_dates(appid=None, subid=None, lang='ru'):
    """
    Вернёт (start_ts, end_ts) для акции Free To Keep или (None, None), 
    если промо нет.
    """
    if appid:
        url = f"https://store.steampowered.com/api/appdetails?appids={appid}&l={lang}"
        key = str(appid)
    else:
        url = f"https://store.steampowered.com/api/packagedetails?packageids={subid}&l={lang}"
        key = str(subid)
    for _ in range(3):
        try:
            resp = requests.get(url, timeout=5).json()
            data = resp.get(key, {}).get('data', {})
            promos = data.get('promotions', {}).get('promotional_events', [])
            for ev in promos:
                if ev.get('type') == 0:  # Free To Keep
                    sd = ev['start_date'].get('initial')
                    ed = ev['end_date'].get('initial')
                    return sd, ed
            return None, None
        except Exception:
            time.sleep(1)
    return None, None

if __name__ == "__main__":
    # Собираем список всех бесплатных товаров
    total_count = get_free_goods(0)
    threads = ThreadPoolExecutor(max_workers=THREAD_CNT)
    futures = [threads.submit(get_free_goods, idx, True)
               for idx in range(0, total_count, 100)]
    wait(futures, return_when=ALL_COMPLETED)

    # Убираем дубликаты
    final_free_list = []
    free_names = set()
    while not free_list.empty():
        name, url = free_list.get()
        if name not in free_names:
            free_names.add(name)
            final_free_list.append([name, url])

    # Получаем даты начала и окончания каждой раздачи
    detailed = []
    for name, link in final_free_list:
        if '/sub/' in link:
            subid = link.split('/sub/')[1].strip('/').split('/')[0]
            start_ts, end_ts = get_promo_dates(subid=subid)
        else:
            appid = link.split('/app/')[1].strip('/').split('/')[0]
            start_ts, end_ts = get_promo_dates(appid=appid)

        fmt = lambda ts: datetime.datetime.fromtimestamp(
            ts, tz=pytz.timezone("Europe/Kiev")
        ).strftime("%Y-%m-%d %H:%M:%S") if ts else None

        detailed.append({
            "name": name,
            "link": link,
            "started": fmt(start_ts),
            "expires": fmt(end_ts)
        })

    # Сохраняем результат
    with open("free_goods_detail.json", "w", encoding="utf-8") as fp:
        json.dump({
            "total_count": len(detailed),
            "free_list": detailed,
            "update_time": datetime.datetime.now(
                tz=pytz.timezone("Europe/Kiev")
            ).strftime('%Y-%m-%d %H:%M:%S')
        }, fp, ensure_ascii=False, indent=2)
