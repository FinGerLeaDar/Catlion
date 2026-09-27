# Catlion 🦁

US stock social-sentiment dashboard.

## Current architecture

```text
Stocktwits → US trending stocks / ETFs → recent messages → Bullish/Bearish/untagged statistics → data.json → GitHub Pages
```

PTT / Dcard are no longer used because Catlion is focused on US stocks / ETFs.

The collector uses Stocktwits' public API endpoints for trending equities and recent symbol streams. Untagged messages are shown separately as「未標記」rather than being treated as confirmed bullish or bearish.

GitHub Actions can be started manually from **Actions → Catlion Daily Update → Run workflow** or run on the daily schedule.

If Stocktwits access fails, the script preserves the previous `data.json` instead of replacing it with an empty dataset.
