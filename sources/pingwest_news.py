import csv
import json
import re
import time
import argparse
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen

API_URL = "https://www.pingwest.com/api/state/list"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"

CST = timezone(timedelta(hours=8))


def fetch_page(last_id=""):
    url = f"{API_URL}?last_id={last_id}"
    req = Request(url)
    req.add_header("User-Agent", USER_AGENT)
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_html_list(html):
    items = re.findall(
        r'<section data-id="(\d+)" class="item[^"]*"\s+data-t="(\d+)">(.*?)</section>\s*</section>',
        html, re.DOTALL
    )

    articles = []
    for item_id, timestamp, item_html in items:
        title_match = re.search(
            r'<p class="title">\s*<a href="([^"]+)"[^>]*>(.*?)</a>', item_html, re.DOTALL
        )
        url = f"https:{title_match.group(1)}" if title_match else ""
        headline = re.sub(r"<[^>]+>", "", title_match.group(2)).strip() if title_match else ""

        desc_match = re.search(r'<p class="description"><a[^>]*>(.*?)</a>', item_html, re.DOTALL)
        abstract = re.sub(r"<[^>]+>", "", desc_match.group(1)).strip() if desc_match else ""

        img_match = re.search(r'<img src="([^"]+)"', item_html)
        img_url = img_match.group(1) if img_match else ""
        if img_url and "?x-oss-process=" in img_url:
            img_url = img_url.split("?x-oss-process=")[0]

        ts = int(timestamp)
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        publish_time = dt.astimezone(CST).strftime("%Y-%m-%d %H:%M:%S")

        articles.append({
            "url": url,
            "headline": headline,
            "abstract": abstract,
            "img_url": img_url,
            "publish_time": publish_time,
            "id": item_id,
        })

    return articles


def crawl_all_pages(max_pages=1, delay=1.0):
    all_articles = []
    last_id = ""

    for page_num in range(1, max_pages + 1):
        print(f"[Page {page_num}] last_id={last_id or '(首页)'} 请求中...")
        try:
            data = fetch_page(last_id)
        except Exception as e:
            print(f"[Page {page_num}] 请求失败: {e}")
            break

        if data.get("status") != 1:
            print(f"[Page {page_num}] API 错误: {data.get('message', '')}")
            break

        html = data.get("data", {}).get("list", "")
        if not html:
            print(f"[Page {page_num}] 无数据，停止翻页")
            break

        articles = parse_html_list(html)
        if not articles:
            print(f"[Page {page_num}] 解析无文章，停止翻页")
            break

        all_articles.extend(articles)
        last_id = articles[-1]["id"]

        print(f"[Page {page_num}] 获取 {len(articles)} 篇 | 累计 {len(all_articles)} 篇")

        if delay > 0:
            time.sleep(delay)

    return all_articles


def export_csv(articles, filepath="pingwest_news.csv"):
    fieldnames = ["id", "url", "headline", "abstract", "img_url", "publish_time"]
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for a in articles:
            writer.writerow({k: a[k] for k in fieldnames})
    print(f"\n已导出 {len(articles)} 条新闻到 {filepath}")


def main():
    parser = argparse.ArgumentParser(description="品玩(PingWest)新闻爬取工具")
    parser.add_argument("--max-pages", type=int, default=1, help="最大翻页数 (默认: 1)")
    parser.add_argument("--delay", type=float, default=1.0, help="翻页间隔秒数 (默认: 1.0)")
    parser.add_argument("--output", type=str, default="pingwest_news.csv", help="输出 CSV 文件名 (默认: pingwest_news.csv)")
    args = parser.parse_args()

    print("=" * 60)
    print("品玩(PingWest)新闻爬取工具")
    print("=" * 60)
    print(f"  最大页数: {args.max_pages}")
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
            print(f"  {i}. [{a['publish_time']}] {a['headline'][:60]}")
    else:
        print("未获取到任何新闻数据")


if __name__ == "__main__":
    main()
