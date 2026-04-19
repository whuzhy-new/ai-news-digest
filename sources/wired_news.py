import csv
import re
import json
import time
import argparse
from html import unescape
from urllib.request import Request, urlopen

BASE_URL = "https://www.wired.com/category/artificial-intelligence/"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
PER_PAGE = 20


def fetch_html(url, timeout=30):
    req = Request(url)
    req.add_header("User-Agent", USER_AGENT)
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def parse_category_page(html):
    items = list(re.finditer(r'data-item="(.*?)"', html))
    articles = []

    for i, match in enumerate(items):
        try:
            item_data = json.loads(unescape(match.group(1)))
        except (json.JSONDecodeError, TypeError):
            continue

        hotel_link = item_data.get("hotelLink", "")
        if not hotel_link or "/story/" not in hotel_link:
            continue

        url = f"https://www.wired.com{hotel_link}" if hotel_link.startswith("/") else hotel_link
        headline = item_data.get("dangerousHed", "")

        next_pos = items[i + 1].start() if i + 1 < len(items) else match.end() + 5000
        card_html = html[match.start():next_pos]

        img_url = ""
        imgs = re.findall(r'src="(https://media\.wired\.com/photos/[^"]+)"', card_html)
        for img in imgs:
            if "w_720" in img or "w_1280" in img or "master" in img:
                img_url = img
                break
        if not img_url and imgs:
            img_url = imgs[0]
        img_url = img_url.replace("%2C", ",")

        articles.append({
            "id": url,
            "url": url,
            "headline": headline,
            "abstract": "",
            "img_url": img_url,
            "publish_time": ""
        })

    return articles


def crawl_all_pages(max_pages=1, delay=1.0):
    all_articles = []

    for page_num in range(1, max_pages + 1):
        url = f"{BASE_URL}?page={page_num}" if page_num > 1 else BASE_URL
        print(f"[Page {page_num}] 请求中... {url}")
        try:
            html = fetch_html(url)
        except Exception as e:
            print(f"[Page {page_num}] 请求失败: {e}")
            break

        articles = parse_category_page(html)
        if not articles:
            print(f"[Page {page_num}] 无文章数据，停止翻页")
            break

        all_articles.extend(articles)
        print(f"[Page {page_num}] 获取 {len(articles)} 篇 | 累计 {len(all_articles)} 篇")

        if len(articles) < PER_PAGE:
            print("文章数不足一页，停止翻页")
            break

        if delay > 0:
            time.sleep(delay)

    return all_articles


def export_csv(articles, filepath="wired_news.csv"):
    fieldnames = ["id", "url", "headline", "abstract", "img_url", "publish_time"]
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(articles)
    print(f"\n已导出 {len(articles)} 条新闻到 {filepath}")


def main():
    parser = argparse.ArgumentParser(description="Wired AI 新闻爬取工具")
    parser.add_argument("--max-pages", type=int, default=1, help="最大翻页数 (默认: 1)")
    parser.add_argument("--delay", type=float, default=1.0, help="翻页间隔秒数 (默认: 1.0)")
    parser.add_argument("--output", type=str, default="wired_news.csv", help="输出 CSV 文件名 (默认: wired_news.csv)")
    args = parser.parse_args()

    print("=" * 60)
    print("Wired AI 新闻爬取工具")
    print("=" * 60)
    print(f"  分类: AI (artificial-intelligence)")
    print(f"  最大页数: {args.max_pages}")
    print(f"  每页条数: ~{PER_PAGE}")
    print(f"  翻页间隔: {args.delay}s")
    print(f"  输出文件: {args.output}")
    print()

    articles = crawl_all_pages(
        max_pages=args.max_pages,
        delay=args.delay
    )

    if articles:
        export_csv(articles, args.output)
        print(f"\n前3条预览:")
        for i, a in enumerate(articles[:3], 1):
            print(f"  {i}. {a['headline'][:60]}")
    else:
        print("未获取到任何新闻数据")


if __name__ == "__main__":
    main()
