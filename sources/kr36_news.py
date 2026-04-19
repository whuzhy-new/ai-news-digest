import csv
import json
import base64
import time
import argparse
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen

API_URL = "https://gateway.36kr.com/api/mis/nav/ifm/subNav/flow"
DEFAULT_CHANNEL = "AI"
DEFAULT_PAGE_SIZE = 30
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"

CST = timezone(timedelta(hours=8))

INIT_CALLBACK = base64.b64encode(json.dumps({
    "firstId": 99999999,
    "lastId": 99999999,
    "firstCreateTime": 9999999999999,
    "lastCreateTime": 9999999999999
}).encode()).decode()


def fetch_page(channel=DEFAULT_CHANNEL, page_size=DEFAULT_PAGE_SIZE, page_callback=INIT_CALLBACK, page_event=1):
    timestamp = int(time.time() * 1000)
    body = json.dumps({
        "partner_id": "web",
        "timestamp": timestamp,
        "param": {
            "subnavType": 1,
            "subnavNick": channel,
            "pageSize": page_size,
            "pageEvent": page_event,
            "pageCallback": page_callback,
            "siteId": 1,
            "platformId": 2
        }
    }).encode("utf-8")

    req = Request(API_URL, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Origin", "https://36kr.com")
    req.add_header("Referer", "https://36kr.com/")
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def extract_article(item):
    tm = item.get("templateMaterial", {})
    item_id = tm.get("itemId", "")
    url = f"https://36kr.com/p/{item_id}" if item_id else ""
    headline = tm.get("widgetTitle", "")
    abstract = tm.get("summary", "")
    img_url = tm.get("widgetImage", "")

    pub_ts = tm.get("publishTime")
    publish_time = ""
    if pub_ts:
        dt = datetime.fromtimestamp(pub_ts / 1000, tz=timezone.utc)
        publish_time = dt.astimezone(CST).strftime("%Y-%m-%d %H:%M:%S")

    return {
        "id": item_id,
        "url": url,
        "headline": headline,
        "abstract": abstract,
        "img_url": img_url,
        "publish_time": publish_time
    }


def crawl_all_pages(max_pages=1, page_size=DEFAULT_PAGE_SIZE, channel=DEFAULT_CHANNEL, delay=1.0):
    all_articles = []
    page_callback = INIT_CALLBACK

    for page_num in range(1, max_pages + 1):
        print(f"[Page {page_num}] 请求中...")
        try:
            data = fetch_page(channel, page_size, page_callback, page_event=1)
        except Exception as e:
            print(f"[Page {page_num}] 请求失败: {e}")
            break

        if data.get("code") != 0:
            print(f"[Page {page_num}] API 错误: {data.get('msg', 'unknown')}")
            break

        items = data.get("data", {}).get("itemList", [])
        page_callback = data.get("data", {}).get("pageCallback", "")
        has_next = data.get("data", {}).get("hasNextPage", 0)

        if not items:
            print(f"[Page {page_num}] 无数据，停止翻页")
            break

        for item in items:
            all_articles.append(extract_article(item))

        print(f"[Page {page_num}] 获取 {len(items)} 篇 | 累计 {len(all_articles)} 篇 | hasNextPage={has_next}")

        if not has_next:
            print("已到最后一页，停止翻页")
            break

        if delay > 0:
            time.sleep(delay)

    return all_articles


def export_csv(articles, filepath="36kr_news.csv"):
    fieldnames = ["id", "url", "headline", "abstract", "img_url", "publish_time"]
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(articles)
    print(f"\n已导出 {len(articles)} 条新闻到 {filepath}")


def main():
    parser = argparse.ArgumentParser(description="36氪新闻爬取工具")
    parser.add_argument("--max-pages", type=int, default=1, help="最大翻页数 (默认: 1)")
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE, help="每页条数 (默认: 30)")
    parser.add_argument("--channel", type=str, default=DEFAULT_CHANNEL, help="频道名称 (默认: AI)")
    parser.add_argument("--delay", type=float, default=1.0, help="翻页间隔秒数 (默认: 1.0)")
    parser.add_argument("--output", type=str, default="36kr_news.csv", help="输出 CSV 文件名 (默认: 36kr_news.csv)")
    args = parser.parse_args()

    print("=" * 60)
    print("36氪新闻爬取工具")
    print("=" * 60)
    print(f"  频道: {args.channel}")
    print(f"  最大页数: {args.max_pages}")
    print(f"  每页条数: {args.page_size}")
    print(f"  翻页间隔: {args.delay}s")
    print(f"  输出文件: {args.output}")
    print()

    articles = crawl_all_pages(
        max_pages=args.max_pages,
        page_size=args.page_size,
        channel=args.channel,
        delay=args.delay
    )

    if articles:
        export_csv(articles, args.output)
        print(f"\n前3条预览:")
        for i, a in enumerate(articles[:3], 1):
            print(f"  {i}. [{a['publish_time']}] {a['headline'][:60]}")
    else:
        print("未获取到任何新闻数据")


if __name__ == "__main__":
    main()
