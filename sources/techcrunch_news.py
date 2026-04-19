import csv
import json
import re
import time
import argparse
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
from urllib.parse import urlencode

API_URL = "https://techcrunch.com/wp-json/wp/v2/posts"
MEDIA_API = "https://techcrunch.com/wp-json/wp/v2/media"
CATEGORY_AI = 577047203
DEFAULT_LIMIT = 20
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"

CST = timezone(timedelta(hours=-4))


def fetch_json(url):
    req = Request(url)
    req.add_header("User-Agent", USER_AGENT)
    with urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        headers = dict(resp.headers)
        return data, headers


def fetch_posts(page=1, per_page=DEFAULT_LIMIT, category=CATEGORY_AI):
    params = urlencode({
        "categories": category,
        "per_page": per_page,
        "page": page,
        "_fields": "id,date,link,title,excerpt,featured_media"
    })
    url = f"{API_URL}?{params}"
    data, headers = fetch_json(url)
    total = int(headers.get("X-Wp-Total", 0))
    total_pages = int(headers.get("X-Wp-Totalpages", 0))
    return data, total, total_pages


def fetch_media_batch(media_ids):
    if not media_ids:
        return {}
    params = urlencode({
        "include": ",".join(str(mid) for mid in media_ids),
        "_fields": "id,source_url,media_details"
    })
    url = f"{MEDIA_API}?{params}"
    data, _ = fetch_json(url)
    result = {}
    for item in data:
        mid = item.get("id")
        source_url = item.get("source_url", "")
        details = item.get("media_details", {})
        sizes = details.get("sizes", {})
        img_url = source_url
        for size_name in ["full", "large", "medium_large"]:
            if size_name in sizes and sizes[size_name].get("source_url"):
                img_url = sizes[size_name]["source_url"]
                break
        result[mid] = img_url
    return result


def extract_article(item, media_map):
    article_id = str(item.get("id", "") or item.get("link", ""))
    url = item.get("link", "")
    title_html = item.get("title", {}).get("rendered", "")
    headline = re.sub(r"<[^>]+>", "", title_html).strip()
    headline = headline.replace("&#8217;", "'").replace("&#8216;", "'").replace("&amp;", "&").replace("&#038;", "&")

    excerpt_html = item.get("excerpt", {}).get("rendered", "")
    abstract = re.sub(r"<[^>]+>", "", excerpt_html).strip()

    media_id = item.get("featured_media", 0)
    img_url = media_map.get(media_id, "") if media_id else ""

    date_str = item.get("date", "")
    publish_time = date_str.replace("T", " ") if date_str else ""

    return {
        "id": article_id,
        "url": url,
        "headline": headline,
        "abstract": abstract,
        "img_url": img_url,
        "publish_time": publish_time,
    }


def crawl_all_pages(max_pages=1, per_page=DEFAULT_LIMIT, category=CATEGORY_AI, delay=1.0):
    all_articles = []
    page = 1

    while page <= max_pages:
        print(f"[Page {page}] 请求中...")
        try:
            data, total, total_pages = fetch_posts(page, per_page, category)
        except Exception as e:
            print(f"[Page {page}] 请求失败: {e}")
            break

        if not data:
            print(f"[Page {page}] 无数据，停止翻页")
            break

        media_ids = [item.get("featured_media", 0) for item in data if item.get("featured_media")]
        media_map = {}
        if media_ids:
            try:
                media_map = fetch_media_batch(media_ids)
            except Exception as e:
                print(f"[Page {page}] 图片获取失败: {e}")

        for item in data:
            all_articles.append(extract_article(item, media_map))

        print(f"[Page {page}] 获取 {len(data)} 篇 | 累计 {len(all_articles)} 篇" + (f" | 总计 {total}" if total else ""))

        if len(data) < per_page:
            print("已到最后一页，停止翻页")
            break

        if total and page >= total_pages:
            print("已到最后一页，停止翻页")
            break

        page += 1
        if delay > 0:
            time.sleep(delay)

    return all_articles


def export_csv(articles, filepath="techcrunch_news.csv"):
    fieldnames = ["id", "url", "headline", "abstract", "img_url", "publish_time"]
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(articles)
    print(f"\n已导出 {len(articles)} 条新闻到 {filepath}")


def main():
    parser = argparse.ArgumentParser(description="TechCrunch 新闻爬取工具")
    parser.add_argument("--max-pages", type=int, default=1, help="最大翻页数 (默认: 1)")
    parser.add_argument("--per-page", type=int, default=DEFAULT_LIMIT, help="每页条数 (默认: 20, 最大: 100)")
    parser.add_argument("--category", type=int, default=CATEGORY_AI, help="分类 ID (默认: 577047203=AI)")
    parser.add_argument("--delay", type=float, default=1.0, help="翻页间隔秒数 (默认: 1.0)")
    parser.add_argument("--output", type=str, default="techcrunch_news.csv", help="输出 CSV 文件名 (默认: techcrunch_news.csv)")
    args = parser.parse_args()

    print("=" * 60)
    print("TechCrunch 新闻爬取工具")
    print("=" * 60)
    print(f"  数据源: WordPress REST API")
    print(f"  分类 ID: {args.category}")
    print(f"  最大页数: {args.max_pages}")
    print(f"  每页条数: {args.per_page}")
    print(f"  翻页间隔: {args.delay}s")
    print(f"  输出文件: {args.output}")
    print()

    articles = crawl_all_pages(
        max_pages=args.max_pages,
        per_page=args.per_page,
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
