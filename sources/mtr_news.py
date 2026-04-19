import csv
import json
import re
import time
import argparse
from urllib.request import Request, urlopen
from urllib.parse import urlencode

API_URL = "https://wp.technologyreview.com/wp-json/irving/v1/data/feed_section"
DEFAULT_TOPIC = 9
DEFAULT_PAGE_SIZE = 5
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"


def fetch_page(page=1, topic=DEFAULT_TOPIC):
    params = urlencode({"page": page, "topic": topic, "orderBy": "date"})
    url = f"{API_URL}?{params}"
    req = Request(url)
    req.add_header("User-Agent", USER_AGENT)
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def extract_from_post(post):
    config = post.get("config", {})
    article_id = str(post.get("id") or config.get("id") or config.get("link", ""))
    url = config.get("link", "")
    headline = config.get("hed", "")
    dek_html = config.get("dek", "")
    abstract = re.sub(r"<[^>]+>", "", dek_html).strip()

    img_url = ""
    for child in post.get("children", []):
        if child.get("name") == "image":
            child_config = child.get("config", {})
            img_url = child_config.get("url", child_config.get("src", ""))
            break

    date_match = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", url)
    publish_time = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)} 00:00:00" if date_match else ""

    return {
        "id": article_id,
        "url": url,
        "headline": headline,
        "abstract": abstract,
        "img_url": img_url,
        "publish_time": publish_time
    }


def crawl_all_pages(max_pages=1, topic=DEFAULT_TOPIC, delay=1.0):
    all_articles = []
    seen_urls = set()

    for page_num in range(1, max_pages + 1):
        print(f"[Page {page_num}] 请求中...")
        try:
            data = fetch_page(page_num, topic)
        except Exception as e:
            print(f"[Page {page_num}] 请求失败: {e}")
            break

        if not isinstance(data, list) or len(data) == 0:
            print(f"[Page {page_num}] 无数据，停止翻页")
            break

        section = data[0]
        feed_posts = section.get("feedPosts", [])
        featured = section.get("featuredPost", {})

        if not feed_posts and not featured:
            print(f"[Page {page_num}] 无文章，停止翻页")
            break

        if page_num == 1 and featured:
            article = extract_from_post(featured)
            if article["url"] not in seen_urls:
                all_articles.append(article)
                seen_urls.add(article["url"])

        for post in feed_posts:
            article = extract_from_post(post)
            if article["url"] not in seen_urls:
                all_articles.append(article)
                seen_urls.add(article["url"])

        print(f"[Page {page_num}] 获取 {len(feed_posts)} 篇 | 累计 {len(all_articles)} 篇")

        if len(feed_posts) < DEFAULT_PAGE_SIZE:
            print("已到最后一页，停止翻页")
            break

        if delay > 0:
            time.sleep(delay)

    return all_articles


def export_csv(articles, filepath="mtr_news.csv"):
    fieldnames = ["id", "url", "headline", "abstract", "img_url", "publish_time"]
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(articles)
    print(f"\n已导出 {len(articles)} 条新闻到 {filepath}")


def main():
    parser = argparse.ArgumentParser(description="MIT Technology Review 新闻爬取工具")
    parser.add_argument("--max-pages", type=int, default=1, help="最大翻页数 (默认: 1)")
    parser.add_argument("--topic", type=int, default=DEFAULT_TOPIC, help="话题 ID (默认: 9=AI)")
    parser.add_argument("--delay", type=float, default=1.0, help="翻页间隔秒数 (默认: 1.0)")
    parser.add_argument("--output", type=str, default="mtr_news.csv", help="输出 CSV 文件名 (默认: mtr_news.csv)")
    args = parser.parse_args()

    print("=" * 60)
    print("MIT Technology Review 新闻爬取工具")
    print("=" * 60)
    print(f"  话题 ID: {args.topic}")
    print(f"  最大页数: {args.max_pages}")
    print(f"  翻页间隔: {args.delay}s")
    print(f"  输出文件: {args.output}")
    print()

    articles = crawl_all_pages(
        max_pages=args.max_pages,
        topic=args.topic,
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
