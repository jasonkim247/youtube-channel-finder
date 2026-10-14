#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""V2.2 launcher for youtube_channel_finder.py.

Adds reusable discovery query presets without duplicating the V2 analysis engine.
The default `all` preset is intentionally balanced at 34 seed queries so that
relevance+date uses 68 search calls rather than exhausting a 100-call search
budget in one pass.
"""

from __future__ import annotations

import builtins
from typing import Sequence

import youtube_channel_finder as base

CORE = [
    "韓国 vlog",
    "韓国 日常 vlog",
    "韓国人 日常 vlog",
    "韓国女子 日常 vlog",
    "韓国生活 vlog",
    "일상 브이로그",
    "여자 일상 브이로그",
    "한국 일상 브이로그",
]

DAILY = [
    "韓国の日常 vlog",
    "韓国で暮らす vlog",
    "韓国で過ごす一日 vlog",
    "韓国の平凡な日常",
    "韓国で過ごす休日 vlog",
    "韓国 一人暮らし vlog",
    "韓国 おうち時間 vlog",
    "韓国 日常記録",
    "韓国人の休日 vlog",
    "韓国女子の休日 vlog",
    "韓国女子 一人暮らし vlog",
    "자취 브이로그",
    "혼자 사는 일상 브이로그",
    "직장인 브이로그",
]

FOOD = [
    "韓国 おうちごはん",
    "韓国 ひとりごはん",
    "韓国 晩ごはん vlog",
    "韓国 夜ごはん vlog",
    "韓国 ご飯 vlog",
    "韓国 自炊 vlog",
    "韓国 食事 vlog",
    "韓国 料理 vlog",
    "韓国 チゲ vlog",
    "韓国 キムチチゲ vlog",
    "韓国 スンドゥブ vlog",
    "韓国 テンジャンチゲ vlog",
    "韓国 プデチゲ vlog",
    "韓国女子 おうちごはん vlog",
    "韓国女子 ごはん vlog",
    "집밥 브이로그",
    "혼밥 브이로그",
    "먹는 일상 브이로그",
    "찌개 브이로그",
]

LOCALIZED = [
    "日本語字幕 韓国 vlog",
    "韓国 vlog 日本語字幕",
    "韓国 日常 日本語字幕",
    "韓国女子 日本語字幕",
    "韓国人 日本語字幕",
    "韓国生活 日本語字幕",
    "일상 브이로그 일본어 자막",
    "집밥 브이로그 일본어 자막",
    "한국 브이로그 일본어 자막",
]


def dedupe(*groups: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for query in group:
            query = query.strip()
            if query and query not in seen:
                seen.add(query)
                result.append(query)
    return result


# Balanced all: broad enough to mix the useful categories while leaving quota
# headroom when each seed is searched by both relevance and date.
ALL = dedupe(
    CORE,
    [
        "韓国の日常 vlog",
        "韓国で暮らす vlog",
        "韓国で過ごす一日 vlog",
        "韓国の平凡な日常",
        "韓国で過ごす休日 vlog",
        "韓国 一人暮らし vlog",
        "韓国 日常記録",
        "韓国女子の休日 vlog",
        "韓国女子 一人暮らし vlog",
    ],
    [
        "韓国 おうちごはん",
        "韓国 ひとりごはん",
        "韓国 晩ごはん vlog",
        "韓国 夜ごはん vlog",
        "韓国 自炊 vlog",
        "韓国 食事 vlog",
        "韓国 チゲ vlog",
        "韓国 キムチチゲ vlog",
        "韓国 スンドゥブ vlog",
        "韓国 テンジャンチゲ vlog",
        "韓国女子 おうちごはん vlog",
        "韓国女子 ごはん vlog",
        "먹는 일상 브이로그",
    ],
    [
        "日本語字幕 韓国 vlog",
        "韓国 日常 日本語字幕",
        "일상 브이로그 일본어 자막",
        "집밥 브이로그 일본어 자막",
    ],
)

PRESETS = {
    "core": CORE,
    "daily": DAILY,
    "food": FOOD,
    "localized": LOCALIZED,
    "all": ALL,
}


def choose_queries() -> tuple[str, list[str]]:
    print("=" * 78)
    print("YouTube Channel Finder V2.2 query preset launcher")
    print("=" * 78)
    print("  1. core       - broad Korean daily-vlog terms")
    print("  2. daily      - daily life / weekend / living-alone terms")
    print("  3. food       - home meal / solo meal / stew / cooking terms")
    print("  4. localized  - Japanese-caption / localization-oriented terms")
    print(f"  5. all        - balanced mix ({len(ALL)} seeds; recommended)")
    print("  6. custom     - use only your own queries")

    raw = input("Search preset [5]: ").strip().lower()
    mapping = {
        "": "all", "1": "core", "2": "daily", "3": "food",
        "4": "localized", "5": "all", "6": "custom",
        "core": "core", "daily": "daily", "food": "food",
        "localized": "localized", "all": "all", "custom": "custom",
    }
    preset = mapping.get(raw, "all")
    if raw and raw not in mapping:
        print(f"Unknown preset {raw!r}; using all.")

    base_queries = [] if preset == "custom" else list(PRESETS[preset])
    extra = input("Extra custom queries separated by | (blank for none): ").strip()
    extras = [q.strip() for q in extra.split("|") if q.strip()] if extra else []
    queries = dedupe(base_queries, extras)
    if not queries:
        preset = "all"
        queries = list(ALL)
        print("No custom queries entered; falling back to all.")

    print(f"Preset={preset!r}; {len(queries)} seed queries selected.")
    return preset, queries


def main() -> None:
    preset, queries = choose_queries()

    # V2's existing query prompt uses DEFAULT_QUERIES when the user presses
    # Enter. Replace it for this process, then auto-answer that one prompt.
    base.DEFAULT_QUERIES = queries
    base.DEFAULT_SCORE_KEYWORDS = dedupe(
        base.DEFAULT_SCORE_KEYWORDS,
        ["晩ごはん", "夜ごはん", "休日", "一人暮らし", "日本語字幕"],
    )

    original_input = builtins.input

    def routed_input(prompt: str = "") -> str:
        if prompt.startswith("Custom queries separated by |"):
            print(f"{prompt}[V2.2 preset {preset!r} applied automatically]")
            return ""
        return original_input(prompt)

    builtins.input = routed_input
    try:
        base.main()
    finally:
        builtins.input = original_input


if __name__ == "__main__":
    main()
