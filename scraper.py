import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

DATA_FILE = Path("data.json")
MAX_ITEMS = int(os.getenv("MAX_ITEMS", "80"))
ARTICLE_FETCH_LIMIT = int(os.getenv("ARTICLE_FETCH_LIMIT", "35"))
ARTICLE_MAX_CHARS = int(os.getenv("ARTICLE_MAX_CHARS", "5000"))

PTT_OFFICIAL = "https://www.ptt.cc/bbs/Stock/index.html"
PTT_MIRROR = "https://www.pttweb.cc/bbs/Stock"

DCARD_ENDPOINTS = [
    "https://www.dcard.tw/service/api/v2/forums/stock/posts",
    "https://www.dcard.tw/_api/forums/stock/posts",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/153.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.7",
    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
}

# Board/admin threads that should not enter stock sentiment analysis.
EXCLUDE_PATTERNS = [
    "分頁",
    "[公告]",
    "公告]",
    "置底",
    "板規",
    "水桶",
    "交易工具異常回報",
    "交易軟體、APP異常回報",
    "異常回報區",
]

# Common ETF names. Do not ask Gemini to invent these.
SYMBOL_NAMES = {
    "0050": "元大台灣50",
    "00631L": "元大台灣50正2",
    "00878": "國泰永續高股息",
    "00919": "群益台灣精選高息",
    "00929": "復華台灣科技優息",
    "00713": "元大台灣高息低波",
    "006208": "富邦台50",
    "SPY": "SPDR S&P 500 ETF Trust",
    "SPYI": "NEOS S&P 500 High Income ETF",
    "QQQ": "Invesco QQQ",
    "VOO": "Vanguard S&P 500 ETF",
    "VT": "Vanguard Total World Stock ETF",
}

# Known Taiwan stock names that are useful when the title contains the company name
# but not the numeric ticker. This is deliberately small; Gemini must not invent
# a ticker that is not present or clearly identifiable in the source.
KNOWN_NAMES = {
    "台積電": "2330",
    "鴻海": "2317",
    "聯發科": "2454",
    "群創": "3481",
    "旺宏": "2337",
    "生達": "1720",
    "邦特": "4107",
    "儒鴻": "1476",
    "宏全": "9939",
    "百一": "6152",
    "宏碁": "2353",
    "漢翔": "2634",
    "南亞科": "2408",
    "華邦電": "2344",
    "聯電": "2303",
    "國巨": "2327",
    "欣興": "3037",
    "友達": "2409",
    "台達電": "2308",
}

session = requests.Session()
session.headers.update(HEADERS)


def clean_text(text):
    text = re.sub(r"\s+", " ", text or "").strip()
    return text


def should_exclude(title):
    t = clean_text(title)
    return any(p in t for p in EXCLUDE_PATTERNS)


