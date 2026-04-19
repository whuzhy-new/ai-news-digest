import argparse
import base64
import csv
import io
import json
import os
from urllib.request import Request, urlopen

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
    return fetch_csv(f"history/{files[0]}", token)


def fetch_master(token=""):
    return fetch_csv("all_sources_master.csv", token)


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
    parser = argparse.ArgumentParser(description="查询 AI News Digest 最新数据")
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""), help="GitHub PAT（私有仓库需要）")
    parser.add_argument("--mode", choices=["latest", "master", "both"], default="latest", help="latest=最新快照, master=总表, both=两者")
    parser.add_argument("--limit", type=int, default=20, help="显示条数")
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
        print("\n📊 总表 (all_sources_master.csv):")
        try:
            rows = fetch_master(args.token)
            print(f"   共 {len(rows)} 条")
            print_rows(rows, args.limit)
        except Exception as e:
            print(f"   获取失败: {e}")


if __name__ == "__main__":
    main()
