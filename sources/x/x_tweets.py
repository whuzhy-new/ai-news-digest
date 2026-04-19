import csv
import json
import os
import time
import argparse
from datetime import datetime, timezone
from pathlib import Path

import requests

CONFIG_FILE = Path(__file__).resolve().parent / "x_tweets_config.txt"

GRAPHQL_URL = "https://x.com/i/api/graphql/x3B_xLqC0yZawOB7WQhaVQ/UserTweets"

BEARER_TOKEN = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs=1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"

FEATURES = {
    "rweb_video_screen_enabled": False,
    "profile_label_improvements_pcf_label_in_post_enabled": True,
    "responsive_web_profile_redirect_enabled": False,
    "rweb_tipjar_consumption_enabled": False,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "premium_content_api_read_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
    "responsive_web_grok_analyze_post_followups_enabled": True,
    "responsive_web_jetfuel_frame": True,
    "responsive_web_grok_share_attachment_enabled": True,
    "responsive_web_grok_annotations_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "content_disclosure_indicator_enabled": True,
    "content_disclosure_ai_generated_indicator_enabled": True,
    "responsive_web_grok_show_grok_translated_post": True,
    "responsive_web_grok_analysis_button_from_backend": True,
    "post_ctas_fetch_enabled": True,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": False,
    "responsive_web_grok_image_annotation_enabled": True,
    "responsive_web_grok_imagine_annotation_enabled": True,
    "responsive_web_grok_community_note_auto_translation_is_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
}

FIELD_TOGGLES = {"withArticlePlainText": False}

CSV_FIELDS = [
    "id",
    "TWEET_ID",
    "AUTHOR",
    "HANDLE",
    "TEXT",
    "TWEET_URL",
    "MEDIA_URL",
    "PUBLISH_TIME",
    "LIKES",
    "RETWEETS",
    "REPLIES",
    "VIEWS",
    "BOOKMARKS",
    "IS_QUOTE",
    "IS_RETWEET",
]

ACCOUNTS_FILE = Path(__file__).resolve().parent / "x_accounts.json"


def load_default_accounts():
    if ACCOUNTS_FILE.exists():
        with open(ACCOUNTS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []


DEFAULT_ACCOUNTS = load_default_accounts()

USER_BY_SCREEN_NAME_URL = "https://x.com/i/api/graphql/xc8f1g7BYqr6VTzTbvNlGw/UserByScreenName"

USER_BY_SCREEN_NAME_FEATURES = {
    "hidden_profile_subscriptions_enabled": True,
    "profile_label_improvements_pcf_label_in_post_enabled": True,
    "rweb_tipjar_consumption_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "subscriptions_verification_info_is_identity_verified_enabled": True,
    "subscriptions_verification_info_verified_since_enabled": True,
    "highlights_tweets_tab_ui_enabled": True,
    "responsive_web_twitter_article_notes_tab_enabled": True,
    "subscriptions_feature_can_gift_premium": True,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "responsive_web_graphql_timeline_navigation_enabled": True,
}

REQUEST_INTERVAL_SECONDS = 2.5
MAX_RETRY_ATTEMPTS = 4
RETRY_BACKOFF_BASE_SECONDS = 4.0
RETRY_BACKOFF_MAX_SECONDS = 45.0
LAST_REQUEST_TS = 0.0


def parse_retry_after(value):
    if not value:
        return None
    try:
        return max(0, int(str(value).strip()))
    except (TypeError, ValueError):
        return None


def wait_for_request_slot():
    global LAST_REQUEST_TS
    elapsed = time.monotonic() - LAST_REQUEST_TS
    if elapsed < REQUEST_INTERVAL_SECONDS:
        time.sleep(REQUEST_INTERVAL_SECONDS - elapsed)


def request_json_with_retry(session, url, *, params, headers, cookies, timeout, context):
    global LAST_REQUEST_TS

    last_error = None
    for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
        wait_for_request_slot()
        try:
            resp = session.get(
                url,
                params=params,
                headers=headers,
                cookies=cookies,
                timeout=timeout,
            )
            LAST_REQUEST_TS = time.monotonic()

            if resp.status_code == 429:
                retry_after = parse_retry_after(resp.headers.get("retry-after"))
                wait_seconds = retry_after if retry_after is not None else min(
                    RETRY_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)),
                    RETRY_BACKOFF_MAX_SECONDS,
                )
                print(f"  [{context}] 触发限流 429，第 {attempt}/{MAX_RETRY_ATTEMPTS} 次重试，等待 {wait_seconds:.1f}s")
                if attempt == MAX_RETRY_ATTEMPTS:
                    return None
                time.sleep(wait_seconds)
                continue

            if 500 <= resp.status_code < 600:
                wait_seconds = min(
                    RETRY_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)),
                    RETRY_BACKOFF_MAX_SECONDS,
                )
                print(f"  [{context}] 服务端错误 {resp.status_code}，第 {attempt}/{MAX_RETRY_ATTEMPTS} 次重试，等待 {wait_seconds:.1f}s")
                if attempt == MAX_RETRY_ATTEMPTS:
                    resp.raise_for_status()
                time.sleep(wait_seconds)
                continue

            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            last_error = e
            wait_seconds = min(
                RETRY_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)),
                RETRY_BACKOFF_MAX_SECONDS,
            )
            print(f"  [{context}] 请求异常，第 {attempt}/{MAX_RETRY_ATTEMPTS} 次重试: {e}")
            if attempt == MAX_RETRY_ATTEMPTS:
                raise
            time.sleep(wait_seconds)

    if last_error:
        raise last_error
    return None


