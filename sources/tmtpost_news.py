import csv
import json
import time
import argparse
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
from urllib.parse import urlencode

API_URL = "https://api.tmtpost.com/v1/lists/category"
DEFAULT_CATEGORY = "6916385"
DEFAULT_LIMIT = 20
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"

CST = timezone(timedelta(hours=8))


def fetch_page(category=DEFAULT_CATEGORY, limit=DEFAULT_LIMIT, offset=0):
    params = urlencode({
        "category_guid": category,
        "limit": limit,
        "offset": offset,
        "subtype": "post;atlas;video_article;fm_audios;word",
        "image_size": '["512_288"]',
        "post_fields": "access;authors;number_of_reads;is_pro_post;is_paid_special_column_post;available;",
    })
    url = f"{API_URL}?{params}"
    req = Request(url)
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("app-key", "2015042403")
    req.add_header("app-version", "web1.0")
    req.add_header("device", "pc")
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def extract_article(item):
    article_id = str(item.get("id") or item.get("post_id") or item.get("guid") or item.get("short_url") or item.get("share_link", ""))
    url = item.get("short_url", item.get("share_link", ""))
    headline = item.get("title", "")
    abstract = item.get("summary", "")

    thumb = item.get("thumb_image", {})
    img_url = ""
    if isinstance(thumb, dict):
        original = thumb.get("original", [])
        if original and isinstance(original, list):
            img_url = original[0].get("url", "")
        elif isinstance(original, dict):
            img_url = original.get("url", "")

    pub_ts = item.get("time_published")
    publish_time = ""
    if pub_ts:
        ts = int(pub_ts)
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        publish_time = dt.astimezone(CST).strftime("%Y-%m-%d %H:%M:%S")

    return {
        "id": article_id,
        "url": url,
        "headline": headline,
        "abstract": abstract,
        "img_url": img_url,
        "publish_time": publish_time,
    }


def crawl_all_pages(max_pages=1, limit=DEFAULT_LIMIT, category=DEFAULT_CATEGORY, delay=1.0):
    all_articles = []
    offset = 0

    for page_num in range(1, max_pages + 1):
        print(f"[Page {page_num}] offset={offset} 请求中...")
        try:
            data = fetch_page(category, limit, offset)
        except Exception as e:
            print(f"[Page {page_num}] 请求失败: {e}")
            break

        if data.get("result") != "ok":
            errors = data.get("errors", [])
            print(f"[Page {page_num}] API 错误: {errors}")
            break

        items = data.get("data", [])
        cursor = data.get("cursor", {})
        total = int(cursor.get("total", 0))

        if not items:
            print(f"[Page {page_num}] 无数据，停止翻页")
            break

        for item in items:
            all_articles.append(extract_article(item))

        print(f"[Page {page_num}] 获取 {len(items)} 篇 | 累计 {len(all_articles)} 篇 | 总计 {total}")

        offset += limit
        if offset >= total:
            print("已到最后一页，停止翻页")
            break

        if delay > 0:
            time.sleep(delay)

    return all_articles


def export_csv(articles, filepath="tmtpost_news.csv"):
    fieldnames = ["id", "url", "headline", "abstract", "img_url", "publish_time"]
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(articles)
    print(f"\n已导出 {len(articles)} 条新闻到 {filepath}")


def main():
    parser = argparse.ArgumentParser(description="钛媒体(tmtpost.com)新闻爬取工具")
    parser.add_argument("--max-pages", type=int, default=1, help="最大翻页数 (默认: 1)")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="每页条数 (默认: 20)")
    parser.add_argument("--category", type=str, default=DEFAULT_CATEGORY, help="分类 GUID (默认: 6916385=AGI)")
    parser.add_argument("--delay", type=float, default=1.0, help="翻页间隔秒数 (默认: 1.0)")
    parser.add_argument("--output", type=str, default="tmtpost_news.csv", help="输出 CSV 文件名 (默认: tmtpost_news.csv)")
    args = parser.parse_args()

    print("=" * 60)
    print("钛媒体(tmtpost.com)新闻爬取工具")
    print("=" * 60)
    print(f"  分类 GUID: {args.category}")
    print(f"  最大页数: {args.max_pages}")
    print(f"  每页条数: {args.limit}")
    print(f"  翻页间隔: {args.delay}s")
    print(f"  输出文件: {args.output}")
    print()

    articles = crawl_all_pages(
        max_pages=args.max_pages,
        limit=args.limit,
        category=args.category,
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
