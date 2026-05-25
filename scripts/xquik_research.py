#!/usr/bin/env python3
"""Collect read-only X research candidates through Xquik.

Usage:
  python3 xquik_research.py search "AI crypto" --limit 10
  python3 xquik_research.py search "from:VitalikButerin AI" --format markdown
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

DEFAULT_BASE_URL = "https://xquik.com"


def api_key() -> str:
    return os.getenv("XQUIK_API_KEY") or ""


def base_url() -> str:
    return (os.getenv("XQUIK_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def build_url(path: str, query: Optional[dict[str, Any]] = None) -> str:
    url = f"{base_url()}/{path.lstrip('/')}"
    if query:
        filtered = {key: str(value) for key, value in query.items() if value not in (None, "")}
        if filtered:
            url = f"{url}?{urllib.parse.urlencode(filtered)}"
    return url


def build_headers(token: str) -> dict[str, str]:
    if token.lower().startswith("bearer "):
        return {"Accept": "application/json", "Authorization": token}
    return {"Accept": "application/json", "x-api-key": token}


def request_json(path: str, query: Optional[dict[str, Any]] = None) -> Any:
    token = api_key()
    if not token:
        raise RuntimeError("Set XQUIK_API_KEY before using Xquik research.")

    request = urllib.request.Request(build_url(path, query), headers=build_headers(token), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:800]
        raise RuntimeError(f"Xquik API returned HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Xquik API request failed: {exc.reason}") from exc


def tweet_list(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []

    for key in ("tweets", "items", "results", "posts"):
        value = payload.get(key)
        if isinstance(value, list):
            return value

    for key in ("data", "result", "response"):
        nested = tweet_list(payload.get(key))
        if nested:
            return nested

    return []


def first_string(record: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float)):
            return str(value)
    return ""


def first_int(record: dict[str, Any], keys: tuple[str, ...]) -> int:
    for key in keys:
        value = record.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str) and value.strip():
            try:
                return int(value.replace(",", ""))
            except ValueError:
                pass
    return 0


def nested_record(record: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    for key in keys:
        value = record.get(key)
        if isinstance(value, dict):
            return value
    return {}


def normalize_tweet(raw: Any, query: str) -> Optional[dict[str, Any]]:
    if not isinstance(raw, dict):
        return None

    author = nested_record(raw, ("author", "user", "creator"))
    metrics = nested_record(raw, ("metrics", "public_metrics", "stats"))
    tweet_id = first_string(raw, ("id", "id_str", "tweet_id", "tweetId", "rest_id"))
    text = first_string(raw, ("text", "full_text", "content", "body"))
    if not text:
        return None

    username = (
        first_string(raw, ("username", "screen_name", "handle", "author_username"))
        or first_string(author, ("username", "screen_name", "handle", "name"))
    ).lstrip("@")
    url = first_string(raw, ("url", "tweet_url", "permalink"))
    if not url and tweet_id:
        url = f"https://x.com/{username}/status/{tweet_id}" if username else f"https://x.com/i/web/status/{tweet_id}"

    return {
        "id": tweet_id,
        "query": query,
        "author": f"@{username}" if username else "",
        "text": text,
        "url": url,
        "created_at": first_string(raw, ("created_at", "createdAt", "date", "time")),
        "likes": first_int(raw, ("like_count", "favorite_count", "likes", "favorites"))
        or first_int(metrics, ("like_count", "favorite_count", "likes", "favorites")),
        "reposts": first_int(raw, ("retweet_count", "repost_count", "retweets", "reposts"))
        or first_int(metrics, ("retweet_count", "repost_count", "retweets", "reposts")),
        "replies": first_int(raw, ("reply_count", "replies")) or first_int(metrics, ("reply_count", "replies")),
        "quotes": first_int(raw, ("quote_count", "quotes")) or first_int(metrics, ("quote_count", "quotes")),
        "views": first_int(raw, ("view_count", "impression_count", "views", "impressions"))
        or first_int(metrics, ("view_count", "impression_count", "views", "impressions")),
    }


def search_tweets(query: str, limit: int) -> list[dict[str, Any]]:
    payload = request_json("/api/v1/x/tweets/search", {"q": query, "limit": limit})
    normalized = [normalize_tweet(item, query) for item in tweet_list(payload)]
    return [tweet for tweet in normalized if tweet]


def render_markdown(tweets: list[dict[str, Any]], query: str) -> str:
    lines = [
        f"# Xquik Research: {query}",
        "",
        "Use these posts to choose reply, quote, or original-tweet angles. Verify factual claims before publishing.",
        "",
        "| Author | Text | Engagement | URL |",
        "| --- | --- | --- | --- |",
    ]
    if not tweets:
        lines.append("| none | No matching posts returned. |  |  |")
    for tweet in tweets:
        text = str(tweet["text"]).replace("\n", " ").replace("|", "\\|")
        if len(text) > 220:
            text = f"{text[:217].rstrip()}..."
        engagement = " ".join(
            part
            for part in (
                f"likes:{tweet['likes']}" if tweet["likes"] else "",
                f"reposts:{tweet['reposts']}" if tweet["reposts"] else "",
                f"replies:{tweet['replies']}" if tweet["replies"] else "",
                f"views:{tweet['views']}" if tweet["views"] else "",
            )
            if part
        )
        lines.append(f"| {tweet['author'] or 'unknown'} | {text} | {engagement or 'unknown'} | {tweet['url']} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    search = subparsers.add_parser("search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args()

    try:
        tweets = search_tweets(args.query, max(1, min(args.limit, 50)))
        if args.format == "markdown":
            print(render_markdown(tweets, args.query))
        else:
            print(json.dumps({"success": True, "query": args.query, "tweets": tweets}, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
