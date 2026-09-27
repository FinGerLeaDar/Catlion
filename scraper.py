import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

DATA_FILE = Path("data.json")
WATCHLIST_FILE = Path("watchlist.json")

ST_BASE = "https://api.stocktwits.com/api/2"
ST_TRENDING = f"{ST_BASE}/trending/symbols/equities.json"
ST_STREAM = f"{ST_BASE}/streams/symbol/{{symbol}}.json"

TRENDING_SYMBOLS = int(os.getenv("TRENDING_SYMBOLS", "10"))
MESSAGES_PER_SYMBOL = min(int(os.getenv("MESSAGES_PER_SYMBOL", "30")), 30)
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "0.25"))

DEFAULT_WATCHLIST = [
    "ONDS", "NVDA", "AMD", "TSLA", "AAPL",
    "MSFT", "AMZN", "META", "GOOGL", "AVGO",
    "PLTR", "SOFI", "RKLB", "SPY", "QQQ",
]

HEADERS = {
    "User-Agent": "Catlion/1.0 (personal US stock sentiment dashboard)",
    "Accept": "application/json",
}

session = requests.Session()
session.headers.update(HEADERS)


def clean_text(value):
    return " ".join(str(value or "").split()).strip()


def normalize_watchlist(values):
    result = []
    seen = set()
    for value in values:
        symbol = clean_text(value).upper()
        if not symbol or symbol in seen or len(symbol) > 10:
            continue
        result.append(symbol)
        seen.add(symbol)
    return result


def load_watchlist():
    env_value = clean_text(os.getenv("WATCHLIST", ""))
    if env_value:
        return normalize_watchlist(env_value.split(","))

    try:
        config = json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
        watchlist = normalize_watchlist(config.get("watchlist", []))
        if watchlist:
            return watchlist
    except Exception as exc:
        print(f"watchlist.json unavailable: {exc}")

    return DEFAULT_WATCHLIST[:]


WATCHLIST = load_watchlist()


def get_json(url, params=None):
    response = session.get(url, params=params or {}, timeout=25)
    response.raise_for_status()
    return response.json()


def fetch_trending_equities():
    payload = get_json(ST_TRENDING, {"limit": 30})
    symbols = []

    for row in payload.get("symbols", []):
        if not isinstance(row, dict):
            continue

        symbol = clean_text(row.get("symbol", "")).upper()
        region = clean_text(row.get("region", "")).upper()
        instrument = clean_text(row.get("instrument_class", "")).lower()

        if not symbol or region != "US":
            continue
        if instrument not in {"stock", "exchangetradedfund"}:
            continue
        if symbol.endswith(".X"):
            continue

        symbols.append({
            "ticker": symbol,
            "name": clean_text(
                row.get("title")
                or (row.get("fundamentals") or {}).get("Name")
                or symbol
            ),
            "exchange": clean_text(row.get("exchange", "")),
            "instrument_class": row.get("instrument_class"),
            "trending_score": row.get("trending_score"),
            "watchlist_count": row.get("watchlist_count"),
            "trend_summary": clean_text((row.get("trends") or {}).get("summary", "")),
            "rank": row.get("rank"),
        })

        if len(symbols) >= TRENDING_SYMBOLS:
            break

    return symbols


def fetch_symbol_messages(symbol):
    payload = get_json(
        ST_STREAM.format(symbol=symbol),
        {"limit": MESSAGES_PER_SYMBOL},
    )
    return payload.get("messages", []), payload.get("symbol", {})


def normalize_sentiment(value):
    value = clean_text(value).lower()
    if value == "bullish":
        return "bullish"
    if value == "bearish":
        return "bearish"
    return "neutral"