def resolve_user_id(session, handle, auth_token, ct0):
    headers = build_headers(ct0)
    cookies = build_cookies(auth_token, ct0)
    variables = {"screen_name": handle}
    params = {
        "variables": json.dumps(variables, separators=(",", ":")),
        "features": json.dumps(USER_BY_SCREEN_NAME_FEATURES, separators=(",", ":")),
        "fieldToggles": json.dumps({"withAuxiliaryUserLabels": False}, separators=(",", ":")),
    }
    try:
        data = request_json_with_retry(
            session,
            USER_BY_SCREEN_NAME_URL,
            params=params,
            headers=headers,
            cookies=cookies,
            timeout=15,
            context=f"resolve_user_id:@{handle}",
        )
        if not data:
            return ""
        user = data.get("data", {}).get("user", {}).get("result", {})
        if user:
            return user.get("rest_id", "")
    except Exception as e:
        print(f"  Failed to resolve user_id for @{handle}: {e}")
    return ""


def parse_twitter_time(time_str):
    dt = datetime.strptime(time_str, "%a %b %d %H:%M:%S %z %Y")
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def build_headers(ct0):
    return {
        "accept": "*/*",
        "authorization": f"Bearer {BEARER_TOKEN}",
        "content-type": "application/json",
        "x-csrf-token": ct0,
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-active-user": "yes",
        "x-twitter-client-language": "en",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    }


def build_cookies(auth_token, ct0):
    return {"auth_token": auth_token, "ct0": ct0}


def build_params(user_id, count=20, cursor=None):
    variables = {
        "userId": str(user_id),
        "count": count,
        "includePromotedContent": False,
        "withQuickPromoteEligibilityTweetFields": True,
        "withVoice": True,
    }
    if cursor:
        variables["cursor"] = cursor
    return {
        "variables": json.dumps(variables, separators=(",", ":")),
        "features": json.dumps(FEATURES, separators=(",", ":")),
        "fieldToggles": json.dumps(FIELD_TOGGLES, separators=(",", ":")),
    }


