# Catlion 🦁

US stock / ETF social-sentiment dashboard.

## V7 architecture

```text
                         Stocktwits
                             │
              ┌──────────────┴──────────────┐
              │                             │
       Fixed Watchlist               Trending discovery
              │                             │
              └──────────────┬──────────────┘
                             ↓
                    recent symbol messages
                             ↓
                Bullish / Bearish / untagged
                             ↓
                         data.json
                             ↓
                      GitHub Pages
```

### Fixed Watchlist

The default list is:

`ONDS, NVDA, AMD, TSLA, AAPL, MSFT, AMZN, META, GOOGL, AVGO, PLTR, SOFI, RKLB, SPY, QQQ`

The workflow passes this list through the `WATCHLIST` environment variable, so it can be edited without changing Python.

### Trending discovery

Catlion also collects up to 10 US trending symbols. If a trending symbol is not already in the Watchlist, it is added as a discovery candidate for that run.

This means a ticker can be monitored for two reasons:

- `watchlist` — permanently requested
- `trending` — discovered from Stocktwits trending symbols

## Sentiment

Catlion reads the sentiment tag attached to each Stocktwits message.

- `bullish` → Bullish
- `bearish` → Bearish
- anything else / no tag → 未標記

Untaged messages are **not** treated as confirmed bullish or bearish.

## GitHub Actions

Run manually:

**GitHub → Actions → Catlion Daily Update → Run workflow**

The scheduled run is daily.

The collector preserves the previous `data.json` if no symbol streams can be collected.

## Important API note

Stocktwits currently says its developer APIs are under review and new developer registrations are not being accepted. The current Catlion collector therefore relies on the public endpoints that were successfully working for this repository's Run #6; if Stocktwits changes access, the workflow may need another source or authenticated integration.

## Files

- `scraper.py` — Stocktwits collector
- `data.json` — generated data
- `app.js` — dashboard rendering/search
- `index.html` — page structure
- `style.css` — dashboard styling
- `.github/workflows/daily.yml` — scheduled collector
