import csv
import json
import re
import time
import argparse
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
from urllib.parse import urlencode

API_URL = "https://www.reuters.com/pf/api/v3/content/fetch/recent-stories-by-sections-v1"
DEFAULT_SECTION = "/technology/"
DEFAULT_SIZE = 20
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"

CST = timezone(timedelta(hours=8))

COOKIES = (
    'datadome=EaR8KZqNn6Qa~FLU5AstmadE8duc61BDkle6xC_RfrqInu59RTNRtm83H7sU4HulfcCwAgLMmeTLdaEtN7UFaAf90HXxel12baKV6dHfMLpnMYg0xmnjibNDQMztygZz; '
    'usprivacy=1---; '
    'RT="z=1&dm=www.reuters.com&si=d0af2976-d3d4-4660-9e32-d13d50abd4bd&ss=mnvu8nop&sl=0&tt=0"; '
    'OptanonConsent=isGpcEnabled=0&datestamp=Sun+Apr+12+2026+22%3A07%3A37+GMT%2B0800+(%E4%B8%AD%E5%9B%BD%E6%A0%87%E5%87%86%E6%97%B6%E9%97%B4)&version=202601.1.0&browserGpcFlag=0&isIABGlobal=false&hosts=&consentId=3fafb5dc-2dc6-45b4-8d0e-354336e18215&interactionCount=0&isAnonUser=1&landingPath=https%3A%2F%2Fwww.reuters.com%2F; '
    '_gcl_au=1.1.106172352.1776002861; '
    '_fbp=fb.1.1776002862438.764921097256301180'
)


def build_url(section_id=DEFAULT_SECTION, size=DEFAULT_SIZE, offset=0):
    query = json.dumps({
        "section_ids": section_id,
        "size": size,
        "offset": offset,
        "website": "reuters"
    })
    params = urlencode({
        "query": query,
        "d": 356,
        "mxId": "00000000",
        "_website": "reuters"
    })
    return f"{API_URL}?{params}"


def fetch_page(section_id=DEFAULT_SECTION, size=DEFAULT_SIZE, offset=0):
    url = build_url(section_id, size, offset)
    req = Request(url)
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("referer", "https://www.reuters.com/")
    req.add_header("accept", "*/*")
    req.add_header("accept-language", "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7")
    req.add_header("sec-fetch-dest", "empty")
    req.add_header("sec-fetch-mode", "cors")
    req.add_header("sec-fetch-site", "same-origin")
    req.add_header("sec-ch-ua", '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"')
    req.add_header("sec-ch-ua-arch", '"arm"')
    req.add_header("sec-ch-ua-mobile", "?0")
    req.add_header("sec-ch-ua-model", '""')
    req.add_header("sec-ch-ua-platform", '"macOS"')
    req.add_header("sec-ch-device-memory", "8")
    req.add_header("Cookie", COOKIES)
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_time(time_str):
    if not time_str:
        return ""
    try:
        cleaned = re.sub(r"(\.\d{3})\d+", r"\1", time_str)
        if cleaned.endswith("Z"):
            cleaned = cleaned[:-1] + "+00:00"
        dt = datetime.fromisoformat(cleaned)
        return dt.astimezone(CST).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return time_str


def extract_article(a):
    article_id = str(a.get("id") or a.get("uri") or a.get("canonical_url") or "")
    url = f"https://www.reuters.com{a.get('canonical_url', '')}"
    headline = a.get("title", a.get("basic_headline", ""))
    abstract = a.get("description", "")

    thumbnail = a.get("thumbnail", {})
    img_url = ""
    if isinstance(thumbnail, dict):
        img_url = thumbnail.get("resizer_url", thumbnail.get("url", ""))

    pub_time = parse_time(a.get("published_time", a.get("display_time", "")))

    return {
        "id": article_id or url,
        "url": url,
        "headline": headline,
        "abstract": abstract,
        "img_url": img_url,
        "publish_time": pub_time
    }


def crawl_all_pages(max_pages=1, size=DEFAULT_SIZE, section_id=DEFAULT_SECTION, delay=1.0):
    all_articles = []
    offset = 0

    for page_num in range(1, max_pages + 1):
        print(f"[Page {page_num}] offset={offset} 请求中...")
        try:
            data = fetch_page(section_id, size, offset)
        except Exception as e:
            print(f"[Page {page_num}] 请求失败: {e}")
            break

        if data.get("statusCode") != 200:
            print(f"[Page {page_num}] API 错误: {data.get('message', 'unknown')}")
            break

        articles = data.get("result", {}).get("articles", [])
        pagination = data.get("result", {}).get("pagination", {})
        total_size = pagination.get("total_size", 0)

        if not articles:
            print(f"[Page {page_num}] 无数据，停止翻页")
            break

        for a in articles:
            all_articles.append(extract_article(a))

        print(f"[Page {page_num}] 获取 {len(articles)} 篇 | 累计 {len(all_articles)} 篇 | 总可用 {total_size}")

        offset += size
        if offset >= total_size:
            print("已到最后一页，停止翻页")
            break

        if delay > 0:
            time.sleep(delay)

    return all_articles


def export_csv(articles, filepath="reuters_news.csv"):
    fieldnames = ["id", "url", "headline", "abstract", "img_url", "publish_time"]
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(articles)
    print(f"\n已导出 {len(articles)} 条新闻到 {filepath}")


def main():
    parser = argparse.ArgumentParser(description="Reuters 新闻爬取工具")
    parser.add_argument("--max-pages", type=int, default=1, help="最大翻页数 (默认: 1)")
    parser.add_argument("--size", type=int, default=DEFAULT_SIZE, help="每页条数 (默认: 20)")
    parser.add_argument("--section", type=str, default=DEFAULT_SECTION, help="板块路径 (默认: /technology/)")
    parser.add_argument("--delay", type=float, default=1.0, help="翻页间隔秒数 (默认: 1.0)")
    parser.add_argument("--output", type=str, default="reuters_news.csv", help="输出 CSV 文件名 (默认: reuters_news.csv)")
    args = parser.parse_args()

    print("=" * 60)
    print("Reuters 新闻爬取工具")
    print("=" * 60)
    print(f"  板块: {args.section}")
    print(f"  最大页数: {args.max_pages}")
    print(f"  每页条数: {args.size}")
    print(f"  翻页间隔: {args.delay}s")
    print(f"  输出文件: {args.output}")
    print()

    articles = crawl_all_pages(
        max_pages=args.max_pages,
        size=args.size,
        section_id=args.section,
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
