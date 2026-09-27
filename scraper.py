import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None


MAX_ITEMS = int(os.getenv("MAX_ITEMS", "80"))
DATA_FILE = Path("data.json")

PTT_DIRECT_URL = "https://www.ptt.cc/bbs/Stock/index.html"
PTT_MIRROR_URL = "https://www.pttweb.cc/bbs/Stock"

# Dcard currently has more than one public web/API route in use.
# GitHub-hosted runners can be blocked by Dcard's edge protection, so try
# both known routes before declaring the source unavailable.
DCARD_ENDPOINTS = [
    "https://www.dcard.tw/service/api/v2/forums/stock/posts",
    "https://www.dcard.tw/_api/forums/stock/posts",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.7",
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
    "Referer": "https://www.dcard.tw/f/stock",
}


def get_json(url, params=None, timeout=25):
    response = requests.get(
        url,
        headers=HEADERS,
        params=params,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def get_html(url, timeout=25):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.text


def clean_text(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def fetch_ptt():
    errors = []

    try:
        html = get_html(PTT_DIRECT_URL)
        soup = BeautifulSoup(html, "html.parser")
        items = []

        for a in soup.select("div.r-ent div.title a"):
            title = clean_text(a.get_text(" ", strip=True))
            href = a.get("href")
            if not title or not href:
                continue

            items.append({
                "source": "PTT",
                "title": title,
                "url": urljoin("https://www.ptt.cc", href),
            })

        if items:
            return items[:MAX_ITEMS], "official"

        errors.append("official PTT returned no article links")
    except Exception as exc:
        errors.append(f"official PTT: {exc}")

    # GitHub Actions runners can receive 403 from ptt.cc.
    # Try a public mirror before giving up.
    try:
        html = get_html(PTT_MIRROR_URL)
        soup = BeautifulSoup(html, "html.parser")
        items = []

        for a in soup.select("a[href*='/bbs/Stock/']"):
            title = clean_text(a.get_text(" ", strip=True))
            href = a.get("href")

            if not title or not href:
                continue

            if title in {"最新", "熱門", "分頁", "搜尋", "自訂"}:
                continue

            items.append({
                "source": "PTT",
                "title": title,
                "url": urljoin("https://www.pttweb.cc", href),
            })

        seen = set()
        unique = []
        for item in items:
            if item["url"] in seen:
                continue
            seen.add(item["url"])
            unique.append(item)

        if unique:
            return unique[:MAX_ITEMS], "pttweb_mirror"

        errors.append("PTTWeb mirror returned no article links")
    except Exception as exc:
        errors.append(f"PTTWeb mirror: {exc}")

    print("PTT unavailable:", " | ".join(errors))
    return [], "unavailable"


def parse_dcard_posts(data):
    posts = data.get("posts", data if isinstance(data, list) else [])
    items = []

    for post in posts:
        post_id = post.get("id")
        title = clean_text(post.get("title"))

        if not title or not post_id:
            continue

        items.append({
            "source": "Dcard",
            "title": title,
            "url": f"https://www.dcard.tw/f/stock/p/{post_id}",
        })

    return items


def fetch_dcard():
    errors = []

    for endpoint in DCARD_ENDPOINTS:
        for params in (
            {"limit": min(MAX_ITEMS, 100), "popular": "false"},
            {"limit": min(MAX_ITEMS, 30), "popular": "false"},
        ):
            try:
                data = get_json(endpoint, params=params)
                items = parse_dcard_posts(data)

                if items:
                    route = "_api" if "/_api/" in endpoint else "service_api_v2"
                    return items[:MAX_ITEMS], route

                errors.append(f"{endpoint}: empty response")
            except Exception as exc:
                errors.append(f"{endpoint}: {exc}")

    print("Dcard unavailable:", " | ".join(errors))
    return [], "unavailable"


def load_existing():
    if not DATA_FILE.exists():
        return {
            "generated_at": None,
            "status": "empty",
            "sources": {},
            "items": [],
            "stocks": [],
        }

    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {
            "generated_at": None,
            "status": "invalid_existing_data",
            "sources": {},
            "items": [],
            "stocks": [],
        }


def merge_items(*groups):
    combined = []
    seen = set()

    for group in groups:
        for item in group:
            key = item.get("url") or item.get("title")
            if not key or key in seen:
                continue

            seen.add(key)
            combined.append(item)

    return combined[:MAX_ITEMS]


def analyze_with_gemini(items):
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        print("GEMINI_API_KEY not set; collector-only mode.")
        return []

    if not items:
        print("No collected items; skipping Gemini.")
        return []

    if genai is None:
        print("google-genai is not installed; skipping Gemini.")
        return []

    source_text = "\n".join(
        f"{i + 1}. [{item['source']}] {item['title']} | {item['url']}"
        for i, item in enumerate(items[:MAX_ITEMS])
    )

    prompt = f"""
你是 Catlion 的股票社群輿情分析器。

請只根據下面 PTT / Dcard 股票討論標題，整理「有明確提及股票或 ETF」的項目。
不要自行補充新聞、股價或外部資料。
同一股票可以合併多篇討論。

每個股票/ETF輸出：
- ticker：台股通常是 4~6 位數字；美股/ETF 使用明確出現的英文字母代號
- name：能從標題可靠判斷才填名稱，否則留空
- bullish / neutral / bearish：三個整數，總和必須等於 100
- summary：繁體中文簡短總結討論焦點，不要給買賣建議
- discussion_count：相關討論篇數
- sources：實際相關文章 URL，最多 5 條

重要：
1. 不要把一般英文單字當 ticker。
2. 不要猜不存在於標題中的股票。
3. 不要加入外部新聞、股價或你自己的投資判斷。
4. 如果資料不足，該股票不要輸出。
5. summary 是描述社群討論內容，不是投資建議。

資料：
{source_text}
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
                        "summary": {"type": "string"},
                        "discussion_count": {"type": "integer"},
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
                        "summary",
                        "discussion_count",
                        "sources",
                    ],
                },
            }
        },
        "required": ["stocks"],
    }

    try:
        client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )

        payload = json.loads(response.text)
        stocks = payload.get("stocks", [])
        print(f"Gemini analyzed {len(stocks)} stocks.")
        return stocks

    except Exception as exc:
        print(f"Gemini analysis failed: {exc}")
        return []


def main():
    print("Catlion collector starting...")

    ptt_items, ptt_mode = fetch_ptt()
    dcard_items, dcard_mode = fetch_dcard()

    print(f"PTT: {len(ptt_items)} items ({ptt_mode})")
    print(f"Dcard: {len(dcard_items)} items ({dcard_mode})")

    items = merge_items(ptt_items, dcard_items)

    # If neither source is usable, preserve the previous useful dataset.
    if not items:
        old = load_existing()
        old["generated_at"] = datetime.now(timezone.utc).isoformat()
        old["status"] = "sources_unavailable"
        old["sources"] = {
            "PTT": {"status": ptt_mode, "items": 0},
            "Dcard": {"status": dcard_mode, "items": 0},
        }
        old["error"] = (
            "PTT and Dcard returned no usable items; previous data preserved."
        )

        DATA_FILE.write_text(
            json.dumps(old, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print("No new items. Previous data preserved.")
        return

    stocks = analyze_with_gemini(items)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ok" if stocks else "collected_no_ai_result",
        "sources": {
            "PTT": {"status": ptt_mode, "items": len(ptt_items)},
            "Dcard": {"status": dcard_mode, "items": len(dcard_items)},
        },
        "total_items": len(items),
        "items": items,
        "stocks": stocks,
    }

    DATA_FILE.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Wrote data.json items={len(items)} stocks={len(stocks)}")


if __name__ == "__main__":
    main()
