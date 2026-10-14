# YouTube Channel Finder

A local Python utility for discovering **public** YouTube channels and narrowing them with channel- and video-level filters.

## Recommended launcher: V2.4

Run:

```powershell
python .\youtube_channel_finder_v24.py
```

V2.4 keeps the V2 analysis engine and V2.2 query presets, while reducing `search.list` quota waste.

### V2.4 quota-saving behavior

- completed search tasks are cached in `discovery_cache.json`
- cached tasks are reused on later runs instead of calling YouTube search again
- seed queries can be grouped with YouTube's OR operator
- relevance-only is the default search mode; date-order is an optional second pass
- the script tracks the search calls it makes during the current Pacific-time quota day
- a configurable local daily budget stops new uncached search calls before the chosen threshold
- if YouTube still returns quota exhaustion, the run continues with cached/manual/already-discovered candidates
- public channel/video URLs, `@handles`, and channel IDs can be supplied manually and resolved without `search.list`

The local quota counter is only an estimate. It cannot see search calls made by other programs or websites using the same Google Cloud project/key.

### Suggested V2.4 options

For normal repeated discovery:

```text
Reuse cached completed searches: Y
Refresh cached searches anyway: N
Group seed queries with OR: Y
OR group size: 3
Local daily search-call budget: 90
Manual references: blank unless you already have candidate URLs
Add a second date-order pass: N
```

With the 34-seed `all` preset and OR group size 3, relevance-only needs about 12 search tasks instead of 34. A relevance+date pass needs about 24 instead of 68. Completed tasks are then cached for later runs.

## Query presets

V2.2/V2.4 provide these presets:

- `core` — broad Korean daily-vlog terms
- `daily` — daily life, weekend, routine, and living-alone terms
- `food` — home meal, solo meal, stew, and cooking terms
- `localized` — Japanese-caption/localization-oriented terms
- `all` — balanced mix across the above categories

For broad discovery, start with `all`. For a later targeted pass, use `daily`, `food`, or `localized`.

## Files produced

Every analysis run writes:

- `youtube_channel_matches.csv`
  - only exact matches
- `youtube_channel_diagnostics.csv`
  - discovered candidates, rejection reasons, and near-miss score

V2.4 additionally writes a local cache:

- `discovery_cache.json`
  - cached search results and this script's local quota-day counter
  - ignored by Git via `.gitignore`

## Requirements

- Python 3.9+ recommended
- YouTube Data API v3 key

The program asks for the API key at runtime using a hidden prompt. It does **not** save the key to disk.

## Run on Windows

After cloning once:

```powershell
git pull
python .\youtube_channel_finder_v24.py
```

If `python` is not recognized:

```powershell
py .\youtube_channel_finder_v24.py
```

Paste the YouTube Data API v3 key when prompted. Nothing may appear while pasting because the prompt is intentionally hidden; press Enter afterward.

## Suggested analysis filters

For a broad first pass when remembered values may have moved:

```text
Minimum subscribers: 150
Maximum subscribers: 400
Minimum of channel's MAX long-form views: 1100
Maximum of channel's MAX long-form views: 2200
Long-form minimum duration: 240
Short-like maximum duration: 180
Minimum channel age: 0.5
Maximum channel age: 6
Max recent uploads: 300
Require both long-form and short-like videos: n
regionCode: blank
```

For a stricter follow-up pass, narrow the subscriber and max-long-form-view ranges after inspecting `youtube_channel_diagnostics.csv`.

## Important heuristics / limitations

### Shorts detection

YouTube's public metadata does not provide this tool a simple perfect `isShort` flag for every use case. The analyzer therefore uses a duration heuristic:

- `duration <= short-like maximum` -> short-like candidate
- `duration >= long-form minimum` -> long-form candidate

Treat this as a discovery aid, not a perfect format classifier.

### Long-form maximum

"MAX long-form views" means the highest public view count among the inspected uploads that satisfy the long-form duration rule.

### Search is not exhaustive

YouTube search ranking can omit small channels. OR grouping saves quota, but several terms share one top-results window, so a later targeted preset or an individual-query pass can still uncover additional candidates. The intended workflow is broad cached discovery first, then targeted expansion.

### Channel age vs upload history

Channel age is the channel creation date, not the date the creator began uploading actively. Keep this range wider than your best guess on early passes.

### Localized titles

When YouTube returns localization metadata, the script includes localized titles/descriptions in keyword scoring and reports available localization language codes in the diagnostics CSV.

## Reading rejection reasons

Examples:

- `subscribers_outside_150_400`
- `channel_age_outside_0.5_6.0`
- `max_longform_views_outside_1100_2200`
- `no_longform_by_duration_rule`
- `no_short_like_video_by_duration_rule`
- `subscriber_count_hidden`

A channel can have more than one reason.

## Near-miss score

`closeness_score_lower_is_better` is only a ranking helper. Lower means the channel is numerically closer to the active subscriber/view/age filters. Hard-filter decisions are still shown explicitly in `rejection_reasons`.