def analyze_symbol(meta, messages, discovery_type):
    bullish = bearish = neutral = 0
    cleaned_messages = []

    for message in messages:
        if not isinstance(message, dict):
            continue

        sentiment = normalize_sentiment(
            ((message.get("entities") or {}).get("sentiment") or {}).get("basic")
        )

        if sentiment == "bullish":
            bullish += 1
        elif sentiment == "bearish":
            bearish += 1
        else:
            neutral += 1

        message_id = message.get("id")
        cleaned_messages.append({
            "id": message_id,
            "body": clean_text(message.get("body", "")),
            "created_at": message.get("created_at"),
            "sentiment": sentiment,
            "discussion": bool(message.get("discussion", False)),
            "replies": int(((message.get("conversation") or {}).get("replies") or 0)),
            "likes": int(((message.get("likes") or {}).get("total") or 0)),
            "url": (
                f"https://stocktwits.com/message/{message_id}"
                if message_id
                else f"https://stocktwits.com/symbol/{meta['ticker']}"
            ),
        })

    total = bullish + bearish + neutral
    tagged = bullish + bearish

    if total:
        bullish_pct = round(bullish * 100 / total)
        bearish_pct = round(bearish * 100 / total)
        neutral_pct = 100 - bullish_pct - bearish_pct
    else:
        bullish_pct = bearish_pct = neutral_pct = 0

    score = round((bullish + 0.5 * neutral) * 100 / total, 1) if total else 50.0
    confidence = round(tagged / total, 2) if total else 0.0

    return {
        "ticker": meta["ticker"],
        "name": meta["name"],
        "exchange": meta["exchange"],
        "instrument_class": meta["instrument_class"],
        "discovery": discovery_type,
        "bullish": bullish_pct,
        "neutral": neutral_pct,
        "bearish": bearish_pct,
        "sentiment_score": score,
        "confidence": confidence,
        "mention_count": total,
        "tagged_count": tagged,
        "summary": meta.get("trend_summary", ""),
        "trending_score": meta.get("trending_score"),
        "watchlist_count": meta.get("watchlist_count"),
        "rank": meta.get("rank"),
        "source": "Stocktwits",
        "source_url": f"https://stocktwits.com/symbol/{meta['ticker']}",
        "messages": cleaned_messages,
    }


def load_previous_data():
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_data(data):
    DATA_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main():
    print("Catlion V8 collector starting...")
    print(f"Permanent watchlist: {', '.join(WATCHLIST)}")

    previous = load_previous_data()

    try:
        trending = fetch_trending_equities()
        print(f"Stocktwits trending US symbols: {len(trending)}")
    except Exception as exc:
        print(f"Stocktwits trending unavailable: {exc}")
        trending = []

    candidates = {}

    for symbol in WATCHLIST:
        candidates[symbol] = {
            "ticker": symbol,
            "name": symbol,
            "exchange": "",
            "instrument_class": "",
            "trending_score": None,
            "watchlist_count": None,
            "trend_summary": "",
            "rank": None,
        }

    for meta in trending:
        candidates.setdefault(meta["ticker"], meta)

    for meta in trending:
        if meta["ticker"] in candidates:
            candidates[meta["ticker"]].update(meta)

    candidate_rows = list(candidates.values())
    print(
        f"Total symbols to monitor: {len(candidate_rows)} "
        f"(watchlist={len(WATCHLIST)}, trending={len(trending)})"
    )

    if not candidate_rows:
        preserved = dict(previous)
        preserved["generated_at"] = datetime.now(timezone.utc).isoformat()
        preserved["status"] = "sources_unavailable"
        write_data(preserved)
        return

    stocks = []
    all_items = []

    for index, meta in enumerate(candidate_rows, 1):
        ticker = meta["ticker"]
        discovery = "watchlist" if ticker in WATCHLIST else "trending"

        try:
            messages, symbol_info = fetch_symbol_messages(ticker)

            if symbol_info:
                meta["name"] = clean_text(symbol_info.get("title") or meta["name"])
                meta["exchange"] = clean_text(symbol_info.get("exchange") or meta["exchange"])
                meta["instrument_class"] = (
                    symbol_info.get("instrument_class") or meta["instrument_class"]
                )

            stock = analyze_symbol(meta, messages, discovery)
            stocks.append(stock)

            for message in stock["messages"]:
                all_items.append({
                    "source": "Stocktwits",
                    "ticker": ticker,
                    "discovery": discovery,
                    "title": message["body"][:140],
                    "content_excerpt": message["body"],
                    "url": message["url"],
                    "created_at": message["created_at"],
                    "sentiment": message["sentiment"],
                })

            print(
                f"[{index}/{len(candidate_rows)}] {ticker}: "
                f"{discovery}, messages={len(messages)}, "
                f"bullish={stock['bullish']}%, "
                f"neutral={stock['neutral']}%, "
                f"bearish={stock['bearish']}%"
            )
            time.sleep(REQUEST_DELAY)

        except Exception as exc:
            print(f"{ticker}: stream unavailable: {exc}")

    if not stocks:
        preserved = dict(previous)
        preserved["generated_at"] = datetime.now(timezone.utc).isoformat()
        preserved["status"] = "streams_unavailable"
        write_data(preserved)
        return

    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ok",
        "version": "v8",
        "source_type": "US social sentiment",
        "watchlist": WATCHLIST,
        "sources": {
            "Stocktwits": {
                "status": "api",
                "watchlist_symbols": len(WATCHLIST),
                "trending_symbols": len(trending),
                "monitored_symbols": len(stocks),
                "messages": len(all_items),
            }
        },
        "total_items": len(all_items),
        "items": all_items,
        "stocks": stocks,
    }

    write_data(data)
    print(f"Wrote data.json symbols={len(stocks)} messages={len(all_items)}")


if __name__ == "__main__":
    main()
