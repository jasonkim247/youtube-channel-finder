# YouTube Channel Finder

A local Python utility for discovering **public** YouTube channels and narrowing them with channel- and video-level filters.

## V2 highlights

V2 was built to make zero-result runs useful instead of opaque:

- searches every seed query by **relevance + upload date** by default
- filters by subscriber count and channel age
- analyzes each surviving channel's uploads playlist
- calculates the channel's **highest-viewed long-form candidate**
- can check whether both long-form and short-like videos exist
- scores Korean/Japanese vlog, food, home-meal, stew, and localization keywords
- exports **exact matches**
- exports **all discovered candidates with rejection reasons**
- prints the nearest candidates when no exact match survives

No third-party Python package is required.

## Files produced

Every run writes:

- `youtube_channel_matches.csv`
  - only exact matches
- `youtube_channel_diagnostics.csv`
  - every discovered channel, including rejection reasons and near-miss score

The diagnostics file is the important V2 addition.

## Requirements

- Python 3.9+ recommended
- YouTube Data API v3 key

The program asks for the API key at runtime using a hidden prompt. It does **not** save the key to disk.

## Run on Windows

Open PowerShell in this repository folder:

```powershell
python .\youtube_channel_finder.py
```

If `python` is not recognized:

```powershell
py .\youtube_channel_finder.py
```

Paste the YouTube Data API v3 key when prompted. Nothing may appear while pasting because the prompt is intentionally hidden; press Enter afterward.

## Suggested first-pass settings

For a small channel where the remembered numbers may have moved since the conversation:

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
Search each seed with BOTH relevance and date order: y
```

For a stricter follow-up pass, narrow the subscriber and max-long-form-view ranges after inspecting `youtube_channel_diagnostics.csv`.

## Important heuristics / limitations

### Shorts detection

YouTube's public metadata does not give this script a simple perfect `isShort` flag for every use case. V2 therefore uses a duration heuristic:

- `duration <= short-like maximum` -> short-like candidate
- `duration >= long-form minimum` -> long-form candidate

Treat this as a discovery aid, not a perfect format classifier.

### Long-form maximum

"MAX long-form views" means:

> Among the uploads inspected for one channel, take the long-form candidate with the highest public view count.

That value is then compared with the min/max range entered at startup.

### Search is not exhaustive

YouTube search ranking can omit small channels. V2 improves recall by running each seed query twice by default:

- `order=relevance`
- `order=date`

This broadens discovery, but it still cannot guarantee that every matching public channel is surfaced.

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

`closeness_score_lower_is_better` is only a ranking helper.

Lower means the channel is numerically closer to the active subscriber/view/age filters. Hard-filter decisions are still shown explicitly in `rejection_reasons`.

## Git workflow

After cloning once:

```powershell
git pull
python .\youtube_channel_finder.py
```

Generated CSV files and local secrets are ignored by `.gitignore`.