def extract_tweet_from_result(tweet_result, account_handle=None, account_name=None):
    legacy = tweet_result.get("legacy", {})
    if not legacy:
        return None

    is_retweet = legacy.get("retweeted", False)
    if is_retweet:
        rt_result = legacy.get("retweeted_status_result", {}).get("result", {})
        rt_legacy = rt_result.get("legacy", {})
        if rt_legacy:
            legacy = rt_legacy
            tweet_result = rt_result

    note_tweet = tweet_result.get("note_tweet", {})
    if note_tweet:
        note_text = (
            note_tweet.get("note_tweet_results", {})
            .get("result", {})
            .get("text", "")
        )
        if note_text:
            legacy["full_text"] = note_text

    media_url = ""
    ext_media = legacy.get("extended_entities", {}).get("media", [])
    if ext_media:
        for m in ext_media:
            if m.get("type") == "photo":
                media_url = m.get("media_url_https", "")
                break
        if not media_url:
            media_url = ext_media[0].get("media_url_https", "")

    tweet_id = legacy.get("id_str", "")

    core_user = (
        tweet_result.get("core", {})
        .get("user_results", {})
        .get("result", {})
    )
    core_legacy = core_user.get("legacy", {})
    author = core_legacy.get("name", "") or account_name or ""
    handle = core_legacy.get("screen_name", "") or account_handle or ""

    tweet_url = f"https://x.com/{handle}/status/{tweet_id}" if handle and tweet_id else ""

    created_at = legacy.get("created_at", "")
    publish_time = parse_twitter_time(created_at) if created_at else ""

    views_count = ""
    views_obj = tweet_result.get("views", {})
    if views_obj:
        views_count = views_obj.get("count", "")

    return {
        "id": tweet_id,
        "TWEET_ID": tweet_id,
        "AUTHOR": author,
        "HANDLE": f"@{handle}" if handle else "",
        "TEXT": legacy.get("full_text", ""),
        "TWEET_URL": tweet_url,
        "MEDIA_URL": media_url,
        "PUBLISH_TIME": publish_time,
        "LIKES": legacy.get("favorite_count", 0),
        "RETWEETS": legacy.get("retweet_count", 0),
        "REPLIES": legacy.get("reply_count", 0),
        "VIEWS": views_count,
        "BOOKMARKS": legacy.get("bookmark_count", 0),
        "IS_QUOTE": legacy.get("is_quote_status", False),
        "IS_RETWEET": is_retweet,
    }


def parse_entries(entries, account_handle=None, account_name=None):
    tweets = []
    for entry in entries:
        content = entry.get("content", {})
        entry_type = content.get("__typename", "")
        if entry_type == "TimelineTimelineItem":
            item_content = content.get("itemContent", {})
            if item_content.get("__typename") != "TimelineTweet":
                continue
            tweet_result = item_content.get("tweet_results", {}).get("result", {})
            if tweet_result.get("__typename") == "TweetTombstone":
                continue
            tweet = extract_tweet_from_result(tweet_result, account_handle, account_name)
            if tweet:
                tweets.append(tweet)
        elif entry_type == "TimelineTimelineModule":
            items = content.get("items", [])
            for item in items:
                item_content = item.get("item", {}).get("itemContent", {})
                if item_content.get("__typename") != "TimelineTweet":
                    continue
                tweet_result = item_content.get("tweet_results", {}).get("result", {})
                if tweet_result.get("__typename") == "TweetTombstone":
                    continue
                tweet = extract_tweet_from_result(tweet_result, account_handle, account_name)
                if tweet:
                    tweets.append(tweet)
    return tweets


def fetch_user_tweets(session, user_id, count, max_pages, auth_token, ct0, handle=None, name=None):
    headers = build_headers(ct0)
    cookies = build_cookies(auth_token, ct0)
    all_tweets = []
    cursor = None

    for page in range(1, max_pages + 1):
        params = build_params(user_id, count, cursor)
        try:
            data = request_json_with_retry(
                session,
                GRAPHQL_URL,
                params=params,
                headers=headers,
                cookies=cookies,
                timeout=30,
                context=f"tweets:@{handle or user_id}:page{page}",
            )
            if not data:
                print(f"  Page {page}: 请求未成功，停止抓取")
                break
        except requests.exceptions.HTTPError as e:
            print(f"  HTTP error: {e}")
            break
        except Exception as e:
            print(f"  Request error: {e}")
            break

        user_result = data.get("data", {}).get("user", {}).get("result", {})
        if not user_result:
            print(f"  Empty user result (user_id={user_id} may be invalid)")
            break

        timeline = user_result.get("timeline", {}).get("timeline", {})
        instructions = timeline.get("instructions", [])

        page_tweets = []
        next_cursor = None
        for inst in instructions:
            if inst.get("type") == "TimelineAddEntries":
                entries = inst.get("entries", [])
                page_tweets = parse_entries(entries, handle, name)
                for e in entries:
                    content = e.get("content", {})
                    if content.get("cursorType") == "Bottom":
                        next_cursor = content.get("value")

        all_tweets.extend(page_tweets)
        print(f"  Page {page}: {len(page_tweets)} tweets (total: {len(all_tweets)})")

        if not next_cursor or not page_tweets:
            break
        cursor = next_cursor

    return all_tweets


