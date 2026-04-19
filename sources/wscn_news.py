import csv
import json
import time
import argparse
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
from urllib.parse import urlencode

API_URL = "https://api-one-wscn.awtmt.com/apiv1/content/information-flow"
DEFAULT_CHANNEL = "ai"
DEFAULT_LIMIT = 20
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"

CST = timezone(timedelta(hours=8))


def fetch_page(channel=DEFAULT_CHANNEL, limit=DEFAULT_LIMIT, cursor=""):
    params = urlencode({
        "channel": channel,
        "accept": "article",
        "cursor": cursor,
        "limit": limit,
        "action": "upglide"
    })
    url = f"{API_URL}?{params}"
    req = Request(url)
    req.add_header("User-Agent", USER_AGENT)
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def extract_article(item):
    a = item.get("resource", {})
    article_id = str(a.get("id") or a.get("resource_id") or a.get("uri", ""))
    url = a.get("uri", "")
    headline = a.get("title", "")
    abstract = a.get("content_short", "")

    img = a.get("image", {})
    img_url = img.get("uri", "") if isinstance(img, dict) else ""

    pub_ts = a.get("display_time")
    publish_time = ""
    if pub_ts:
        dt = datetime.fromtimestamp(pub_ts, tz=timezone.utc)
        publish_time = dt.astimezone(CST).strftime("%Y-%m-%d %H:%M:%S")

    return {
        "id": article_id,
        "url": url,
        "headline": headline,
        "abstract": abstract,
        "img_url": img_url,
        "publish_time": publish_time
    }


def crawl_all_pages(max_pages=1, limit=DEFAULT_LIMIT, channel=DEFAULT_CHANNEL, delay=1.0):
    all_articles = []
    cursor = ""

    for page_num in range(1, max_pages + 1):
        print(f"[Page {page_num}] 请求中... (cursor={cursor[:30]}...)" if cursor else f"[Page {page_num}] 请求中...")
        try:
            data = fetch_page(channel, limit, cursor)
        except Exception as e:
            print(f"[Page {page_num}] 请求失败: {e}")
            break

        if data.get("code") != 20000:
            print(f"[Page {page_num}] API 错误: code={data.get('code')}, msg={data.get('message', '')}")
            break

        d = data.get("data", {})
        items = d.get("items", [])
        next_cursor = d.get("next_cursor", "")
        item_count = d.get("item_count", 0)

        if not items:
            print(f"[Page {page_num}] 无数据，停止翻页")
            break

        for item in items:
            all_articles.append(extract_article(item))

        print(f"[Page {page_num}] 获取 {len(items)} 篇 | 累计 {len(all_articles)} 篇")

        if not next_cursor or item_count < limit:
            print("已到最后一页，停止翻页")
            break

        cursor = next_cursor
        if delay > 0:
            time.sleep(delay)

    return all_articles


def export_csv(articles, filepath="wscn_news.csv"):
    fieldnames = ["id", "url", "headline", "abstract", "img_url", "publish_time"]
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(articles)
    print(f"\n已导出 {len(articles)} 条新闻到 {filepath}")


def main():
    parser = argparse.ArgumentParser(description="华尔街见闻新闻爬取工具")
    parser.add_argument("--max-pages", type=int, default=1, help="最大翻页数 (默认: 1)")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="每页条数 (默认: 20)")
    parser.add_argument("--channel", type=str, default=DEFAULT_CHANNEL, help="频道 (默认: ai)")
    parser.add_argument("--delay", type=float, default=1.0, help="翻页间隔秒数 (默认: 1.0)")
    parser.add_argument("--output", type=str, default="wscn_news.csv", help="输出 CSV 文件名 (默认: wscn_news.csv)")
    args = parser.parse_args()

    print("=" * 60)
    print("华尔街见闻新闻爬取工具")
    print("=" * 60)
    print(f"  频道: {args.channel}")
    print(f"  最大页数: {args.max_pages}")
    print(f"  每页条数: {args.limit}")
    print(f"  翻页间隔: {args.delay}s")
    print(f"  输出文件: {args.output}")
    print()

    articles = crawl_all_pages(
        max_pages=args.max_pages,
        limit=args.limit,
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
