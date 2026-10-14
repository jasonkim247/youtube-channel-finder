#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""YouTube Channel Finder V2.4 launcher.

V2.4 reduces search-list quota waste by:
- caching completed search tasks on disk and reusing them on later runs
- optionally grouping seed queries with YouTube's OR operator
- defaulting the old "relevance + date" prompt to relevance-only
- tracking search calls made by this script for the current Pacific-time quota day
- stopping before a configurable local daily budget
- accepting public channel/video references that can be resolved without search.list
- keeping V2.3's graceful behavior when the API itself reports quota exhaustion

The local quota counter is only an estimate: it cannot see calls made by other
programs or websites that use the same Google Cloud project/key.
"""

from __future__ import annotations

import builtins
import json
import re
import urllib.parse
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence
from zoneinfo import ZoneInfo

import youtube_channel_finder as base
import youtube_channel_finder_v22 as presets

CACHE_PATH = Path(__file__).with_name("discovery_cache.json")
CACHE_VERSION = 1

CONFIG = {
    "use_cache": True,
    "refresh_cache": False,
    "use_or_grouping": True,
    "or_group_size": 3,
    "daily_budget": 90,
    "manual_refs": [],
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def pacific_quota_day() -> str:
    return datetime.now(ZoneInfo("America/Los_Angeles")).date().isoformat()


def empty_cache() -> dict:
    return {
        "version": CACHE_VERSION,
        "searches": {},
        "quota_tracking": {},
    }


def load_cache() -> dict:
    if not CONFIG["use_cache"] or not CACHE_PATH.exists():
        return empty_cache()
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_cache()

    if not isinstance(data, dict):
        return empty_cache()
    data.setdefault("version", CACHE_VERSION)
    data.setdefault("searches", {})
    data.setdefault("quota_tracking", {})
    return data


def save_cache(cache: dict) -> None:
    if not CONFIG["use_cache"]:
        return
    tmp = CACHE_PATH.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    tmp.replace(CACHE_PATH)


def cache_key(query: str, order: str, region_code: str) -> str:
    return json.dumps(
        [query, order, region_code or ""],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def tracked_calls(cache: dict) -> int:
    day = pacific_quota_day()
    entry = cache.setdefault("quota_tracking", {}).setdefault(day, {"search_calls": 0})
    return int(entry.get("search_calls", 0) or 0)


def increment_tracked_calls(cache: dict, amount: int = 1) -> None:
    day = pacific_quota_day()
    entry = cache.setdefault("quota_tracking", {}).setdefault(day, {"search_calls": 0})
    entry["search_calls"] = int(entry.get("search_calls", 0) or 0) + amount
    entry["updated_at"] = now_iso()


def chunked(seq: Sequence[str], size: int) -> Iterable[list[str]]:
    size = max(1, int(size))
    for i in range(0, len(seq), size):
        yield list(seq[i:i + size])


def make_search_queries(queries: Sequence[str]) -> list[tuple[str, list[str]]]:
    clean = []
    seen = set()
    for q in queries:
        q = q.strip()
        if q and q not in seen:
            seen.add(q)
            clean.append(q)

    if not CONFIG["use_or_grouping"]:
        return [(q, [q]) for q in clean]

    size = max(2, int(CONFIG["or_group_size"]))
    tasks = []
    for group in chunked(clean, size):
        tasks.append(("|".join(group), group))
    return tasks


def add_candidate(
    channel_id: str,
    source_label: str,
    order_label: str,
    found_by: dict[str, set[str]],
    found_orders: dict[str, set[str]],
) -> None:
    if not channel_id:
        return
    found_by[channel_id].add(source_label)
    found_orders[channel_id].add(order_label)


def channel_ids_from_search_data(data: dict) -> list[str]:
    out = []
    seen = set()
    for item in data.get("items", []):
        channel_id = item.get("snippet", {}).get("channelId")
        if channel_id and channel_id not in seen:
            seen.add(channel_id)
            out.append(channel_id)
    return out


def extract_video_id(text: str) -> str | None:
    text = text.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", text):
        return text

    try:
        parsed = urllib.parse.urlparse(text)
    except ValueError:
        return None

    host = parsed.netloc.lower()
    path = parsed.path.strip("/")

    if host in {"youtu.be", "www.youtu.be"}:
        candidate = path.split("/", 1)[0]
        return candidate if re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate) else None

    if "youtube.com" in host:
        if path == "watch":
            candidate = urllib.parse.parse_qs(parsed.query).get("v", [""])[0]
            return candidate if re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate) else None
        match = re.match(r"(?:shorts|live|embed)/([A-Za-z0-9_-]{11})", path)
        if match:
            return match.group(1)

    return None


def resolve_manual_ref(api_key: str, ref: str) -> tuple[str | None, str]:
    raw = ref.strip()
    if not raw:
        return None, "empty"

    direct = re.search(r"(?:youtube\.com/)?channel/(UC[A-Za-z0-9_-]+)", raw)
    if direct:
        return direct.group(1), "channel-url"

    if re.fullmatch(r"UC[A-Za-z0-9_-]+", raw):
        return raw, "channel-id"

    video_id = extract_video_id(raw)
    if video_id:
        data = base.api_get(
            "videos",
            {"part": "snippet", "id": video_id, "maxResults": 1},
            api_key,
        )
        items = data.get("items", [])
        if items:
            return items[0].get("snippet", {}).get("channelId"), "video-url"
        return None, "video-not-found"

    handle_match = re.search(r"(?:youtube\.com/)?@([A-Za-z0-9._-]+)", raw)
    if handle_match:
        handle = handle_match.group(1)
        data = base.api_get(
            "channels",
            {"part": "id,snippet", "forHandle": handle, "maxResults": 1},
            api_key,
        )
        items = data.get("items", [])
        if items:
            return items[0].get("id"), "handle"
        return None, "handle-not-found"

    user_match = re.search(r"youtube\.com/user/([^/?#]+)", raw)
    if user_match:
        username = urllib.parse.unquote(user_match.group(1))
        data = base.api_get(
            "channels",
            {"part": "id,snippet", "forUsername": username, "maxResults": 1},
            api_key,
        )
        items = data.get("items", [])
        if items:
            return items[0].get("id"), "username"
        return None, "username-not-found"

    return None, "unsupported-ref"


def efficient_collect_search_candidates(
    api_key: str,
    queries: Sequence[str],
    orders: Sequence[str],
    region_code: str = "",
    max_results_per_query: int = 50,
):
    found_by: dict[str, set[str]] = defaultdict(set)
    found_orders: dict[str, set[str]] = defaultdict(set)
    cache = load_cache()

    grouped_queries = make_search_queries(queries)
    tasks = [(order, q, members) for order in orders for q, members in grouped_queries]

    cached_count = 0
    api_calls_this_run = 0
    skipped_for_budget = 0
    stop_new_calls = False

    tracked_before = tracked_calls(cache)
    local_budget = max(1, int(CONFIG["daily_budget"]))

    print("\n" + "-" * 78)
    print("V2.4 quota-efficient discovery")
    print("-" * 78)
    print(
        f"Seed queries: {len(queries)} -> search tasks per order: {len(grouped_queries)} "
        f"(OR grouping={'on' if CONFIG['use_or_grouping'] else 'off'})"
    )
    print(
        f"Orders: {', '.join(orders)} | planned tasks: {len(tasks)} | "
        f"local tracked calls today: {tracked_before}/{local_budget}"
    )
    if CONFIG["use_cache"]:
        print(
            "Cache is ON"
            + (" (refresh requested)" if CONFIG["refresh_cache"] else " (reuse completed searches)")
        )
    else:
        print("Cache is OFF")

    for step, (order, query, members) in enumerate(tasks, 1):
        key = cache_key(query, order, region_code)
        cached = cache.get("searches", {}).get(key)

        if cached and not CONFIG["refresh_cache"]:
            channel_ids = list(cached.get("channel_ids", []))
            for channel_id in channel_ids:
                add_candidate(
                    channel_id,
                    " || ".join(members),
                    order,
                    found_by,
                    found_orders,
                )
            cached_count += 1
            print(
                f"[cache {step:02d}/{len(tasks)}] order={order:<9} "
                f"{query!r} -> {len(channel_ids)} channels; unique={len(found_by)}"
            )
            continue

        if stop_new_calls:
            skipped_for_budget += 1
            continue

        used = tracked_calls(cache)
        if used >= local_budget:
            stop_new_calls = True
            skipped_for_budget += 1
            print(
                f"\nLocal search-call budget reached ({used}/{local_budget}). "
                "No more uncached search.list calls will be made this run."
            )
            continue

        params = {
            "part": "snippet",
            "type": "video",
            "q": query,
            "maxResults": min(50, max_results_per_query),
            "order": order,
        }
        if region_code:
            params["regionCode"] = region_code

        try:
            data = base.api_get("search", params, api_key)
        except RuntimeError as exc:
            message = str(exc)
            quota_error = (
                "HTTP 429" in message
                or "Quota exceeded" in message
                or "RESOURCE_EXHAUSTED" in message
                or "RATE_LIMIT_EXCEEDED" in message
                or "rateLimitExceeded" in message
            )
            if not quota_error:
                raise

            stop_new_calls = True
            print("\n" + "!" * 78)
            print("YouTube search quota is exhausted for the current project/day.")
            print(
                "V2.4 will keep cached/manual candidates and any candidates already "
                "collected in this run, then continue with analysis."
            )
            print("!" * 78)
            continue

        api_calls_this_run += 1
        increment_tracked_calls(cache, 1)
        channel_ids = channel_ids_from_search_data(data)

        if CONFIG["use_cache"]:
            cache.setdefault("searches", {})[key] = {
                "query": query,
                "members": list(members),
                "order": order,
                "region_code": region_code,
                "channel_ids": channel_ids,
                "saved_at": now_iso(),
            }
            save_cache(cache)

        for channel_id in channel_ids:
            add_candidate(
                channel_id,
                " || ".join(members),
                order,
                found_by,
                found_orders,
            )

        print(
            f"[api   {step:02d}/{len(tasks)}] order={order:<9} "
            f"{query!r} -> {len(channel_ids)} channels; unique={len(found_by)}"
        )

    manual_added = 0
    for ref in CONFIG["manual_refs"]:
        try:
            channel_id, kind = resolve_manual_ref(api_key, ref)
        except RuntimeError as exc:
            print(f"[manual] {ref!r} -> API error: {exc}")
            continue

        if channel_id:
            add_candidate(channel_id, f"[manual] {ref}", "manual", found_by, found_orders)
            manual_added += 1
            print(f"[manual] {ref!r} -> {channel_id} ({kind})")
        else:
            print(f"[manual] {ref!r} -> could not resolve ({kind})")

    save_cache(cache)

    print("\nV2.4 discovery summary")
    print(f"  cached search tasks reused: {cached_count}")
    print(f"  new search.list calls this run: {api_calls_this_run}")
    print(f"  uncached tasks skipped after limit/budget: {skipped_for_budget}")
    print(f"  manual references added: {manual_added}")
    print(f"  unique candidate channels available: {len(found_by)}")
    print(
        f"  locally tracked calls for Pacific quota day {pacific_quota_day()}: "
        f"{tracked_calls(cache)}/{local_budget}"
    )
    print(
        "  Note: the local counter cannot see search calls made outside this script."
    )

    return found_by, found_orders, api_calls_this_run


def ask_v24_options() -> None:
    print("=" * 78)
    print("YouTube Channel Finder V2.4 - quota-efficient mode")
    print("=" * 78)

    raw = input("Reuse cached completed searches [Y/n]: ").strip().lower()
    CONFIG["use_cache"] = raw not in {"n", "no", "0", "false"}

    if CONFIG["use_cache"]:
        raw = input("Refresh cached searches anyway [y/N]: ").strip().lower()
        CONFIG["refresh_cache"] = raw in {"y", "yes", "1", "true"}
    else:
        CONFIG["refresh_cache"] = False

    raw = input("Group seed queries with OR to save search quota [Y/n]: ").strip().lower()
    CONFIG["use_or_grouping"] = raw not in {"n", "no", "0", "false"}

    if CONFIG["use_or_grouping"]:
        raw = input("OR group size [3]: ").strip()
        if raw:
            CONFIG["or_group_size"] = max(2, min(5, int(raw)))

    raw = input("Local daily search-call budget [90]: ").strip()
    if raw:
        CONFIG["daily_budget"] = max(1, min(100, int(raw)))

    print(
        "Optional: paste public YouTube channel/video URLs, @handles, or channel IDs.\n"
        "Separate multiple entries with |. These are resolved without search.list."
    )
    raw = input("Manual references (blank for none): ").strip()
    CONFIG["manual_refs"] = [part.strip() for part in raw.split("|") if part.strip()]

    print(
        "\nV2.4 recommendation: when the older prompt asks whether to search BOTH "
        "relevance and date, press Enter; V2.4 changes that prompt's default to NO "
        "(relevance only). Add date only for a deliberate second pass."
    )


def main() -> None:
    ask_v24_options()
    base.collect_search_candidates = efficient_collect_search_candidates

    original_input = builtins.input

    def routed_input(prompt: str = "") -> str:
        if prompt.startswith("Search each seed with BOTH relevance and date order"):
            raw = original_input(
                "Add a second date-order pass too? (relevance-only is recommended) [y/N]: "
            ).strip()
            if not raw:
                return "n"
            return "y" if raw.lower() in {"y", "yes", "1", "true"} else "n"
        return original_input(prompt)

    builtins.input = routed_input
    try:
        presets.main()
    finally:
        builtins.input = original_input


if __name__ == "__main__":
    main()
