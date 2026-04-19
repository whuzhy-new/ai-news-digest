import argparse
import csv
import importlib.util
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


ROOT_DIR = Path(__file__).resolve().parent
OUTPUT_FIELDS = ["id", "source", "url", "headline", "abstract", "img_url", "publish_time"]
DEFAULT_MASTER_OUTPUT = "all_sources_master.csv"
DEFAULT_HISTORY_DIR = "history"
DEFAULT_HISTORY_LIMIT = 12
TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "igshid",
    "mkt_tok",
    "spm",
    "yclid",
}
GENERIC_ID_KEYS = (
    "id",
    "guid",
    "item_id",
    "itemId",
    "post_id",
    "postId",
    "article_id",
    "articleId",
    "story_id",
    "storyId",
)

CST = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class SourceTask:
    name: str
    module_path: Path
    runner: Callable[["argparse.Namespace", Any], list[dict[str, Any]]]


def load_module(module_name: str, file_path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载模块: {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def normalize_whitespace(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def truncate_text(value: str, limit: int) -> str:
    value = normalize_whitespace(value)
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def strip_tracking_query(url: str) -> str:
    url = normalize_whitespace(url)
    if not url:
        return ""
    parts = urlsplit(url)
    filtered_query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY_KEYS
        and not any(key.lower().startswith(prefix) for prefix in TRACKING_QUERY_PREFIXES)
    ]
    normalized_path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            normalized_path,
            urlencode(filtered_query, doseq=True),
            "",
        )
    )


def standardize_time(value: Any) -> str:
    text = normalize_whitespace(value)
    if not text:
        return ""

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(text, fmt)
            if dt.tzinfo is None:
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            return dt.astimezone(CST).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass

    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.astimezone(CST).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        pass

    try:
        dt = parsedate_to_datetime(text)
        return dt.astimezone(CST).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError, IndexError, OverflowError):
        return text


def build_row_id(source: str, item: dict[str, Any], row: dict[str, str]) -> str:
    source_name = normalize_whitespace(source)

    native_candidates: list[Any] = []
    for key in GENERIC_ID_KEYS:
        native_candidates.append(item.get(key, ""))
    if source == "x_tweets":
        native_candidates.append(item.get("TWEET_ID", ""))

    for candidate in native_candidates:
        candidate_text = normalize_whitespace(candidate)
        if candidate_text:
            return f"{source_name}|{candidate_text}"

    url_key = strip_tracking_query(row.get("url", ""))
    if url_key:
        return f"{source_name}|{url_key}"

    headline_key = normalize_whitespace(row.get("headline", ""))
    publish_time = standardize_time(row.get("publish_time", ""))
    if headline_key or publish_time:
        return f"{source_name}|{headline_key}|{publish_time}"

    return source_name


def finalize_row(source: str, item: dict[str, Any], row: dict[str, str]) -> dict[str, str]:
    finalized = {
        "id": "",
        "source": source,
        "url": strip_tracking_query(row.get("url", "")),
        "headline": normalize_whitespace(row.get("headline", "")),
        "abstract": normalize_whitespace(row.get("abstract", "")),
        "img_url": normalize_whitespace(row.get("img_url", "")),
        "publish_time": standardize_time(row.get("publish_time", "")),
    }
    finalized["id"] = build_row_id(source, item, finalized)
    return finalized


def build_default_row(source: str, item: dict[str, Any]) -> dict[str, str]:
    return finalize_row(
        source,
        item,
        {
            "url": item.get("url", ""),
            "headline": item.get("headline", ""),
            "abstract": item.get("abstract", ""),
            "img_url": item.get("img_url", ""),
            "publish_time": item.get("publish_time", ""),
        },
    )


def normalize_row(source: str, item: dict[str, Any]) -> dict[str, str]:
    if source == "github_trending":
        owner = normalize_whitespace(item.get("owner", ""))
        repo = normalize_whitespace(item.get("repo", ""))
        headline = "/".join(part for part in [owner, repo] if part)
        return finalize_row(
            source,
            item,
            {
                "url": item.get("url", ""),
                "headline": headline,
                "abstract": item.get("full_description") or item.get("description", ""),
                "img_url": item.get("img_url", ""),
                "publish_time": item.get("rss_pub_date") or item.get("crawl_time", ""),
            },
        )

    if source == "x_tweets":
        text = normalize_whitespace(item.get("TEXT", ""))
        return finalize_row(
            source,
            item,
            {
                "url": item.get("TWEET_URL", ""),
                "headline": text,
                "abstract": "",
                "img_url": item.get("MEDIA_URL", ""),
                "publish_time": item.get("PUBLISH_TIME", ""),
            },
        )

    return build_default_row(source, item)


