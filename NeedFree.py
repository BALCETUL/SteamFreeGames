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
                attrs={"class":"search_discount_block", "data-discount":"100"}
            )
            sub_free_list = [
                [
                    div.parent.parent.parent.parent
                       .find(name="span", attrs={"class":"title"})
                       .get_text(),
                    div.parent.parent.parent.parent.get("href"),
                ]
                for div in full_discounts_div
            ]
            if append_list:
                for sub_free in sub_free_list:
                    free_list.put(sub_free)
            return goods_count
        except Exception as e:
            retry_time -= 1

    return 0

if __name__ == "__main__":
    total_count = get_free_goods(0)
    threads = ThreadPoolExecutor(max_workers=THREAD_CNT)
    futures = [threads.submit(get_free_goods, idx, True)
               for idx in range(0, total_count, 100)]
    wait(futures, return_when=ALL_COMPLETED)

    final_free_list = []
    free_names = set()
    while not free_list.empty():
        name, url = free_list.get()
        if name not in free_names:
            free_names.add(name)
            final_free_list.append([name, url])

    with open("free_goods_detail.json", "w") as fp:
        json.dump({
            "total_count": len(final_free_list),
            "free_list": final_free_list,
            "update_time": datetime.datetime.now(
                tz=pytz.timezone("Europe/Kiev")
            ).strftime('%Y-%m-%d %H:%M:%S')
        }, fp)
