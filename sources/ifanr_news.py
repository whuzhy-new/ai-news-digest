import csv
import json
import time
import argparse
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
from urllib.parse import urlencode

API_URL = "https://sso.ifanr.com/api/v5/wp/web-feed/"
DEFAULT_LIMIT = 20
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"

CST = timezone(timedelta(hours=8))


def fetch_page(limit=DEFAULT_LIMIT, offset=0, published_at_lte=""):
    params = {"limit": limit, "offset": offset}
    if published_at_lte:
        params["published_at__lte"] = published_at_lte
    url = f"{API_URL}?{urlencode(params)}"
    req = Request(url)
    req.add_header("User-Agent", USER_AGENT)
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def extract_article(a):
    article_id = str(a.get("post_id") or a.get("id") or a.get("post_url", ""))
    url = a.get("post_url", "")
    headline = a.get("post_title", "")
    abstract = a.get("post_excerpt", "")
    img_url = a.get("post_cover_image", "")

    pub_time = a.get("created_at_format", "")
    if not pub_time:
        ts = a.get("created_at")
        if ts:
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            pub_time = dt.astimezone(CST).strftime("%Y-%m-%d %H:%M:%S")

    return {
        "id": article_id,
        "url": url,
        "headline": headline,
        "abstract": abstract,
        "img_url": img_url,
        "publish_time": pub_time
    }


def crawl_all_pages(max_pages=1, limit=DEFAULT_LIMIT, delay=1.0):
    all_articles = []
    offset = 0

    for page_num in range(1, max_pages + 1):
        print(f"[Page {page_num}] offset={offset} 请求中...")
        try:
            data = fetch_page(limit, offset)
        except Exception as e:
            print(f"[Page {page_num}] 请求失败: {e}")
            break

        objects = data.get("objects", [])
        meta = data.get("meta", {})
        total_count = meta.get("total_count", 0)
        next_url = meta.get("next", "")

        if not objects:
            print(f"[Page {page_num}] 无数据，停止翻页")
            break

        for a in objects:
            all_articles.append(extract_article(a))

        print(f"[Page {page_num}] 获取 {len(objects)} 篇 | 累计 {len(all_articles)} 篇 | 总计 {total_count}")

        if not next_url:
            print("已到最后一页，停止翻页")
            break

        offset += limit
        if offset >= total_count:
            print("已到最后一页，停止翻页")
            break

        if delay > 0:
            time.sleep(delay)

    return all_articles


def export_csv(articles, filepath="ifanr_news.csv"):
    fieldnames = ["id", "url", "headline", "abstract", "img_url", "publish_time"]
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(articles)
    print(f"\n已导出 {len(articles)} 条新闻到 {filepath}")


def main():
    parser = argparse.ArgumentParser(description="爱范儿(ifanr.com)新闻爬取工具")
    parser.add_argument("--max-pages", type=int, default=1, help="最大翻页数 (默认: 1)")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="每页条数 (默认: 20)")
    parser.add_argument("--delay", type=float, default=1.0, help="翻页间隔秒数 (默认: 1.0)")
    parser.add_argument("--output", type=str, default="ifanr_news.csv", help="输出 CSV 文件名 (默认: ifanr_news.csv)")
    args = parser.parse_args()

    print("=" * 60)
    print("爱范儿(ifanr.com)新闻爬取工具")
    print("=" * 60)
    print(f"  最大页数: {args.max_pages}")
    print(f"  每页条数: {args.limit}")
    print(f"  翻页间隔: {args.delay}s")
    print(f"  输出文件: {args.output}")
    print()

    articles = crawl_all_pages(
        max_pages=args.max_pages,
        limit=args.limit,
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
