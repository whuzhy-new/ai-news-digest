import csv
import re
import time
import random
import argparse
from datetime import datetime, timezone, timedelta
from xml.etree import ElementTree
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

RSS_BASE = "https://mshibanami.github.io/GitHubTrendingRSS"
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
]

CST = timezone(timedelta(hours=8))

SINCE_MAP = {
    "daily": "daily",
    "weekly": "weekly",
    "monthly": "monthly",
}

MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 5

MEDIA_NS = "{http://search.yahoo.com/mrss/}"


def _random_ua():
    return random.choice(USER_AGENTS)


def _build_request(url):
    req = Request(url)
    req.add_header("User-Agent", _random_ua())
    req.add_header("Accept", "application/rss+xml, application/xml, text/xml, */*")
    return req


def fetch_with_retry(url, max_retries=MAX_RETRIES):
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            req = _build_request(url)
            with urlopen(req, timeout=30) as resp:
                status = resp.status if hasattr(resp, "status") else 200
                if status == 200:
                    return resp.read().decode("utf-8")
                elif status == 429:
                    retry_after = resp.headers.get("Retry-After", RETRY_BACKOFF_BASE * attempt)
                    wait = int(retry_after) if str(retry_after).isdigit() else RETRY_BACKOFF_BASE * attempt
                    print(f"  [429 限速] 第{attempt}次重试，等待 {wait}s ...")
                    time.sleep(wait)
                elif status == 403:
                    wait = RETRY_BACKOFF_BASE * attempt + random.uniform(1, 3)
                    print(f"  [403 禁止访问] 第{attempt}次重试，等待 {wait:.1f}s ...")
                    time.sleep(wait)
                else:
                    raise HTTPError(url, status, resp.reason, resp.headers, None)
        except HTTPError as e:
            last_err = e
            if e.code in (429, 403):
                wait = RETRY_BACKOFF_BASE * attempt + random.uniform(1, 3)
                print(f"  [HTTP {e.code}] 第{attempt}次重试，等待 {wait:.1f}s ...")
                time.sleep(wait)
            else:
                print(f"  [HTTP {e.code}] {e.reason}，第{attempt}次重试 ...")
                time.sleep(RETRY_BACKOFF_BASE * attempt)
        except (URLError, ConnectionError, TimeoutError, OSError) as e:
            last_err = e
            wait = RETRY_BACKOFF_BASE * attempt + random.uniform(1, 3)
            print(f"  [网络错误] {type(e).__name__}，第{attempt}次重试，等待 {wait:.1f}s ...")
            time.sleep(wait)
    raise RuntimeError(f"请求失败，已重试 {max_retries} 次: {last_err}")


def _strip_html(text):
    return re.sub(r"<[^>]+>", "", text).strip()


def _extract_description(raw_desc):
    if not raw_desc:
        return "", ""
    short = ""
    first_p = re.search(r"<p>(.*?)</p>", raw_desc, re.DOTALL)
    if first_p:
        short = _strip_html(first_p.group(1))
    elif "<hr" in raw_desc:
        short = _strip_html(raw_desc.split("<hr")[0])
    else:
        short = _strip_html(raw_desc)
    full = _strip_html(raw_desc)
    full = re.sub(r"\n{3,}", "\n\n", full)
    words = full.split()
    if len(words) > 200:
        full = " ".join(words[:200]) + "..."
    return short, full


def parse_rss(xml_text):
    root = ElementTree.fromstring(xml_text)
    channel = root.find("channel")

    pub_date_str = ""
    pub_date_el = channel.find("pubDate")
    if pub_date_el is not None and pub_date_el.text:
        pub_date_str = pub_date_el.text.strip()

    repos = []
    for item in channel.findall("item"):
        title_el = item.find("title")
        link_el = item.find("link")
        desc_el = item.find("description")

        full_name = title_el.text.strip() if title_el is not None and title_el.text else ""
        url = link_el.text.strip() if link_el is not None and link_el.text else ""
        raw_desc = desc_el.text.strip() if desc_el is not None and desc_el.text else ""

        parts = full_name.split("/", 1)
        owner = parts[0] if len(parts) >= 2 else ""
        repo = parts[1] if len(parts) >= 2 else full_name

        description, full_description = _extract_description(raw_desc)

        img_url = ""
        media_el = item.find(f"{MEDIA_NS}content")
        if media_el is not None:
            img_url = media_el.get("url", "")

        repos.append({
            "id": full_name,
            "owner": owner,
            "repo": repo,
            "url": url,
            "description": description,
            "full_description": full_description,
            "img_url": img_url,
            "rss_pub_date": pub_date_str,
        })

    return repos


def fetch_trending(since="daily", language=""):
    since_val = SINCE_MAP.get(since, "daily")
    lang_path = language if language else "all"
    url = f"{RSS_BASE}/{since_val}/{lang_path}.xml"

    print(f"请求 RSS: {url}")
    xml_text = fetch_with_retry(url)

    repos = parse_rss(xml_text)

    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    for r in repos:
        r["crawl_time"] = now

    return repos


def export_csv(repos, filepath="github_trending.csv"):
    fieldnames = [
        "id", "owner", "repo", "url", "description", "full_description",
        "img_url", "rss_pub_date", "crawl_time"
    ]
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(repos)
    print(f"\n已导出 {len(repos)} 条到 {filepath}")


def main():
    parser = argparse.ArgumentParser(description="GitHub Trending 爬取工具 (RSS)")
    parser.add_argument("--since", type=str, default="daily",
                        choices=list(SINCE_MAP.keys()),
                        help="时间范围: daily/weekly/monthly (默认: daily)")
    parser.add_argument("--language", type=str, default="",
                        help="编程语言筛选 (如: python, typescript, go)")
    parser.add_argument("--output", type=str, default="github_trending.csv",
                        help="输出 CSV 文件名 (默认: github_trending.csv)")
    parser.add_argument("--retries", type=int, default=MAX_RETRIES,
                        help=f"最大重试次数 (默认: {MAX_RETRIES})")
    args = parser.parse_args()

    print("=" * 60)
    print("GitHub Trending 爬取工具 (RSS)")
    print("=" * 60)
    print(f"  数据源: {RSS_BASE}")
    print(f"  时间范围: {args.since}")
    if args.language:
        print(f"  编程语言: {args.language}")
    print(f"  输出文件: {args.output}")
    print()

    repos = fetch_trending(
        since=args.since,
        language=args.language,
    )

    if repos:
        export_csv(repos, args.output)
        print(f"\n前5条预览:")
        for i, r in enumerate(repos[:5], 1):
            print(f"  {i}. {r['owner']}/{r['repo']}  [{r['description'][:60]}]")
    else:
        print("未获取到任何数据")


if __name__ == "__main__":
    main()
