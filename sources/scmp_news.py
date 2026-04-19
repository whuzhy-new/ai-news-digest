import csv
import json
import time
import base64
import argparse
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
from urllib.parse import urlencode, quote

API_URL = "https://apigw.scmp.com/content-delivery/v2"
API_KEY = "MyYvyg8M9RTaevVlcIRhN5yRIqqVssNY"
APPLICATION_ID = "2695b2c9-96ef-4fe4-96f8-ba20d0a020b3"
DEFAULT_TOPIC_ID = "VG9waWM6MDY3MGQzM2QtYzFmMC00YWFlLWI1YmUtZDFkYjRmNWMyMDQy"
DEFAULT_COUNT = 11
PERSISTED_QUERY_HASH = "3b19d6162d1b93fc1a9bd569b096859b450b8711c2751437591b474fe64e4578"

CST = timezone(timedelta(hours=8))


def build_url(after_cursor=None, count=DEFAULT_COUNT, topic_id=DEFAULT_TOPIC_ID):
    extensions = json.dumps({
        "persistedQuery": {
            "sha256Hash": PERSISTED_QUERY_HASH,
            "version": 1
        }
    })
    variables = json.dumps({
        "after": after_cursor,
        "applicationId": APPLICATION_ID,
        "count": count,
        "id": topic_id
    })
    params = urlencode({
        "extensions": extensions,
        "operationName": "topicTopicPagePaginationQuery",
        "variables": variables
    })
    return f"{API_URL}?{params}"


def fetch_page(after_cursor=None, count=DEFAULT_COUNT, topic_id=DEFAULT_TOPIC_ID):
    url = build_url(after_cursor, count, topic_id)
    req = Request(url)
    req.add_header("apikey", API_KEY)
    req.add_header("content-type", "application/json")
    req.add_header("origin", "https://www.scmp.com")
    req.add_header("referer", "https://www.scmp.com/")
    req.add_header("user-agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36")
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def extract_article(node):
    article_id = str(node.get("id") or node.get("urlAlias") or "")
    url_alias = node.get("urlAlias", "")
    full_url = f"https://www.scmp.com{url_alias}" if url_alias else ""

    headline = node.get("headline", "")

    summary = node.get("summary", {})
    abstract = summary.get("text", "") if isinstance(summary, dict) else str(summary or "")

    images = node.get("images", [])
    img_url = ""
    if images and len(images) > 0:
        img = images[0]
        size1200 = img.get("size1200x800", {})
        if isinstance(size1200, dict) and size1200.get("url"):
            img_url = size1200["url"]
        elif img.get("url"):
            img_url = img["url"]

    pub_ts = node.get("publishedDate")
    publish_time = ""
    if pub_ts:
        dt = datetime.fromtimestamp(pub_ts / 1000, tz=timezone.utc)
        publish_time = dt.astimezone(CST).strftime("%Y-%m-%d %H:%M:%S")

    return {
        "id": article_id or full_url,
        "url": full_url,
        "headline": headline,
        "abstract": abstract,
        "img_url": img_url,
        "publish_time": publish_time
    }


def crawl_all_pages(max_pages=1, count=DEFAULT_COUNT, topic_id=DEFAULT_TOPIC_ID, delay=1.0):
    all_articles = []
    after_cursor = None

    for page_num in range(1, max_pages + 1):
        print(f"[Page {page_num}] 请求中... (after={after_cursor})")
        try:
            data = fetch_page(after_cursor, count, topic_id)
        except Exception as e:
            print(f"[Page {page_num}] 请求失败: {e}")
            break

        contents = data.get("data", {}).get("node", {}).get("contents", {})
        edges = contents.get("edges", [])
        page_info = contents.get("pageInfo", {})

        if not edges:
            print(f"[Page {page_num}] 无数据，停止翻页")
            break

        for edge in edges:
            article = extract_article(edge.get("node", {}))
            all_articles.append(article)

        has_next = page_info.get("hasNextPage", False)
        end_cursor = page_info.get("endCursor")

        print(f"[Page {page_num}] 获取 {len(edges)} 篇 | hasNextPage={has_next} | endCursor={end_cursor}")

        if not has_next or not end_cursor:
            print("已到最后一页，停止翻页")
            break

        after_cursor = end_cursor
        if delay > 0:
            time.sleep(delay)

    return all_articles


def export_csv(articles, filepath="scmp_news.csv"):
    fieldnames = ["id", "url", "headline", "abstract", "img_url", "publish_time"]
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(articles)
    print(f"\n已导出 {len(articles)} 条新闻到 {filepath}")


def main():
    parser = argparse.ArgumentParser(description="SCMP 新闻爬取工具")
    parser.add_argument("--max-pages", type=int, default=1, help="最大翻页数 (默认: 1)")
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT, help="每页条数 (默认: 11)")
    parser.add_argument("--topic-id", type=str, default=DEFAULT_TOPIC_ID, help="话题 ID (Base64)")
    parser.add_argument("--delay", type=float, default=1.0, help="翻页间隔秒数 (默认: 1.0)")
    parser.add_argument("--output", type=str, default="scmp_news.csv", help="输出 CSV 文件名 (默认: scmp_news.csv)")
    args = parser.parse_args()

    print("=" * 60)
    print("SCMP 新闻爬取工具")
    print("=" * 60)
    print(f"  最大页数: {args.max_pages}")
    print(f"  每页条数: {args.count}")
    print(f"  翻页间隔: {args.delay}s")
    print(f"  输出文件: {args.output}")
    print()

    articles = crawl_all_pages(
        max_pages=args.max_pages,
        count=args.count,
        topic_id=args.topic_id,
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
