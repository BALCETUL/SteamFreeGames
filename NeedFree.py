from concurrent.futures import ThreadPoolExecutor, wait, ALL_COMPLETED
import requests
import bs4
import queue
import time
import json
import datetime
import pytz

API_SEARCH = "https://store.steampowered.com/search/results/?query&start={pos}&count=100&infinite=1"
THREADS = 8
Q = queue.Queue()

def fetch_json(url, retries=3):
    for _ in range(retries):
        try:
            return requests.get(url, timeout=5).json()
        except:
            time.sleep(1)
    return {}

def get_free_goods_block(start, enqueue=False):
    resp = fetch_json(API_SEARCH.format(pos=start))
    html = resp.get("results_html", "")
    soup = bs4.BeautifulSoup(html, "html.parser")
    blocks = soup.find_all("a", class_="search_result_row", attrs={"data-discount":"100"})
    items = []
    for b in blocks:
        name = b.find("span", class_="title").text.strip()
        appid = b.get("data-ds-appid")
        subid = b.get("data-ds-packageid") or b.get("data-subid")
        link = b.get("href")
        items.append((name, appid, subid, link))
    if enqueue:
        for it in items:
            Q.put(it)
    return resp.get("total_count", 0)

def get_promos(appid=None, subid=None, lang="ru"):
    if subid:
        url = f"https://store.steampowered.com/api/packagedetails?packageids={subid}&l={lang}"
        key = str(subid)
    else:
        url = f"https://store.steampowered.com/api/appdetails?appids={appid}&l={lang}"
        key = str(appid)
    data = fetch_json(url).get(key, {}).get("data", {})
    events = data.get("promotions", {}).get("promotional_events", [])
    out = {
        "started": None,
        "expires": None,
        "weekend_start": None,
        "weekend_end": None,
        "promo_type": None
    }
    for ev in events:
        t = ev.get("type")
        sd = ev["start_date"].get("initial")
        ed = ev["end_date"].get("initial")
        if t == 0:  # Free to Keep
            out["started"], out["expires"], out["promo_type"] = sd, ed, 0
        elif t == 3:  # Free Weekend
            out["weekend_start"], out["weekend_end"], out["promo_type"] = sd, ed, 3
    return out

if __name__ == "__main__":
    total = get_free_goods_block(0)
    with ThreadPoolExecutor(THREADS) as pool:
        futures = [
            pool.submit(get_free_goods_block, i, True)
            for i in range(0, total, 100)
        ]
        wait(futures, return_when=ALL_COMPLETED)

    seen = set()
    detailed = []
    while not Q.empty():
        name, appid, subid, link = Q.get()
        key = subid or appid
        if key in seen:
            continue
        seen.add(key)
        promos = get_promos(appid=appid, subid=subid)
        fmt = lambda ts: datetime.datetime.fromtimestamp(
            ts, tz=pytz.timezone("Europe/Kiev")
        ).strftime("%Y-%m-%d %H:%M:%S") if ts else None

        detailed.append({
            "name": name,
            "link": link,
            "promo_type": promos["promo_type"],
            "started": fmt(promos["started"]),
            "expires": fmt(promos["expires"]),
            "weekend_start": fmt(promos["weekend_start"]),
            "weekend_end": fmt(promos["weekend_end"])
        })

    with open("free_goods_detail.json", "w", encoding="utf-8") as f:
        json.dump({
            "total_count": len(detailed),
            "free_list": detailed,
            "update_time": datetime.datetime.now(
                tz=pytz.timezone("Europe/Kiev")
            ).strftime("%Y-%m-%d %H:%M:%S")
        }, f, ensure_ascii=False, indent=2)
