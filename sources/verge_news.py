import csv
import re
import json
import time
import argparse
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen

BASE_URL = "https://www.theverge.com/ai-artificial-intelligence"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
PER_PAGE = 40

CST = timezone(timedelta(hours=8))


def fetch_page(page_num=1):
    if page_num == 1:
        url = BASE_URL
    else:
        url = f"{BASE_URL}/archives/{page_num}"
    req = Request(url)
    req.add_header("User-Agent", USER_AGENT)
    with urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def extract_next_data(html):
    match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
    if not match:
        return None
    return json.loads(match.group(1))


def extract_article(node):
    url = node.get("permalink", "")
    article_id = str(node.get("id") or node.get("_id") or url)
    headline = node.get("title", "")

    dek = node.get("dek", {})
    abstract = ""
    if isinstance(dek, dict):
        abstract = dek.get("html", "").strip()
    elif isinstance(dek, str):
        abstract = dek.strip()
    abstract = abstract.lstrip("\ufeff")

    if not abstract:
        promo = node.get("promo", {})
        if isinstance(promo, dict):
            desc = promo.get("description", "")
            if isinstance(desc, dict):
                abstract = desc.get("html", "").strip()
            elif isinstance(desc, str):
                abstract = desc.strip()
    abstract = abstract.lstrip("\ufeff")

    img_url = ""
    promo = node.get("promo", {})
    if isinstance(promo, dict):
        img = promo.get("image", {})
        if isinstance(img, dict):
            thumbs = img.get("thumbnails", {})
            if isinstance(thumbs, dict):
                horizontal = thumbs.get("horizontal", {})
                if isinstance(horizontal, dict):
                    img_url = horizontal.get("url", "")
    if not img_url:
        lede = node.get("ledeMedia", {})
        if isinstance(lede, dict):
            img = lede.get("image", {})
            if isinstance(img, dict):
                thumbs = img.get("thumbnails", {})
                if isinstance(thumbs, dict):
                    horizontal = thumbs.get("horizontal", {})
                    if isinstance(horizontal, dict):
                        img_url = horizontal.get("url", "")

    pub_time_str = node.get("publishedAt", "")
    publish_time = ""
    if pub_time_str:
        try:
            dt = datetime.fromisoformat(pub_time_str.replace("Z", "+00:00"))
            publish_time = dt.astimezone(CST).strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            publish_time = pub_time_str

    return {
        "id": article_id,
        "url": url,
        "headline": headline,
        "abstract": abstract,
        "img_url": img_url,
        "publish_time": publish_time
    }


def crawl_all_pages(max_pages=1, delay=1.5):
    all_articles = []

    for page_num in range(1, max_pages + 1):
        print(f"[Page {page_num}] 请求中...")
        try:
            html = fetch_page(page_num)
        except Exception as e:
            print(f"[Page {page_num}] 请求失败: {e}")
            break

        data = extract_next_data(html)
        if not data:
            print(f"[Page {page_num}] 未找到 __NEXT_DATA__，停止翻页")
            break

        try:
            resp = data["props"]["pageProps"]["hydration"]["responses"][0]
            node = resp["data"]["node"]
            posts = node["categoryLayoutPosts"]
            page_info = posts.get("pageInfo", {})
            nodes = posts.get("nodes", [])
        except (KeyError, IndexError, TypeError) as e:
            print(f"[Page {page_num}] 数据解析失败: {e}")
            break

        if not nodes:
            print(f"[Page {page_num}] 无文章数据，停止翻页")
            break

        for n in nodes:
            all_articles.append(extract_article(n))

        total_pages = page_info.get("totalPages", 0)
        has_next = page_info.get("hasNextPage", False)

        print(f"[Page {page_num}] 获取 {len(nodes)} 篇 | 累计 {len(all_articles)} 篇 | 总页数: {total_pages} | 有下一页: {has_next}")

        if not has_next:
            print("已到最后一页，停止翻页")
            break

        if delay > 0:
            time.sleep(delay)

    return all_articles


def export_csv(articles, filepath="verge_news.csv"):
    fieldnames = ["id", "url", "headline", "abstract", "img_url", "publish_time"]
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(articles)
    print(f"\n已导出 {len(articles)} 条新闻到 {filepath}")


def main():
    parser = argparse.ArgumentParser(description="The Verge AI 新闻爬取工具")
    parser.add_argument("--max-pages", type=int, default=1, help="最大翻页数 (默认: 1)")
    parser.add_argument("--delay", type=float, default=1.5, help="翻页间隔秒数 (默认: 1.5)")
    parser.add_argument("--output", type=str, default="verge_news.csv", help="输出 CSV 文件名 (默认: verge_news.csv)")
    args = parser.parse_args()

    print("=" * 60)
    print("The Verge AI 新闻爬取工具")
    print("=" * 60)
    print(f"  分类: AI (ai-artificial-intelligence)")
    print(f"  最大页数: {args.max_pages}")
    print(f"  每页条数: {PER_PAGE}")
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
