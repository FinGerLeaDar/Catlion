import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
import requests

DATA_FILE = Path("data.json")
ST_BASE = "https://api.stocktwits.com/api/2"
ST_TRENDING = f"{ST_BASE}/trending/symbols/equities.json"
ST_STREAM = f"{ST_BASE}/streams/symbol/{{symbol}}.json"
MAX_SYMBOLS = int(os.getenv("MAX_SYMBOLS", "15"))
MESSAGES_PER_SYMBOL = min(int(os.getenv("MESSAGES_PER_SYMBOL", "30")), 30)
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "0.25"))
HEADERS = {"User-Agent": "Catlion/1.0 (personal US stock sentiment dashboard)", "Accept": "application/json"}
session = requests.Session(); session.headers.update(HEADERS)

def clean_text(value): return " ".join(str(value or "").split()).strip()

def get_json(url, params=None):
    r=session.get(url, params=params or {}, timeout=25); r.raise_for_status(); return r.json()

def fetch_trending_equities():
    payload=get_json(ST_TRENDING, {"limit":30}); out=[]
    for row in payload.get("symbols", []):
        if not isinstance(row, dict): continue
        symbol=clean_text(row.get("symbol", "")).upper(); region=clean_text(row.get("region", "")).upper(); instrument=clean_text(row.get("instrument_class", "")).lower()
        if not symbol or region != "US" or instrument not in {"stock","exchangetradedfund"} or symbol.endswith(".X"): continue
        out.append({"ticker":symbol,"name":clean_text(row.get("title") or (row.get("fundamentals") or {}).get("Name") or symbol),"exchange":clean_text(row.get("exchange","")),"instrument_class":row.get("instrument_class"),"trending_score":row.get("trending_score"),"watchlist_count":row.get("watchlist_count"),"trend_summary":clean_text((row.get("trends") or {}).get("summary","")),"rank":row.get("rank")})
        if len(out)>=MAX_SYMBOLS: break
    return out

def fetch_symbol_messages(symbol):
    p=get_json(ST_STREAM.format(symbol=symbol), {"limit":MESSAGES_PER_SYMBOL}); return p.get("messages", []), p.get("symbol", {})

def normalize_sentiment(value):
    value=clean_text(value).lower(); return value if value in {"bullish","bearish"} else "neutral"

def analyze_symbol(meta, messages):
    bullish=bearish=neutral=0; cleaned=[]
    for m in messages:
        if not isinstance(m,dict): continue
        sentiment=normalize_sentiment(((m.get("entities") or {}).get("sentiment") or {}).get("basic"))
        if sentiment=="bullish": bullish+=1
        elif sentiment=="bearish": bearish+=1
        else: neutral+=1
        mid=m.get("id"); cleaned.append({"id":mid,"body":clean_text(m.get("body","")),"created_at":m.get("created_at"),"sentiment":sentiment,"discussion":bool(m.get("discussion",False)),"replies":int(((m.get("conversation") or {}).get("replies") or 0)),"likes":int(((m.get("likes") or {}).get("total") or 0)),"url":f"https://stocktwits.com/message/{mid}" if mid else f"https://stocktwits.com/symbol/{meta['ticker']}"})
    total=bullish+bearish+neutral; tagged=bullish+bearish
    if total:
        bp=round(bullish*100/total); rp=round(bearish*100/total); np=100-bp-rp
    else: bp=np=rp=0
    score=round((bullish+0.5*neutral)*100/total,1) if total else 50.0
    confidence=round(tagged/total,2) if total else 0.0
    return {"ticker":meta["ticker"],"name":meta["name"],"exchange":meta["exchange"],"instrument_class":meta["instrument_class"],"bullish":bp,"neutral":np,"bearish":rp,"sentiment_score":score,"confidence":confidence,"mention_count":total,"tagged_count":tagged,"summary":meta.get("trend_summary",""),"trending_score":meta.get("trending_score"),"watchlist_count":meta.get("watchlist_count"),"rank":meta.get("rank"),"source":"Stocktwits","source_url":f"https://stocktwits.com/symbol/{meta['ticker']}","messages":cleaned}

def load_previous_data():
    try: return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception: return {}

def write_data(data): DATA_FILE.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")

def main():
    print("Catlion V6 collector starting..."); previous=load_previous_data()
    try: candidates=fetch_trending_equities(); print(f"Stocktwits trending US symbols: {len(candidates)}")
    except Exception as exc:
        print(f"Stocktwits trending unavailable: {exc}"); preserved=dict(previous); preserved["generated_at"]=datetime.now(timezone.utc).isoformat(); preserved["status"]="sources_unavailable"; preserved["sources"]={"Stocktwits":{"status":"unavailable","items":0}}; write_data(preserved); return
    if not candidates:
        preserved=dict(previous); preserved["generated_at"]=datetime.now(timezone.utc).isoformat(); preserved["status"]="no_us_symbols"; preserved["sources"]={"Stocktwits":{"status":"empty","items":0}}; write_data(preserved); return
    stocks=[]; all_items=[]
    for i,meta in enumerate(candidates,1):
        try:
            messages,symbol_info=fetch_symbol_messages(meta["ticker"])
            if symbol_info: meta["name"]=clean_text(symbol_info.get("title") or meta["name"])
            stock=analyze_symbol(meta,messages); stocks.append(stock)
            for msg in stock["messages"]: all_items.append({"source":"Stocktwits","ticker":meta["ticker"],"title":msg["body"][:140],"content_excerpt":msg["body"],"url":msg["url"],"created_at":msg["created_at"],"sentiment":msg["sentiment"]})
            print(f"[{i}/{len(candidates)}] {meta['ticker']}: messages={len(messages)} bullish={stock['bullish']}% neutral={stock['neutral']}% bearish={stock['bearish']}%"); time.sleep(REQUEST_DELAY)
        except Exception as exc: print(f"{meta['ticker']}: stream unavailable: {exc}")
    if not stocks:
        preserved=dict(previous); preserved["generated_at"]=datetime.now(timezone.utc).isoformat(); preserved["status"]="streams_unavailable"; preserved["sources"]={"Stocktwits":{"status":"trending_ok_streams_failed","items":0}}; write_data(preserved); return
    data={"generated_at":datetime.now(timezone.utc).isoformat(),"status":"ok","version":"v6","source_type":"US social sentiment","sources":{"Stocktwits":{"status":"api","symbols":len(stocks),"messages":len(all_items)}},"total_items":len(all_items),"items":all_items,"stocks":stocks}; write_data(data); print(f"Wrote data.json symbols={len(stocks)} messages={len(all_items)}")

if __name__=="__main__": main()
