import argparse
import base64
import csv
import io
import json
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen

UTC8 = timezone(timedelta(hours=8))

REPO = "whuzhy-new/ai-news-digest"
API_BASE = f"https://api.github.com/repos/{REPO}/contents"


def api_get(path, token=""):
    url = f"{API_BASE}/{path}"
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(url, headers=headers)
    with urlopen(req) as resp:
        return json.loads(resp.read().decode())


def fetch_csv(path, token=""):
    data = api_get(path, token)
    content = base64.b64decode(data["content"]).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    return list(reader)


def list_history_files(token=""):
    data = api_get("history", token)
    files = [f["name"] for f in data if f["name"].startswith("all_sources_new_")]
    files.sort(reverse=True)
    return files


def fetch_latest_snapshot(token=""):
    files = list_history_files(token)
    if not files:
        return []
    rows = fetch_csv(f"history/{files[0]}", token)
    return filter_noise(rows)


def parse_utc8(s):
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC8)
        return dt.astimezone(UTC8)
    except Exception:
        return None


URL_PATTERN = re.compile(r"^https?://\S+$")


def is_noise(row):
    hl = row.get("headline", "").strip()
    source = row.get("source", "")
    if hl.startswith("RT @") and len(hl) < 50:
        return True
    if len(hl) < 15:
        return True
    if hl.startswith("RT @") and "…" in hl:
        return True
    if URL_PATTERN.match(hl):
        return True
    if source == "x_tweets" and len(hl.split()) <= 2:
        return True
    return False


def filter_noise(rows):
    return [r for r in rows if not is_noise(r)]


def filter_recent(rows, hours=8):
    cutoff = datetime.now(UTC8) - timedelta(hours=hours)
    result = []
    for r in rows:
        pt = r.get("publish_time", "")
        dt = parse_utc8(pt)
        if dt and dt >= cutoff:
            result.append(r)
    return result


def fetch_master(token="", recent_hours=8):
    rows = fetch_csv("all_sources_master.csv", token)
    if rows:
        rows = filter_recent(rows, recent_hours)
        rows = filter_noise(rows)
    return rows


def print_rows(rows, limit):
    if not rows:
        print("无数据")
        return
    for i, row in enumerate(rows[:limit], 1):
        headline = row.get("headline", "")[:60]
        source = row.get("source", "")
        pub = row.get("publish_time", "")[:16]
        print(f"  {i:>3}. [{source}] {headline}  ({pub})")
    if len(rows) > limit:
        print(f"  ... 共 {len(rows)} 条，显示前 {limit} 条")


def main():
    parser = argparse.ArgumentParser(description="查询 AI News Digest 最新数据（公开仓库）")
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""), help="GitHub PAT（可选，提高 API 限额）")
    parser.add_argument("--mode", choices=["latest", "master", "both"], default="latest", help="latest=最新快照, master=总表近N小时, both=两者")
    parser.add_argument("--hours", type=int, default=8, help="时间范围（小时）")
    parser.add_argument("--limit", type=int, default=999, help="显示条数")
    args = parser.parse_args()

    if args.mode in ("latest", "both"):
        print("📦 最新快照 (history/):")
        try:
            rows = fetch_latest_snapshot(args.token)
            print(f"   共 {len(rows)} 条新增")
            print_rows(rows, args.limit)
        except Exception as e:
            print(f"   获取失败: {e}")

    if args.mode in ("master", "both"):
        print(f"\n📊 总表近{args.hours}小时（已去噪）:")
        try:
            rows = fetch_master(args.token, recent_hours=args.hours)
            print(f"   共 {len(rows)} 条")
            print_rows(rows, args.limit)
        except Exception as e:
            print(f"   获取失败: {e}")


if __name__ == "__main__":
    main()