def dedupe_items(items):
    seen = set()
    out = []
    for item in items:
        key = item.get("url") or item.get("title", "")
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def parse_ptt_list(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    items = []

    # PTT official HTML
    for row in soup.select("div.r-ent"):
        a = row.select_one("div.title a")
        if not a:
            continue
        title = clean_text(a.get_text(" ", strip=True))
        url = urljoin(base_url, a.get("href", ""))
        if title and url and not should_exclude(title):
            items.append({"source": "PTT", "title": title, "url": url})

    # PTTWeb mirror
    if not items:
        for a in soup.select("a[href*='/bbs/Stock/']"):
            title = clean_text(a.get_text(" ", strip=True))
            href = a.get("href", "")
            if not title or not href:
                continue
            if "/bbs/Stock/M." not in href:
                continue
            if should_exclude(title):
                continue
            url = urljoin(base_url, href)
            items.append({"source": "PTT", "title": title, "url": url})

    return dedupe_items(items)


def fetch_ptt():
    # Try official PTT first.
    try:
        r = session.get(
            PTT_OFFICIAL,
            timeout=20,
            cookies={"over18": "1"},
        )
        r.raise_for_status()
        items = parse_ptt_list(r.text, PTT_OFFICIAL)
        if items:
            return items[:MAX_ITEMS], "ptt_official"
    except Exception as exc:
        print(f"PTT official unavailable: {exc}")

    # GitHub Actions frequently gets blocked by PTT, so use PTTWeb as fallback.
    try:
        r = session.get(PTT_MIRROR, timeout=20)
        r.raise_for_status()
        items = parse_ptt_list(r.text, PTT_MIRROR)
        if items:
            return items[:MAX_ITEMS], "pttweb_mirror"
    except Exception as exc:
        print(f"PTT mirror unavailable: {exc}")

    return [], "unavailable"


def extract_article_content(url):
    """Fetch PTTWeb article text + visible push comments when available."""
    try:
        r = session.get(url, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Main article body.
        main = soup.select_one(".bbs-screen.bbs-content")
        article_text = clean_text(main.get_text("\n", strip=True)) if main else ""

        # Visible PTTWeb push comments.
        pushes = []
        for push in soup.select(".push"):
            txt = clean_text(push.get_text(" ", strip=True))
            if txt:
                pushes.append(txt)

        if pushes:
            comment_text = " | ".join(pushes[:80])
            combined = f"文章：{article_text}\n留言：{comment_text}"
        else:
            combined = article_text

        combined = clean_text(combined)
        return combined[:ARTICLE_MAX_CHARS]
    except Exception as exc:
        print(f"Article fetch failed: {url} -> {exc}")
        return ""


def enrich_ptt_items(items):
    """Add article/comment excerpts to a limited number of non-admin threads."""
    enriched = []
    fetched = 0

    for item in items:
        row = dict(item)

        # Only fetch article bodies for potentially useful threads.
        if fetched < ARTICLE_FETCH_LIMIT:
            body = extract_article_content(item["url"])
            if body:
                row["content_excerpt"] = body
                fetched += 1
                time.sleep(0.15)

        enriched.append(row)

    print(f"PTT article enrichment: {fetched}/{len(items)} articles fetched")
    return enriched


def fetch_dcard():
    for endpoint in DCARD_ENDPOINTS:
        try:
            r = session.get(
                endpoint,
                params={"limit": min(MAX_ITEMS, 100), "popular": "false"},
                headers={"Referer": "https://www.dcard.tw/f/stock"},
                timeout=20,
            )
            r.raise_for_status()
            payload = r.json()

            items = []
            for post in payload if isinstance(payload, list) else payload.get("data", []):
                if not isinstance(post, dict):
                    continue
                title = clean_text(post.get("title", ""))
                if not title or should_exclude(title):
                    continue

                pid = post.get("id")
                if not pid:
                    continue

                items.append(
                    {
                        "source": "Dcard",
                        "title": title,
                        "url": f"https://www.dcard.tw/f/stock/p/{pid}",
                    }
                )

            if items:
                return dedupe_items(items)[:MAX_ITEMS], "api"

        except Exception as exc:
            print(f"Dcard unavailable: {endpoint}: {exc}")

    return [], "unavailable"


def merge_items(ptt_items, dcard_items):
    return dedupe_items(ptt_items + dcard_items)[:MAX_ITEMS]


def normalize_ticker(ticker):
    return clean_text(str(ticker)).upper().replace(" ", "")


def apply_symbol_names(stocks):
    cleaned = []
    seen = set()

    for stock in stocks or []:
        if not isinstance(stock, dict):
            continue

        ticker = normalize_ticker(stock.get("ticker", ""))
        if not ticker:
            continue

        # Basic validation: Taiwan numeric tickers, common ETF symbols, or
        # alphabetic US ETF/ticker symbols.
        if not re.fullmatch(r"\d{4,6}|[A-Z][A-Z0-9.\-]{0,9}", ticker):
            continue

        if ticker in seen:
            continue
        seen.add(ticker)

        name = clean_text(stock.get("name", ""))
        if not name:
            name = SYMBOL_NAMES.get(ticker, "")

        bullish = max(0, min(100, int(float(stock.get("bullish", 0) or 0))))
        neutral = max(0, min(100, int(float(stock.get("neutral", 0) or 0))))
        bearish = max(0, min(100, int(float(stock.get("bearish", 0) or 0))))

        # Normalize the three percentages to total 100.
        total = bullish + neutral + bearish
        if total == 0:
            neutral = 100
        elif total != 100:
            bullish = round(bullish * 100 / total)
            neutral = round(neutral * 100 / total)
            bearish = 100 - bullish - neutral

        sources = stock.get("sources", [])
        if not isinstance(sources, list):
            sources = []

        cleaned.append(
            {
                "ticker": ticker,
                "name": name,
                "bullish": bullish,
                "neutral": neutral,
                "bearish": bearish,
                "confidence": round(
                    max(0.0, min(1.0, float(stock.get("confidence", 0.0) or 0.0))),
                    2,
                ),
                "summary": clean_text(stock.get("summary", "")),
                "mention_count": max(
                    1, int(float(stock.get("mention_count", 1) or 1))
                ),
                "sources": list(dict.fromkeys(str(x) for x in sources if x)),
            }
        )

    return cleaned


def analyze_with_gemini(items):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY is missing; skipping Gemini.")
        return []

    try:
        from google import genai
        from google.genai import types
    except Exception as exc:
        print(f"google-genai import failed: {exc}")
        return []

    # Keep the working model configurable. If Google changes availability,
    # GEMINI_MODEL can be changed in GitHub Actions without editing this file.
    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    client = genai.Client(api_key=api_key)

    source_rows = []
    for i, item in enumerate(items, 1):
        source_rows.append(
            {
                "id": i,
                "source": item.get("source"),
                "title": item.get("title"),
                "url": item.get("url"),
                "content_excerpt": item.get("content_excerpt", ""),
            }
        )

    prompt = f"""
你是 Catlion 的「社交股票情緒分析器」。

只分析以下 PTT / Dcard 股票討論資料。
禁止使用外部新聞、即時股價、財報或你自己的背景資料補充。
不要提供買賣建議。

重要：
1. 優先使用文章內容及留言；如果沒有 content_excerpt，才使用標題。
2. 只列出在來源文字中「明確出現」或能從明確公司名稱直接對應的股票/ETF。
3. 不要因為新聞提到某產業，就自行推測相關公司。
4. 不要把公告、板規、置底、水桶等行政內容當作投資情緒。
5. mention_count 是來源文章/討論串中實際提及該標的的「討論串數」，不是留言人數。
6. bullish + neutral + bearish 必須等於 100。
7. 如果資料不足以判斷情緒，neutral 應提高，不要硬猜。
8. confidence 是你對該標的情緒判斷的信心，0 到 1。
9. sources 只能使用提供給你的 URL。
10. 同一股票在多篇討論出現時，要合併成一個 ticker。
11. 中文股票名稱如果來源沒有提供，不要自行亂填；ETF 可使用常見名稱。

輸入資料：
{json.dumps(source_rows, ensure_ascii=False)}

請只輸出符合 schema 的 JSON。
"""

    schema = {
        "type": "object",
        "properties": {
            "stocks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string"},
                        "name": {"type": "string"},
                        "bullish": {"type": "integer"},
                        "neutral": {"type": "integer"},
                        "bearish": {"type": "integer"},
                        "confidence": {"type": "number"},
                        "summary": {"type": "string"},
                        "mention_count": {"type": "integer"},
                        "sources": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": [
                        "ticker",
                        "name",
                        "bullish",
                        "neutral",
                        "bearish",
                        "confidence",
                        "summary",
                        "mention_count",
                        "sources",
                    ],
                },
            }
        },
        "required": ["stocks"],
    }

    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
                temperature=0.2,
            ),
        )

        raw = response.text or "{}"
        result = json.loads(raw)
        stocks = apply_symbol_names(result.get("stocks", []))
        print(f"Gemini analyzed {len(stocks)} stocks.")
        return stocks

    except Exception as exc:
        print(f"Gemini analysis failed: {exc}")
        return []


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
    print("Catlion V4 collector starting...")

    ptt_items, ptt_status = fetch_ptt()
    print(f"PTT: {len(ptt_items)} items ({ptt_status})")

    dcard_items, dcard_status = fetch_dcard()
    print(f"Dcard: {len(dcard_items)} items ({dcard_status})")

    # Enrich PTT with article + visible comment text before Gemini analysis.
    ptt_items = enrich_ptt_items(ptt_items)

    items = merge_items(ptt_items, dcard_items)

    previous = load_previous_data()

    if not items:
        # Never replace good historical data with an empty dataset.
        preserved = dict(previous)
        preserved["generated_at"] = datetime.now(timezone.utc).isoformat()
        preserved["status"] = "sources_unavailable"
        preserved["sources"] = {
            "PTT": {"status": ptt_status, "items": 0},
            "Dcard": {"status": dcard_status, "items": 0},
        }
        write_data(preserved)
        print("No source items. Preserved previous data.json.")
        return

    stocks = analyze_with_gemini(items)

    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ok" if stocks else "collected_no_ai_result",
        "version": "v4",
        "sources": {
            "PTT": {"status": ptt_status, "items": len(ptt_items)},
            "Dcard": {"status": dcard_status, "items": len(dcard_items)},
        },
        "total_items": len(items),
        "items": items,
        "stocks": stocks,
    }

    write_data(data)
    print(f"Wrote data.json items={len(items)} stocks={len(stocks)}")


if __name__ == "__main__":
    main()