def load_config():
    if not CONFIG_FILE.exists():
        return {}
    config = {}
    with open(CONFIG_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                config[key.strip()] = value.strip()
    return config


def save_config(auth_token, ct0):
    with open(CONFIG_FILE, "w") as f:
        f.write(f"auth_token={auth_token}\n")
        f.write(f"ct0={ct0}\n")
    os.chmod(CONFIG_FILE, 0o600)


def main():
    config = load_config()

    parser = argparse.ArgumentParser(description="Fetch tweets from X accounts via GraphQL API")
    parser.add_argument("--auth-token", default=config.get("auth_token", ""), help="X auth_token cookie (saved to config if provided)")
    parser.add_argument("--ct0", default=config.get("ct0", ""), help="X ct0 cookie (saved to config if provided)")
    parser.add_argument("--count", type=int, default=20, help="Tweets per page (default: 20)")
    parser.add_argument("--max-pages", type=int, default=1, help="Max pages per account (default: 1)")
    parser.add_argument("--output", default="x_tweets.csv", help="Output CSV filename")
    parser.add_argument(
        "--accounts",
        nargs="*",
        help='Accounts as handles (e.g. "karpathy swyx") or "handle:user_id". Default: built-in list',
    )
    args = parser.parse_args()

    if not args.auth_token or not args.ct0:
        if config.get("auth_token") and config.get("ct0"):
            args.auth_token = config["auth_token"]
            args.ct0 = config["ct0"]
            print(f"Loaded credentials from {CONFIG_FILE}")
        else:
            print("Error: No credentials found. Run once with --auth-token and --ct0 to save them.")
            print(f"  Config file: {CONFIG_FILE}")
            return

    if args.auth_token != config.get("auth_token") or args.ct0 != config.get("ct0"):
        save_config(args.auth_token, args.ct0)
        print(f"Credentials saved to {CONFIG_FILE}")

    if args.accounts:
        accounts = []
        for a in args.accounts:
            if ":" in a:
                handle, user_id = a.split(":", 1)
                accounts.append({"handle": handle, "user_id": user_id, "name": handle})
            else:
                accounts.append({"handle": a, "user_id": "", "name": a})
    else:
        accounts = DEFAULT_ACCOUNTS

    session = requests.Session()
    all_tweets = []
    accounts_updated = False

    for account in accounts:
        if not account["user_id"]:
            print(f"Resolving user_id for @{account['handle']}...")
            user_id = resolve_user_id(session, account["handle"], args.auth_token, args.ct0)
            if not user_id:
                print(f"  Skipping @{account['handle']} (could not resolve user_id)")
                continue
            account["user_id"] = user_id
            accounts_updated = True
            print(f"  @{account['handle']} -> user_id={user_id}")

        print(f"Fetching @{account['handle']} ({account.get('name', '')})...")
        tweets = fetch_user_tweets(
            session,
            account["user_id"],
            args.count,
            args.max_pages,
            args.auth_token,
            args.ct0,
            handle=account["handle"],
            name=account.get("name", ""),
        )
        all_tweets.extend(tweets)
        print(f"  Got {len(tweets)} tweets from @{account['handle']}")
        time.sleep(2)

    seen = set()
    unique_tweets = []
    for t in all_tweets:
        if t["TWEET_ID"] not in seen:
            seen.add(t["TWEET_ID"])
            unique_tweets.append(t)

    with open(args.output, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(unique_tweets)

    if accounts_updated and not args.accounts:
        with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
            json.dump(accounts, f, ensure_ascii=False, indent=2)
        print(f"Updated user_ids saved to {ACCOUNTS_FILE}")

    print(f"\nDone. {len(unique_tweets)} unique tweets saved to {args.output}")


if __name__ == "__main__":
    main()
