# V2.2 Search Presets

V2.2 adds reusable discovery presets on top of the existing V2 analysis engine.

- `core`: broad Korean daily-vlog terms
- `daily`: daily life, weekend, living-alone, and routine terms
- `food`: home meal, solo meal, stew, and cooking terms
- `localized`: Japanese-caption / localization-oriented terms
- `all`: balanced cross-category mix

The `all` preset is intentionally balanced at 34 seed queries. With both `relevance` and `date` enabled, that means 68 search calls, leaving room for follow-up experiments instead of using the whole daily search budget at once.

## Run V2.2

After pulling the repository:

```powershell
git pull
python .\youtube_channel_finder_v22.py
```

At the preset prompt, press Enter to choose `5. all`. Leave the extra-custom-query prompt blank for the first pass.

The V2.2 launcher then hands the selected query set to the existing V2 engine, so the subscriber, channel-age, long-form-view, diagnostics CSV, and near-miss logic stay unchanged.
