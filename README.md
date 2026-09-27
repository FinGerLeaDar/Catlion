# Catlion 🦁

US stock / ETF social-sentiment dashboard.

## Step 2 — Custom Watchlist

Catlion now has a Watchlist Manager:

- Add ticker
- Remove ticker
- Drag & drop reorder
- Filter: All / Bullish / Neutral / Bearish
- Sort: My order / Sentiment / Bullish % / Bearish % / Messages / Confidence / Ticker
- Search ticker/name
- Export `watchlist.json`

### Important GitHub Pages limitation

The dashboard is a static GitHub Pages site. Changes made in **Manage Watchlist** are stored in the current browser using `localStorage`.

To make the GitHub Actions collector permanently monitor a changed list:

1. Use **Export watchlist.json**.
2. Replace the repository's `watchlist.json`.
3. Run **GitHub Actions → Catlion Daily Update → Run workflow**.

The collector reads `watchlist.json` first, so the next run will monitor the new symbols.

## Architecture

```text
watchlist.json ──┐
                 ├──→ scraper.py ──→ data.json ──→ GitHub Pages
Stocktwits ──────┘
                       ↑
                 Trending discovery
```
