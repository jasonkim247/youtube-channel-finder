#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""YouTube Channel Finder V2.3 launcher.

V2.3 keeps the V2.2 search presets but makes discovery resilient to YouTube's
daily search-list quota. If the API returns a quota-exhausted / HTTP 429 error
mid-search, the program stops issuing search calls and continues analyzing the
candidate channels already collected in memory instead of crashing and losing
the run.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Sequence

import youtube_channel_finder as base
import youtube_channel_finder_v22 as presets


def resilient_collect_search_candidates(
    api_key: str,
    queries: Sequence[str],
    orders: Sequence[str],
    region_code: str = "",
    max_results_per_query: int = 50,
):
    found_by: dict[str, set[str]] = defaultdict(set)
    found_orders: dict[str, set[str]] = defaultdict(set)
    search_calls = 0
    total = len(queries) * len(orders)
    step = 0

    quota_exhausted = False

    for order in orders:
        if quota_exhausted:
            break

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

                quota_exhausted = True
                print("\n" + "!" * 78)
                print("YouTube search quota was exhausted during discovery.")
                print(
                    f"Completed {search_calls} search call(s) in this run before the limit."
                )
                print(
                    f"Keeping {len(found_by)} candidate channel(s) collected so far and "
                    "continuing with channel/video analysis instead of aborting."
                )
                print("The unfinished seed searches will simply be skipped for this run.")
                print("!" * 78 + "\n")
                break

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


def main() -> None:
    base.collect_search_candidates = resilient_collect_search_candidates
    presets.main()


if __name__ == "__main__":
    main()