def row_sort_key(row: dict[str, str]) -> tuple[int, str, str]:
    publish_time = row.get("publish_time", "")
    if publish_time:
        return (1, publish_time, row.get("headline", ""))
    return (0, "", row.get("headline", ""))


def build_dedupe_candidates(row: dict[str, str]) -> list[tuple[str, str]]:
    id_key = normalize_whitespace(row.get("id", ""))
    url_key = strip_tracking_query(row.get("url", ""))
    headline_key = normalize_whitespace(row.get("headline", "")).lower()
    abstract_key = normalize_whitespace(row.get("abstract", "")).lower()
    publish_day = row.get("publish_time", "")[:10]

    dedupe_candidates: list[tuple[str, str]] = []
    if id_key:
        dedupe_candidates.append(("id", id_key))
    if url_key:
        dedupe_candidates.append(("url", url_key))
    if headline_key:
        dedupe_candidates.append(("headline_day", f"{headline_key}|{publish_day}"))
    if headline_key and abstract_key:
        dedupe_candidates.append(("headline_abstract", f"{headline_key}|{abstract_key[:160]}"))

    if not dedupe_candidates:
        dedupe_candidates.append(("fallback", str(row)))
    return dedupe_candidates


def dedupe_rows(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], int]:
    unique_rows: list[dict[str, str]] = []
    seen_keys: set[tuple[str, str]] = set()

    for row in rows:
        dedupe_candidates = build_dedupe_candidates(row)

        if any(candidate in seen_keys for candidate in dedupe_candidates):
            continue

        seen_keys.update(dedupe_candidates)
        unique_rows.append(row)

    return unique_rows, len(rows) - len(unique_rows)


