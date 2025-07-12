from concurrent.futures import ThreadPoolExecutor, wait, ALL_COMPLETED
import traceback
import requests
import datetime
import queue
import time
import json
import pytz
import bs4
import re


API_URL_TEMPLATE = "https://store.steampowered.com/search/results/?query&start={pos}&count=100&specials=1&infinite=1"
THREAD_CNT = 8

free_list = queue.Queue()


def fetch_Steam_json_response(url):
    ''' Fetch json response from Steam API
    URL:            Steam WebAPI url

    return:         json content
    '''
    while True:
        try:
            with requests.get(url, timeout = 5) as response:
                ret_json = response.json()
            return ret_json
        except Exception as e:
            print(e)
            time.sleep(10)
            continue

def get_free_goods(start, append_list = False):
    ''' Extract discount goods list in a list of 100 products
    start:          start page index
    append_list:    if to append new found free goods to final list

    return:         goods_count
    '''

    global free_list
    retry_time = 3

    while retry_time >= 0:
        response_json = fetch_Steam_json_response(API_URL_TEMPLATE.format(pos = start))
        try:
            goods_count = response_json["total_count"]
            goods_html = response_json["results_html"]
            page_parser = bs4.BeautifulSoup(goods_html, "html.parser")
            full_discounts_div = page_parser.find_all(name = "div", attrs = {"class":"search_discount_block"})
            sub_free_list = [
                [
                    div.parent.parent.parent.parent.find(name="div", attrs={"class": "search_discount_block"}).get("data-discount"),  # discount
                    div.parent.parent.parent.parent.find(name="div", attrs={"class": "discount_original_price"}),  # full price
                    div.parent.parent.parent.parent.find(name="div", attrs={"class": "discount_final_price"}).get_text(),  # price with discount
                    div.parent.parent.parent.parent.find(name="span", attrs={"class": "title"}).get_text(),  # title
                    div.parent.parent.parent.parent.get("href"),  # link
                    div.parent.parent.parent.parent.find_all("div")[0].find("img").get("src"),  # image
                    div.parent.parent.parent.parent.get("data-ds-tagids"),  # tags
                    div.parent.parent.parent.parent.get("data-ds-bundleid"),  # is_bundle
                    div.parent.parent.parent.parent.find(name="span", attrs={"class": "music"}),  # is_soundtrack
                    div.parent.parent.parent.parent.find(name="span", attrs={"class": "win"}),  # for win
                    div.parent.parent.parent.parent.find(name="span", attrs={"class": "mac"}),  # for mac
                    div.parent.parent.parent.parent.find(name="span", attrs={"class": "linux"}),  # for linux
                    div.parent.parent.parent.parent.find(name="span", attrs={"class": "vr_supported"}),  # for vr_supported
                    div.parent.parent.parent.parent.find(name="div", attrs={"class": "search_released"}),  # release
                    div.parent.parent.parent.parent.find(name="span", attrs={"class": "search_review_summary"})  # reviews
                ] for div in full_discounts_div
            ]

            counter = 0
            if append_list:
                for sub_free in sub_free_list:
                    if sub_free[0] and sub_free[0] != '0':
                        if sub_free[1]:
                            sub_free[1] = sub_free[1].get_text()
                        if sub_free[13]:
                            sub_free[13] = sub_free[13].get_text()
                        else:
                            sub_free[13] = ''
                        if sub_free[14]:
                            sub_free[14] = sub_free[14].get("data-tooltip-html")
                        else:
                            sub_free[14] = r'None<br>0% of the 0'
                        counter += 1
                        sub_free[0] = int(sub_free[0])
                        free_list.put(sub_free)

            return goods_count
        except Exception as e:
            print("get_free_goods: error on start = %d, remain retry %d time(s)" % (start, retry_time))
            print(e)
            print(traceback.format_exc())
            retry_time -= 1
    print("get_free_goods: error on start = %d, throw" % (start))

    return 0

# Get total count of free goods
tryget_first_page = get_free_goods(0)
total_count = tryget_first_page

# Multi-thread crawling
threads = ThreadPoolExecutor(max_workers = THREAD_CNT)
futures = [threads.submit(get_free_goods, index, True) for index in range(0, total_count, 100)]

wait(futures, return_when=ALL_COMPLETED)

# Process free list
final_free_list = []
free_ids = set()
while not free_list.empty():
    free_item = free_list.get()

    game_link = free_item[4]

    game_id = re.search(r'.com\/[a-z]+\/(\d+)\/', game_link)
    if game_id is None:
        continue

    game_id = int(game_id.group(1))
    if game_id in free_ids:
        continue

    game_tags = free_item[6]
    free_item[6] = json.loads(game_tags or '[]')

    is_bundle = free_item[7]
    free_item[7] = bool(is_bundle)

    is_soundtrack = free_item[8]
    free_item[8] = bool(is_soundtrack)

    for_win = free_item[9]
    free_item[9] = bool(for_win)

    for_mac = free_item[10]
    free_item[10] = bool(for_mac)

    for_linux = free_item[11]
    free_item[11] = bool(for_linux)

    for_vr = free_item[12]
    free_item[12] = bool(for_vr)

    release = free_item[13]
    free_item[13] = release.strip() or ''

    reviews = free_item[14]
    if reviews is None:
        reviews = r'None<br>0% of the 0'
    reviews = re.search(r'^([a-zA-Z ]+)\<br\>(\d{1,3})% of the ([\d,]+)', reviews)
    if reviews is None:
        review, percent, users = 'None', '0', '0'
    else:
        review, percent, users = reviews.groups()
    free_item[14] = [review, int(percent), int(users.replace(',' ,''))]

    free_ids.add(game_id)
    final_free_list.append(free_item)

final_free_list = sorted_data = sorted(final_free_list, key=lambda x: (-x[0], x[3]))

with open("free_goods_detail.json", "w", encoding="utf-8") as fp:
    json.dump({
        "total_count": len(final_free_list),
        "free_list": final_free_list,
        "update_time": datetime.datetime.now(tz=pytz.timezone("Europe/Moscow")).strftime('%Y-%m-%d %H:%M:%S')
    }, fp)
