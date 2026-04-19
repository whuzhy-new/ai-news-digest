import csv
import json
import re
import time
import argparse
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen

API_BASE = "https://hacker-news.firebaseio.com/v0"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

CST = timezone(timedelta(hours=8))

FEED_MAP = {
    "top": "topstories",
    "new": "newstories",
    "best": "beststories",
    "ask": "askstories",
    "show": "showstories",
    "job": "jobstories",
}


def fetch_json(url):
    req = Request(url)
    req.add_header("User-Agent", USER_AGENT)
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_item(item_id):
    return fetch_json(f"{API_BASE}/item/{item_id}.json")


def fetch_feed_ids(feed_type="top"):
    endpoint = FEED_MAP.get(feed_type, "topstories")
    return fetch_json(f"{API_BASE}/{endpoint}.json")


def extract_article(item):
    item_id = item.get("id", "")
    item_url = item.get("url", "")
    hn_url = f"https://news.ycombinator.com/item?id={item_id}"

    url = item_url or hn_url
    headline = item.get("title", "")

    text = item.get("text", "")
    abstract = re.sub(r"<[^>]+>", "", text).strip() if text else ""

    ts = item.get("time", 0)
    publish_time = ""
    if ts:
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        publish_time = dt.astimezone(CST).strftime("%Y-%m-%d %H:%M:%S")

    return {
        "id": item_id,
        "url": url,
        "headline": headline,
        "abstract": abstract,
        "img_url": "",
        "publish_time": publish_time,
        "hn_url": hn_url,
        "score": item.get("score", 0),
        "by": item.get("by", ""),
        "type": item.get("type", ""),
    }


def crawl_feed(feed_type="top", limit=30, delay=0.1):
    print(f"获取 {feed_type} stories ID 列表...")
    ids = fetch_feed_ids(feed_type)
    total = len(ids)
    fetch_count = min(limit, total)
    print(f"共 {total} 条，将获取前 {fetch_count} 条")

    all_articles = []
    for i, item_id in enumerate(ids[:fetch_count]):
        if (i + 1) % 10 == 0 or i == 0:
            print(f"  [{i+1}/{fetch_count}] 获取 item {item_id}...")
        try:
            item = fetch_item(item_id)
            if item:
                all_articles.append(extract_article(item))
        except Exception as e:
            print(f"  [{i+1}] item {item_id} 获取失败: {e}")
        if delay > 0 and i < fetch_count - 1:
            time.sleep(delay)

    return all_articles


def export_csv(articles, filepath="hn_news.csv"):
    fieldnames = ["id", "url", "headline", "abstract", "img_url", "publish_time", "hn_url", "score", "by", "type"]
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(articles)
    print(f"\n已导出 {len(articles)} 条新闻到 {filepath}")


def main():
    parser = argparse.ArgumentParser(description="Hacker News 爬取工具")
    parser.add_argument("--feed", type=str, default="top",
                        choices=list(FEED_MAP.keys()),
                        help="分类: top/new/best/ask/show/job (默认: top)")
    parser.add_argument("--limit", type=int, default=30, help="获取条数 (默认: 30)")
    parser.add_argument("--delay", type=float, default=0.1, help="请求间隔秒数 (默认: 0.1)")
    parser.add_argument("--output", type=str, default="hn_news.csv", help="输出 CSV 文件名 (默认: hn_news.csv)")
    args = parser.parse_args()

    print("=" * 60)
    print("Hacker News 爬取工具")
    print("=" * 60)
    print(f"  分类: {args.feed} ({FEED_MAP[args.feed]})")
    print(f"  获取条数: {args.limit}")
    print(f"  请求间隔: {args.delay}s")
    print(f"  输出文件: {args.output}")
    print()

    articles = crawl_feed(
        feed_type=args.feed,
        limit=args.limit,
        delay=args.delay
    )

    if articles:
        export_csv(articles, args.output)
        print(f"\n前3条预览:")
        for i, a in enumerate(articles[:3], 1):
            print(f"  {i}. [score={a['score']}] {a['headline'][:60]}")
    else:
        print("未获取到任何新闻数据")


if __name__ == "__main__":
    main()
