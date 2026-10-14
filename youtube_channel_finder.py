#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
YouTube Channel Finder V2
=========================

Public-data discovery helper for small YouTube channels.

V2 adds:
- relevance + date seed-search discovery
- rejection diagnostics for every discovered channel
- near-miss ranking when exact matches are empty
- separate CSVs for exact matches and diagnostics
- localized-title keyword scoring when YouTube returns localizations
- conservative quota usage by using uploads playlists instead of per-channel search
- runtime-only API key input (never written to disk)

Uses only Python standard library.
"""

from __future__ import annotations

import csv
import getpass
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, Sequence

API_BASE = "https://www.googleapis.com/youtube/v3"

DEFAULT_QUERIES = [
    "韓国女子 日常 vlog",
    "韓国女子 おうちごはん vlog",
    "韓国女子 ごはん vlog",
    "韓国人 日常 vlog",
    "韓国 日常 vlog",
    "韓国 おうちごはん",
    "韓国 自炊 vlog",
    "韓国 チゲ vlog",
    "韓国 キムチチゲ vlog",
    "韓国 スンドゥブ vlog",
    "日本語字幕 韓国 vlog",
    "일상 브이로그 일본어 자막",
    "집밥 브이로그 일본어 자막",
    "찌개 브이로그",
]

DEFAULT_SCORE_KEYWORDS = [
    "vlog", "브이로그", "일상", "집밥", "혼밥", "찌개", "김치찌개", "된장찌개",
    "순두부", "韓国", "韓国女子", "日常", "ごはん", "おうちごはん", "ひとりごはん",
    "自炊", "食事", "チゲ", "キムチチゲ", "スンドゥブ", "日本語字幕",
]

DEFAULT_SEARCH_ORDERS = ("relevance", "date")


@dataclass(frozen=True)
class Filters:
    sub_min: int
    sub_max: int
    max_views_min: int
    max_views_max: int
    long_min_sec: int
    short_max_sec: int
    min_channel_age: float
    max_channel_age: float
    max_videos: int
    require_both: bool
    region_code: str


def api_get(resource: str, params: dict, api_key: str, retries: int = 3) -> dict:
    params = dict(params)
    params["key"] = api_key
    url = f"{API_BASE}/{resource}?" + urllib.parse.urlencode(params, doseq=True)

    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(
                f"YouTube API HTTP {exc.code}: {body[:1200]}"
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"Network error: {exc}") from exc


def parse_iso8601_duration_seconds(value: str) -> int:
    match = re.fullmatch(
        r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?",
        value or "",
    )
    if not match:
        return 0
    days, hours, minutes, seconds = match.groups()
    return (
        int(days or 0) * 86400
        + int(hours or 0) * 3600
        + int(minutes or 0) * 60
        + int(seconds or 0)
    )


def ask_int(prompt: str, default: int) -> int:
    raw = input(f"{prompt} [{default}]: ").strip()
    return default if not raw else int(raw.replace(",", ""))


def ask_float(prompt: str, default: float) -> float:
    raw = input(f"{prompt} [{default}]: ").strip()
    return default if not raw else float(raw)


def ask_bool(prompt: str, default: bool = True) -> bool:
    suffix = "Y/n" if default else "y/N"
    raw = input(f"{prompt} [{suffix}]: ").strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes", "1", "true"}


def years_since(iso_date: str) -> float:
    dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    return max(0.0, (now - dt).days / 365.2425)


def batched(seq: Iterable[str], n: int = 50) -> Iterator[list[str]]:
    items = list(seq)
    for i in range(0, len(items), n):
        yield items[i:i + n]


def keyword_score(text: str, keywords: Sequence[str]) -> tuple[int, list[str]]:
    lowered = (text or "").lower()
    hits = [kw for kw in keywords if kw.lower() in lowered]
    return len(hits), hits


def range_distance(value: float, low: float, high: float) -> float:
    if low <= value <= high:
        return 0.0
    return (low - value) if value < low else (value - high)


def normalized_distance(value: float, low: float, high: float) -> float:
    span = max(float(high - low), 1.0)
    return range_distance(value, low, high) / span


def collect_search_candidates(
    api_key: str,
    queries: Sequence[str],
    orders: Sequence[str],
    region_code: str = "",
    max_results_per_query: int = 50,
) -> tuple[dict[str, set[str]], dict[str, set[str]], int]:
    found_by: dict[str, set[str]] = defaultdict(set)
    found_orders: dict[str, set[str]] = defaultdict(set)
    search_calls = 0
    total = len(queries) * len(orders)
    step = 0

    for order in orders:
        for query in queries:
            step += 1
            params = {
                "part": "snippet",
                "type": "video",
                "q": query,
                "maxResults": min(50, max_results_per_query),
                "order": order,
            }
            if region_code:
                params["regionCode"] = region_code

            data = api_get("search", params, api_key)
            search_calls += 1

            for item in data.get("items", []):
                snippet = item.get("snippet", {})
                channel_id = snippet.get("channelId")
                if not channel_id:
                    continue
                found_by[channel_id].add(query)
                found_orders[channel_id].add(order)

            print(
                f"[search {step:02d}/{total}] order={order:<9} "
                f"{query!r} -> unique channels: {len(found_by)}"
            )

    return found_by, found_orders, search_calls


def fetch_channels(api_key: str, channel_ids: Iterable[str]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for batch in batched(channel_ids, 50):
        data = api_get(
            "channels",
            {
                "part": "snippet,statistics,contentDetails",
                "id": ",".join(batch),
                "maxResults": 50,
            },
            api_key,
        )
        for item in data.get("items", []):
            result[item["id"]] = item
    return result


def fetch_upload_video_ids(
    api_key: str,
    uploads_playlist_id: str,
    max_videos: int = 300,
) -> list[str]:
    ids: list[str] = []
    page_token = None

    while len(ids) < max_videos:
        params = {
            "part": "contentDetails",
            "playlistId": uploads_playlist_id,
            "maxResults": min(50, max_videos - len(ids)),
        }
        if page_token:
            params["pageToken"] = page_token

        data = api_get("playlistItems", params, api_key)
        for item in data.get("items", []):
            video_id = item.get("contentDetails", {}).get("videoId")
            if video_id:
                ids.append(video_id)

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return ids


def fetch_videos(api_key: str, video_ids: Sequence[str]) -> list[dict]:
    videos: list[dict] = []
    for batch in batched(video_ids, 50):
        data = api_get(
            "videos",
            {
                "part": "snippet,contentDetails,statistics,localizations",
                "id": ",".join(batch),
                "maxResults": 50,
            },
            api_key,
        )
        videos.extend(data.get("items", []))
    return videos


def analyze_channel_videos(
    videos: Sequence[dict],
    long_min_sec: int,
    short_max_sec: int,
    score_keywords: Sequence[str],
) -> dict:
    longforms: list[dict] = []
    shortlikes: list[dict] = []
    total_score = 0
    all_hits: set[str] = set()
    localization_languages: set[str] = set()

    for video in videos:
        duration = parse_iso8601_duration_seconds(
            video.get("contentDetails", {}).get("duration", "")
        )
        stats = video.get("statistics", {})
        views = int(stats.get("viewCount", 0) or 0)
        snippet = video.get("snippet", {})
        title = snippet.get("title", "")
        description = snippet.get("description", "")
        localizations = video.get("localizations", {}) or {}

        text_parts = [title, description]
        for lang, localized in localizations.items():
            localization_languages.add(lang)
            text_parts.extend([
                localized.get("title", ""),
                localized.get("description", ""),
            ])

        score, hits = keyword_score("\n".join(text_parts), score_keywords)
        total_score += score
        all_hits.update(hits)

        row = {
            "video_id": video.get("id", ""),
            "title": title,
            "views": views,
            "duration_sec": duration,
            "url": f"https://www.youtube.com/watch?v={video.get('id', '')}",
            "keyword_score": score,
        }

        if duration >= long_min_sec:
            longforms.append(row)
        if 0 < duration <= short_max_sec:
            shortlikes.append(row)

    longforms.sort(key=lambda item: item["views"], reverse=True)
    shortlikes.sort(key=lambda item: item["views"], reverse=True)

    return {
        "longforms": longforms,
        "shortlikes": shortlikes,
        "max_longform": longforms[0] if longforms else None,
        "keyword_score": total_score,
        "keyword_hits": sorted(all_hits),
        "localized_languages": sorted(localization_languages),
    }


def channel_level_reasons(
    subscribers: int | None,
    age_years: float,
    hidden_subscribers: bool,
    filters: Filters,
) -> list[str]:
    reasons: list[str] = []
    if hidden_subscribers:
        reasons.append("subscriber_count_hidden")
    elif subscribers is None:
        reasons.append("subscriber_count_missing")
    elif not (filters.sub_min <= subscribers <= filters.sub_max):
        reasons.append(f"subscribers_outside_{filters.sub_min}_{filters.sub_max}")

    if not (filters.min_channel_age <= age_years <= filters.max_channel_age):
        reasons.append(
            f"channel_age_outside_{filters.min_channel_age}_{filters.max_channel_age}"
        )
    return reasons


def video_level_reasons(analysis: dict, filters: Filters) -> list[str]:
    reasons: list[str] = []
    max_longform = analysis["max_longform"]

    if not max_longform:
        reasons.append("no_longform_by_duration_rule")
    else:
        max_views = max_longform["views"]
        if not (filters.max_views_min <= max_views <= filters.max_views_max):
            reasons.append(
                f"max_longform_views_outside_{filters.max_views_min}_{filters.max_views_max}"
            )

    if filters.require_both and not analysis["shortlikes"]:
        reasons.append("no_short_like_video_by_duration_rule")

    return reasons


def closeness_score(
    subscribers: int | None,
    age_years: float,
    analysis: dict | None,
    filters: Filters,
) -> float:
    if subscribers is None:
        sub_penalty = 3.0
    else:
        sub_penalty = normalized_distance(subscribers, filters.sub_min, filters.sub_max)

    age_penalty = normalized_distance(
        age_years, filters.min_channel_age, filters.max_channel_age
    )

    if not analysis or not analysis.get("max_longform"):
        view_penalty = 4.0
        both_penalty = 1.0 if filters.require_both else 0.0
        keyword_bonus = 0.0
    else:
        max_views = analysis["max_longform"]["views"]
        view_penalty = normalized_distance(
            max_views, filters.max_views_min, filters.max_views_max
        )
        both_penalty = 0.0 if (not filters.require_both or analysis.get("shortlikes")) else 1.0
        keyword_bonus = min(analysis.get("keyword_score", 0), 20) * 0.01

    return round(
        2.0 * sub_penalty
        + 3.0 * view_penalty
        + 0.5 * age_penalty
        + both_penalty
        - keyword_bonus,
        4,
    )


def join_sorted(values: Iterable[str]) -> str:
    return " | ".join(sorted(set(values)))


def write_csv(path: Path, rows: Sequence[dict], fields: Sequence[str]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_row(
    channel_id: str,
    item: dict,
    found_by: dict[str, set[str]],
    found_orders: dict[str, set[str]],
    filters: Filters,
    analysis: dict | None,
    reasons: Sequence[str],
    uploads_inspected: int,
) -> dict:
    statistics = item.get("statistics", {})
    snippet = item.get("snippet", {})
    hidden = bool(statistics.get("hiddenSubscriberCount"))
    subscribers = None if hidden else int(statistics.get("subscriberCount", 0) or 0)
    age = years_since(snippet.get("publishedAt", "1970-01-01T00:00:00Z"))
    max_longform = analysis.get("max_longform") if analysis else None
    keyword_hits = analysis.get("keyword_hits", []) if analysis else []
    localized_languages = analysis.get("localized_languages", []) if analysis else []
    longforms_found = len(analysis.get("longforms", [])) if analysis else 0
    shortlikes_found = len(analysis.get("shortlikes", [])) if analysis else 0

    return {
        "closeness_score_lower_is_better": closeness_score(subscribers, age, analysis, filters),
        "status": "MATCH" if not reasons else "REJECTED",
        "rejection_reasons": " | ".join(reasons),
        "channel_title": snippet.get("title", ""),
        "channel_id": channel_id,
        "channel_url": f"https://www.youtube.com/channel/{channel_id}",
        "subscribers": "" if subscribers is None else subscribers,
        "subscriber_count_hidden": hidden,
        "channel_age_years": round(age, 2),
        "country_metadata": snippet.get("country", ""),
        "video_count_reported": int(statistics.get("videoCount", 0) or 0),
        "uploads_inspected": uploads_inspected,
        "longforms_found": longforms_found,
        "shortlikes_found": shortlikes_found,
        "max_longform_views": "" if not max_longform else max_longform["views"],
        "max_longform_title": "" if not max_longform else max_longform["title"],
        "max_longform_url": "" if not max_longform else max_longform["url"],
        "matched_seed_queries": join_sorted(found_by.get(channel_id, set())),
        "surfaced_by_orders": join_sorted(found_orders.get(channel_id, set())),
        "keyword_hits": join_sorted(keyword_hits),
        "localized_languages": join_sorted(localized_languages),
    }


def main() -> None:
    print("=" * 78)
    print("YouTube Channel Finder V2")
    print("=" * 78)
    print("The API key is used only for this run and is never written to disk.")
    api_key = getpass.getpass("YouTube Data API v3 key: ").strip()
    if not api_key:
        print("No API key entered.")
        sys.exit(1)

    print("\n--- Filters ---")
    filters = Filters(
        sub_min=ask_int("Minimum subscribers", 150),
        sub_max=ask_int("Maximum subscribers", 400),
        max_views_min=ask_int("Minimum of channel's MAX long-form views", 1100),
        max_views_max=ask_int("Maximum of channel's MAX long-form views", 2200),
        long_min_sec=ask_int("Long-form minimum duration (seconds)", 240),
        short_max_sec=ask_int("Short-like maximum duration (seconds, heuristic)", 180),
        min_channel_age=ask_float("Minimum channel age (years)", 0.5),
        max_channel_age=ask_float("Maximum channel age (years)", 6.0),
        max_videos=ask_int("Max recent uploads to inspect per channel", 300),
        require_both=ask_bool("Require both long-form and short-like videos", False),
        region_code=input("YouTube regionCode (blank recommended; KR if desired) []: ").strip().upper(),
    )

    print("\n--- Discovery ---")
    use_date = ask_bool("Search each seed with BOTH relevance and date order", True)
    orders = DEFAULT_SEARCH_ORDERS if use_date else ("relevance",)

    print("\n--- Search queries ---")
    print("Press Enter to use the built-in Korean/Japanese vlog/food query set.")
    custom = input("Custom queries separated by | : ").strip()
    queries = [q.strip() for q in custom.split("|") if q.strip()] if custom else DEFAULT_QUERIES

    expected_search_calls = len(queries) * len(orders)
    print(
        f"\nUsing {len(queries)} seed queries x {len(orders)} order(s) "
        f"= {expected_search_calls} search calls."
    )
    print("Discovery starts now.\n")

    found_by, found_orders, search_calls = collect_search_candidates(
        api_key,
        queries,
        orders=orders,
        region_code=filters.region_code,
        max_results_per_query=50,
    )

    print(f"\nUnique candidate channels discovered: {len(found_by)}")
    print("Fetching channel metadata...")
    channels = fetch_channels(api_key, found_by.keys())

    diagnostics: list[dict] = []
    analyze_queue: list[tuple[str, dict, str]] = []

    for channel_id, item in channels.items():
        stats = item.get("statistics", {})
        snippet = item.get("snippet", {})
        hidden = bool(stats.get("hiddenSubscriberCount"))
        subscribers = None if hidden else int(stats.get("subscriberCount", 0) or 0)
        age = years_since(snippet.get("publishedAt", "1970-01-01T00:00:00Z"))
        reasons = channel_level_reasons(subscribers, age, hidden, filters)
        uploads = item.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads", "")

        if reasons or not uploads:
            if not uploads:
                reasons = list(reasons) + ["uploads_playlist_missing"]
            diagnostics.append(
                build_row(
                    channel_id=channel_id,
                    item=item,
                    found_by=found_by,
                    found_orders=found_orders,
                    filters=filters,
                    analysis=None,
                    reasons=reasons,
                    uploads_inspected=0,
                )
            )
        else:
            analyze_queue.append((channel_id, item, uploads))

    print(
        f"Channels passing subscriber + age prefilters: "
        f"{len(analyze_queue)} / {len(channels)}"
    )

    for idx, (channel_id, item, uploads_playlist) in enumerate(analyze_queue, 1):
        stats = item.get("statistics", {})
        title = item.get("snippet", {}).get("title", "")
        subs = int(stats.get("subscriberCount", 0) or 0)
        print(f"[analyze {idx:03d}/{len(analyze_queue)}] {title} ({subs} subs)")

        video_ids = fetch_upload_video_ids(
            api_key,
            uploads_playlist,
            max_videos=filters.max_videos,
        )
        videos = fetch_videos(api_key, video_ids)
        analysis = analyze_channel_videos(
            videos,
            long_min_sec=filters.long_min_sec,
            short_max_sec=filters.short_max_sec,
            score_keywords=DEFAULT_SCORE_KEYWORDS,
        )
        reasons = video_level_reasons(analysis, filters)

        diagnostics.append(
            build_row(
                channel_id=channel_id,
                item=item,
                found_by=found_by,
                found_orders=found_orders,
                filters=filters,
                analysis=analysis,
                reasons=reasons,
                uploads_inspected=len(videos),
            )
        )

    diagnostics.sort(
        key=lambda row: (
            row["status"] != "MATCH",
            float(row["closeness_score_lower_is_better"]),
            str(row["channel_title"]).lower(),
        )
    )
    matches = [row for row in diagnostics if row["status"] == "MATCH"]

    fields = [
        "closeness_score_lower_is_better",
        "status",
        "rejection_reasons",
        "channel_title",
        "channel_url",
        "subscribers",
        "subscriber_count_hidden",
        "channel_age_years",
        "country_metadata",
        "video_count_reported",
        "uploads_inspected",
        "longforms_found",
        "shortlikes_found",
        "max_longform_views",
        "max_longform_title",
        "max_longform_url",
        "matched_seed_queries",
        "surfaced_by_orders",
        "keyword_hits",
        "localized_languages",
        "channel_id",
    ]

    out_dir = Path.cwd()
    matches_path = out_dir / "youtube_channel_matches.csv"
    diagnostics_path = out_dir / "youtube_channel_diagnostics.csv"

    write_csv(matches_path, matches, fields)
    write_csv(diagnostics_path, diagnostics, fields)

    print("\n" + "=" * 78)
    print(f"Search calls used by this run: {search_calls}")
    print(f"Discovered channels: {len(found_by)}")
    print(f"Exact matches: {len(matches)}")
    print(f"Matches CSV:      {matches_path}")
    print(f"Diagnostics CSV:  {diagnostics_path}")
    print("=" * 78)

    if matches:
        print("\nExact matches:")
        for idx, row in enumerate(matches[:20], 1):
            print(
                f"{idx:2d}. {row['channel_title']} | "
                f"{row['subscribers']} subs | "
                f"max long-form {int(row['max_longform_views']):,} views"
            )
            print(f"    {row['channel_url']}")
            print(f"    {row['max_longform_title']}")
            print(f"    {row['max_longform_url']}")
    else:
        print("\nNo exact matches. Closest analyzed / discovered candidates:")
        near = diagnostics[:20]
        for idx, row in enumerate(near, 1):
            views = row["max_longform_views"]
            views_text = f"{int(views):,}" if views != "" else "not analyzed"
            print(
                f"{idx:2d}. {row['channel_title']} | "
                f"subs={row['subscribers'] or 'hidden'} | "
                f"max-long={views_text} | "
                f"score={row['closeness_score_lower_is_better']}"
            )
            print(f"    rejected: {row['rejection_reasons'] or '-'}")
            print(f"    {row['channel_url']}")

        print("\nNext-step suggestions:")
        print("  1) Inspect youtube_channel_diagnostics.csv first.")
        print("  2) If close channels miss only the view range, widen that range.")
        print("  3) If few channels pass subscriber/age prefilters, widen those first.")
        print("  4) If discovery still looks thin, add broader seed queries.")
        print("  5) Keep regionCode blank for the broadest first pass.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
    except Exception as exc:
        print(f"\nERROR: {exc}")
        sys.exit(1)