def load_csv_rows(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.exists():
        return []

    rows: list[dict[str, str]] = []
    with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for raw_row in reader:
            if raw_row is None:
                continue
            normalized_base = {
                "url": raw_row.get("url", ""),
                "headline": raw_row.get("headline", ""),
                "abstract": raw_row.get("abstract", ""),
                "img_url": raw_row.get("img_url", ""),
                "publish_time": raw_row.get("publish_time", ""),
            }
            row = finalize_row(normalize_whitespace(raw_row.get("source", "")), raw_row, normalized_base)
            explicit_id = normalize_whitespace(raw_row.get("id", ""))
            if explicit_id:
                row["id"] = explicit_id
            if row.get("url") or row.get("headline"):
                rows.append(row)
    return rows


def export_csv(rows: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def filter_new_rows(
    rows: list[dict[str, str]],
    existing_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    existing_keys: set[tuple[str, str]] = set()
    for row in existing_rows:
        existing_keys.update(build_dedupe_candidates(row))

    new_rows: list[dict[str, str]] = []
    for row in rows:
        dedupe_candidates = build_dedupe_candidates(row)
        if any(candidate in existing_keys for candidate in dedupe_candidates):
            continue
        existing_keys.update(dedupe_candidates)
        new_rows.append(row)
    return new_rows


def write_history_snapshot(
    new_rows: list[dict[str, str]],
    history_dir: Path,
    history_limit: int,
) -> Path:
    history_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(CST).strftime("%Y%m%d_%H%M%S")
    history_path = history_dir / f"all_sources_new_{timestamp}.csv"
    export_csv(new_rows, history_path)

    history_files = sorted(history_dir.glob("all_sources_new_*.csv"))
    if len(history_files) > history_limit:
        for old_file in history_files[: len(history_files) - history_limit]:
            old_file.unlink()

    return history_path


def update_master_csv(
    existing_rows: list[dict[str, str]],
    new_rows: list[dict[str, str]],
    output_path: Path,
) -> list[dict[str, str]]:
    combined_rows = existing_rows + new_rows
    combined_rows, _ = dedupe_rows(combined_rows)
    combined_rows.sort(key=row_sort_key, reverse=True)
    export_csv(combined_rows, output_path)
    return combined_rows


def maybe_export_source_csv(
    source_name: str,
    rows: list[dict[str, str]],
    output_dir: Optional[Path],
) -> None:
    if output_dir is None:
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    export_csv(rows, output_dir / f"{source_name}.csv")


def run_github(args: argparse.Namespace, module: Any) -> list[dict[str, Any]]:
    return module.fetch_trending(since=args.github_since, language=args.github_language)


def run_wired(args: argparse.Namespace, module: Any) -> list[dict[str, Any]]:
    return module.crawl_all_pages(max_pages=args.max_pages, delay=args.delay)


def run_verge(args: argparse.Namespace, module: Any) -> list[dict[str, Any]]:
    return module.crawl_all_pages(max_pages=args.max_pages, delay=args.delay)


def run_techcrunch(args: argparse.Namespace, module: Any) -> list[dict[str, Any]]:
    return module.crawl_all_pages(max_pages=args.max_pages, per_page=args.page_size, delay=args.delay)


def run_tmtpost(args: argparse.Namespace, module: Any) -> list[dict[str, Any]]:
    return module.crawl_all_pages(max_pages=args.max_pages, limit=args.page_size, delay=args.delay)


def run_pingwest(args: argparse.Namespace, module: Any) -> list[dict[str, Any]]:
    return module.crawl_all_pages(max_pages=args.max_pages, delay=args.delay)


def run_mtr(args: argparse.Namespace, module: Any) -> list[dict[str, Any]]:
    return module.crawl_all_pages(max_pages=args.max_pages, delay=args.delay)


def run_ifanr(args: argparse.Namespace, module: Any) -> list[dict[str, Any]]:
    return module.crawl_all_pages(max_pages=args.max_pages, limit=args.page_size, delay=args.delay)


def run_wscn(args: argparse.Namespace, module: Any) -> list[dict[str, Any]]:
    return module.crawl_all_pages(max_pages=args.max_pages, limit=args.page_size, delay=args.delay)


def run_36kr(args: argparse.Namespace, module: Any) -> list[dict[str, Any]]:
    return module.crawl_all_pages(max_pages=args.max_pages, page_size=args.page_size, delay=args.delay)


def run_reuters(args: argparse.Namespace, module: Any) -> list[dict[str, Any]]:
    return module.crawl_all_pages(max_pages=args.max_pages, size=args.page_size, delay=args.delay)


def run_qbitai(args: argparse.Namespace, module: Any) -> list[dict[str, Any]]:
    return module.crawl_all_pages(max_pages=args.max_pages, per_page=args.page_size, delay=args.delay)


def run_scmp(args: argparse.Namespace, module: Any) -> list[dict[str, Any]]:
    return module.crawl_all_pages(max_pages=args.max_pages, count=args.page_size, delay=args.delay)


def run_x(args: argparse.Namespace, module: Any) -> list[dict[str, Any]]:
    config = module.load_config()
    auth_token = args.x_auth_token or config.get("auth_token", "")
    ct0 = args.x_ct0 or config.get("ct0", "")
    if not auth_token or not ct0:
        raise RuntimeError("X 缺少 auth_token/ct0，无法抓取")

    if auth_token != config.get("auth_token") or ct0 != config.get("ct0"):
        module.save_config(auth_token, ct0)

    accounts = list(module.DEFAULT_ACCOUNTS)
    if args.x_accounts:
        accounts = []
        for raw_account in args.x_accounts:
            if ":" in raw_account:
                handle, user_id = raw_account.split(":", 1)
                accounts.append({"handle": handle, "user_id": user_id, "name": handle})
            else:
                accounts.append({"handle": raw_account, "user_id": "", "name": raw_account})

    if not accounts:
        raise RuntimeError("X 账号列表为空")

    session = module.requests.Session()
    all_tweets: list[dict[str, Any]] = []
    accounts_updated = False

    for account in accounts:
        handle = account.get("handle", "")
        if not handle:
            continue

        if not account.get("user_id"):
            print(f"[x_tweets] 解析 @{handle} 的 user_id...")
            user_id = module.resolve_user_id(session, handle, auth_token, ct0)
            if not user_id:
                print(f"[x_tweets] 跳过 @{handle}，未能解析 user_id")
                continue
            account["user_id"] = user_id
            accounts_updated = True

        tweets = module.fetch_user_tweets(
            session=session,
            user_id=account["user_id"],
            count=args.x_count,
            max_pages=args.x_max_pages,
            auth_token=auth_token,
            ct0=ct0,
            handle=handle,
            name=account.get("name", ""),
        )
        all_tweets.extend(tweets)

    if accounts_updated and not args.x_accounts:
        with module.ACCOUNTS_FILE.open("w", encoding="utf-8") as f:
            module.json.dump(accounts, f, ensure_ascii=False, indent=2)

    seen_tweet_ids: set[str] = set()
    unique_tweets: list[dict[str, Any]] = []
    for tweet in all_tweets:
        tweet_id = str(tweet.get("TWEET_ID", ""))
        if tweet_id and tweet_id in seen_tweet_ids:
            continue
        if tweet_id:
            seen_tweet_ids.add(tweet_id)
        unique_tweets.append(tweet)

    return unique_tweets


SOURCE_TASKS = {
    "github_trending": SourceTask("github_trending", ROOT_DIR / "sources" / "github_trending.py", run_github),
    "wired_news": SourceTask("wired_news", ROOT_DIR / "sources" / "wired_news.py", run_wired),
    "verge_news": SourceTask("verge_news", ROOT_DIR / "sources" / "verge_news.py", run_verge),
    "techcrunch_news": SourceTask("techcrunch_news", ROOT_DIR / "sources" / "techcrunch_news.py", run_techcrunch),
    "tmtpost_news": SourceTask("tmtpost_news", ROOT_DIR / "sources" / "tmtpost_news.py", run_tmtpost),
    "pingwest_news": SourceTask("pingwest_news", ROOT_DIR / "sources" / "pingwest_news.py", run_pingwest),
    "mtr_news": SourceTask("mtr_news", ROOT_DIR / "sources" / "mtr_news.py", run_mtr),
    "ifanr_news": SourceTask("ifanr_news", ROOT_DIR / "sources" / "ifanr_news.py", run_ifanr),
    "wscn_news": SourceTask("wscn_news", ROOT_DIR / "sources" / "wscn_news.py", run_wscn),
    "kr36_news": SourceTask("kr36_news", ROOT_DIR / "sources" / "kr36_news.py", run_36kr),
    "reuters_news": SourceTask("reuters_news", ROOT_DIR / "sources" / "reuters_news.py", run_reuters),
    "qbitai_news": SourceTask("qbitai_news", ROOT_DIR / "sources" / "qbitai_news.py", run_qbitai),
    "scmp_news": SourceTask("scmp_news", ROOT_DIR / "sources" / "scmp_news.py", run_scmp),
    "x_tweets": SourceTask("x_tweets", ROOT_DIR / "sources" / "x" / "x_tweets.py", run_x),
}


def parse_sources(raw_sources: Optional[list[str]]) -> list[SourceTask]:
    if not raw_sources or raw_sources == ["all"]:
        return list(SOURCE_TASKS.values())

    selected: list[SourceTask] = []
    for raw_source in raw_sources:
        for name in raw_source.split(","):
            source_name = name.strip()
            if not source_name:
                continue
            if source_name == "all":
                return list(SOURCE_TASKS.values())
            if source_name not in SOURCE_TASKS:
                raise ValueError(f"未知 source: {source_name}")
            if SOURCE_TASKS[source_name] not in selected:
                selected.append(SOURCE_TASKS[source_name])
    return selected


def fetch_source(task: SourceTask, args: argparse.Namespace) -> tuple[str, list[dict[str, str]]]:
    module_name = f"aggregator_{task.name}"
    module = load_module(module_name, task.module_path)
    raw_items = task.runner(args, module)
    normalized_rows = [normalize_row(task.name, item) for item in raw_items]
    normalized_rows = [row for row in normalized_rows if row.get("url") or row.get("headline")]
    print(f"[{task.name}] 完成，获取 {len(normalized_rows)} 条")
    return task.name, normalized_rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI News 多源并发汇总抓取工具")
    parser.add_argument(
        "--sources",
        nargs="*",
        default=["all"],
        help="要抓取的数据源，支持 all 或多个 source 名称",
    )
    parser.add_argument("--output", default=DEFAULT_MASTER_OUTPUT, help="总表 CSV 输出路径")
    parser.add_argument(
        "--history-dir",
        default=DEFAULT_HISTORY_DIR,
        help="分表输出目录，每次抓取新增单独保存",
    )
    parser.add_argument(
        "--history-limit",
        type=int,
        default=DEFAULT_HISTORY_LIMIT,
        help="保留最近多少次分表快照",
    )
    parser.add_argument("--max-pages", type=int, default=1, help="大多数分页源的最大翻页数")
    parser.add_argument("--page-size", type=int, default=20, help="大多数分页源的每页条数")
    parser.add_argument("--delay", type=float, default=0.5, help="大多数分页源的翻页间隔秒数")
    parser.add_argument("--workers", type=int, default=6, help="并发线程数")
    parser.add_argument(
        "--source-output-dir",
        default="",
        help="可选：按 source 输出归一化后的单独 CSV 目录",
    )

    parser.add_argument("--github-since", default="daily", choices=["daily", "weekly", "monthly"])
    parser.add_argument("--github-language", default="")

    parser.add_argument("--x-auth-token", default=os.environ.get("X_AUTH_TOKEN", ""))
    parser.add_argument("--x-ct0", default=os.environ.get("X_CT0", ""))
    parser.add_argument("--x-count", type=int, default=20)
    parser.add_argument("--x-max-pages", type=int, default=1)
    parser.add_argument("--x-accounts", nargs="*", default=None)
    return parser


def main() -> None:
    parser = build_parser()
    parsed_args = parser.parse_args()

    try:
        selected_tasks = parse_sources(parsed_args.sources)
    except ValueError as exc:
        parser.error(str(exc))
        return

    output_path = Path(parsed_args.output)
    if not output_path.is_absolute():
        output_path = ROOT_DIR / output_path

    history_dir = Path(parsed_args.history_dir)
    if not history_dir.is_absolute():
        history_dir = ROOT_DIR / history_dir

    history_limit = max(1, parsed_args.history_limit)

    source_output_dir: Optional[Path] = None
    if parsed_args.source_output_dir:
        source_output_dir = Path(parsed_args.source_output_dir)
        if not source_output_dir.is_absolute():
            source_output_dir = ROOT_DIR / source_output_dir

    worker_count = max(1, min(parsed_args.workers, len(selected_tasks)))
    print("=" * 72)
    print("AI News 多源并发汇总抓取")
    print("=" * 72)
    print(f"数据源数量: {len(selected_tasks)}")
    print(f"并发线程数: {worker_count}")
    print(f"总表输出: {output_path}")
    print(f"分表目录: {history_dir}")
    print(f"分表保留次数: {history_limit}")
    if source_output_dir:
        print(f"单源输出目录: {source_output_dir}")
    print()

    all_rows: list[dict[str, str]] = []
    failed_sources: list[tuple[str, str]] = []

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_map = {
            executor.submit(fetch_source, task, parsed_args): task.name
            for task in selected_tasks
        }
        for future in as_completed(future_map):
            source_name = future_map[future]
            try:
                finished_source, rows = future.result()
                all_rows.extend(rows)
                maybe_export_source_csv(finished_source, rows, source_output_dir)
            except Exception as exc:
                failed_sources.append((source_name, str(exc)))
                print(f"[{source_name}] 失败: {exc}")

    deduped_rows, duplicate_count = dedupe_rows(all_rows)
    deduped_rows.sort(key=row_sort_key, reverse=True)
    existing_rows = load_csv_rows(output_path)
    new_rows = filter_new_rows(deduped_rows, existing_rows)
    is_initial = len(existing_rows) == 0
    if is_initial:
        snapshot_path = None
    else:
        snapshot_path = write_history_snapshot(new_rows, history_dir, history_limit)
    master_rows = update_master_csv(existing_rows, new_rows, output_path)

    print()
    print("=" * 72)
    print("抓取完成")
    print("=" * 72)
    print(f"抓取总条数: {len(all_rows)}")
    print(f"本次去重后条数: {len(deduped_rows)}")
    print(f"去重移除数: {duplicate_count}")
    if is_initial:
        print(f"首次建库，写入总表 {len(master_rows)} 条（不生成分表快照）")
    else:
        print(f"本次新增条数: {len(new_rows)}")
        print(f"总表累计条数: {len(master_rows)}")
    print(f"总表文件: {output_path}")
    if snapshot_path:
        print(f"本次分表快照: {snapshot_path}")
    if failed_sources:
        print("失败数据源:")
        for source_name, reason in failed_sources:
            print(f"  - {source_name}: {reason}")
    else:
        print("所有数据源执行成功")


if __name__ == "__main__":
    main()
