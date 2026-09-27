import json, os, time
from datetime import datetime, timezone
from pathlib import Path
import requests

DATA_FILE=Path("data.json")
WATCHLIST_FILE=Path("watchlist.json")
ST_BASE="https://api.stocktwits.com/api/2"
ST_TRENDING=f"{ST_BASE}/trending/symbols/equities.json"
ST_STREAM=f"{ST_BASE}/streams/symbol/{{symbol}}.json"
YF_CHART="https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
TRENDING_SYMBOLS=int(os.getenv("TRENDING_SYMBOLS","10"))
MESSAGES_PER_SYMBOL=min(int(os.getenv("MESSAGES_PER_SYMBOL","30")),30)
REQUEST_DELAY=float(os.getenv("REQUEST_DELAY","0.25"))
PRICE_DELAY=float(os.getenv("PRICE_DELAY","0.25"))
DEFAULT_WATCHLIST=["ONDS","NVDA","AMD","TSLA","AAPL","MSFT","AMZN","META","GOOGL","AVGO","PLTR","SOFI","RKLB","SPY","QQQ"]
HEADERS={"User-Agent":"Catlion/1.0 (personal US stock sentiment dashboard)","Accept":"application/json"}
session=requests.Session();session.headers.update(HEADERS)

def clean_text(v): return " ".join(str(v or "").split()).strip()
def normalize_watchlist(values):
    out=[];seen=set()
    for v in values:
        s=clean_text(v).upper()
        if s and s not in seen and len(s)<=10: out.append(s);seen.add(s)
    return out
def load_watchlist():
    e=clean_text(os.getenv("WATCHLIST",""))
    if e:return normalize_watchlist(e.split(","))
    try:
        c=json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"));w=normalize_watchlist(c.get("watchlist",[]))
        if w:return w
    except Exception as exc: print(f"watchlist.json unavailable: {exc}")
    return DEFAULT_WATCHLIST[:]
WATCHLIST=load_watchlist()
def get_json(url,params=None):
    r=session.get(url,params=params or {},timeout=25);r.raise_for_status();return r.json()

def fetch_trending_equities():
    payload=get_json(ST_TRENDING,{"limit":30});symbols=[]
    for row in payload.get("symbols",[]):
        if not isinstance(row,dict):continue
        symbol=clean_text(row.get("symbol","")).upper()
        region=clean_text(row.get("region","")).upper()
        instrument=clean_text(row.get("instrument_class","")).lower()
        if not symbol or region!="US" or instrument not in {"stock","exchangetradedfund"} or symbol.endswith(".X"):continue
        if symbol in WATCHLIST:continue
        symbols.append({"ticker":symbol,"name":clean_text(row.get("title") or (row.get("fundamentals") or {}).get("Name") or symbol),"exchange":clean_text(row.get("exchange","")),"instrument_class":row.get("instrument_class"),"trending_score":row.get("trending_score"),"watchlist_count":row.get("watchlist_count"),"trend_summary":clean_text((row.get("trends") or {}).get("summary","")),"rank":row.get("rank")})
        if len(symbols)>=TRENDING_SYMBOLS:break
    return symbols

def fetch_current_price(symbol):
    p=get_json(YF_CHART.format(symbol=symbol),{"range":"1d","interval":"1m","includePrePost":"true","events":"div,splits"})
    result=(p.get("chart",{}).get("result") or [])
    if not result:return None
    meta=result[0].get("meta") or {}
    for key in ("regularMarketPrice","postMarketPrice","preMarketPrice"):
        v=meta.get(key)
        if isinstance(v,(int,float)) and v>0:return float(v)
    return None

def fetch_symbol_messages(symbol):
    p=get_json(ST_STREAM.format(symbol=symbol),{"limit":MESSAGES_PER_SYMBOL})
    return p.get("messages",[]),p.get("symbol",{})
def normalize_sentiment(v):
    v=clean_text(v).lower()
    return v if v in {"bullish","bearish"} else "neutral"

def analyze_symbol(meta,messages,discovery_type):
    bullish=bearish=neutral=0;cleaned=[]
    for m in messages:
        if not isinstance(m,dict):continue
        sentiment=normalize_sentiment(((m.get("entities") or {}).get("sentiment") or {}).get("basic"))
        if sentiment=="bullish":bullish+=1
        elif sentiment=="bearish":bearish+=1
        else:neutral+=1
        mid=m.get("id")
        cleaned.append({"id":mid,"body":clean_text(m.get("body","")),"created_at":m.get("created_at"),"sentiment":sentiment,"discussion":bool(m.get("discussion",False)),"replies":int(((m.get("conversation") or {}).get("replies") or 0)),"likes":int(((m.get("likes") or {}).get("total") or 0)),"url":f"https://stocktwits.com/message/{mid}" if mid else f"https://stocktwits.com/symbol/{meta['ticker']}"})
    total=bullish+bearish+neutral;tagged=bullish+bearish
    if total:
        bp=round(bullish*100/total);brp=round(bearish*100/total);np=100-bp-brp
    else:bp=brp=np=0
    return {"ticker":meta["ticker"],"name":meta["name"],"exchange":meta["exchange"],"instrument_class":meta["instrument_class"],"discovery":discovery_type,"bullish":bp,"neutral":np,"bearish":brp,"sentiment_score":round((bullish+.5*neutral)*100/total,1) if total else 50.0,"confidence":round(tagged/total,2) if total else 0.0,"mention_count":total,"tagged_count":tagged,"summary":meta.get("trend_summary",""),"trending_score":meta.get("trending_score"),"watchlist_count":meta.get("watchlist_count"),"rank":meta.get("rank"),"price":meta.get("price"),"price_source":meta.get("price_source"),"source":"Stocktwits","source_url":f"https://stocktwits.com/symbol/{meta['ticker']}","messages":cleaned}

def load_previous_data():
    try:return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception:return {}
def write_data(d):DATA_FILE.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding="utf-8")

def main():
    print("Catlion V9 collector starting...")
    print(f"Permanent watchlist: {', '.join(WATCHLIST)}")
    previous=load_previous_data()
    try:trending=fetch_trending_equities();print(f"Stocktwits trending US symbols: {len(trending)}")
    except Exception as exc:print(f"Stocktwits trending unavailable: {exc}");trending=[]
    candidates={}
    for s in WATCHLIST:candidates[s]={"ticker":s,"name":s,"exchange":"","instrument_class":"","trending_score":None,"watchlist_count":None,"trend_summary":"","rank":None}
    for meta in trending:candidates.setdefault(meta["ticker"],meta)
    for meta in trending:
        if meta["ticker"] in candidates:candidates[meta["ticker"]].update(meta)
    rows=list(candidates.values());print(f"Total symbols to monitor: {len(rows)} (watchlist={len(WATCHLIST)}, trending={len(trending)})")
    if not rows:
        d=dict(previous);d["generated_at"]=datetime.now(timezone.utc).isoformat();d["status"]="sources_unavailable";write_data(d);return
    stocks=[];all_items=[]
    for i,meta in enumerate(rows,1):
        ticker=meta["ticker"];discovery="watchlist" if ticker in WATCHLIST else "trending"
        try:
            messages,symbol_info=fetch_symbol_messages(ticker)
            if symbol_info:
                meta["name"]=clean_text(symbol_info.get("title") or meta["name"]);meta["exchange"]=clean_text(symbol_info.get("exchange") or meta["exchange"]);meta["instrument_class"]=symbol_info.get("instrument_class") or meta["instrument_class"]
            stock=analyze_symbol(meta,messages,discovery)
            try:
                stock["price"]=fetch_current_price(ticker);stock["price_source"]="Yahoo Finance" if stock["price"] is not None else None
            except Exception as exc:
                print(f"{ticker}: price unavailable: {exc}");stock["price"]=None;stock["price_source"]=None
            stocks.append(stock)
            for m in stock["messages"]:
                all_items.append({"source":"Stocktwits","ticker":ticker,"discovery":discovery,"title":m["body"][:140],"content_excerpt":m["body"],"url":m["url"],"created_at":m["created_at"],"sentiment":m["sentiment"]})
            print(f"[{i}/{len(rows)}] {ticker}: {discovery}, messages={len(messages)}, bullish={stock['bullish']}%, neutral={stock['neutral']}%, bearish={stock['bearish']}%")
            time.sleep(PRICE_DELAY+REQUEST_DELAY)
        except Exception as exc:print(f"{ticker}: stream unavailable: {exc}")
    if not stocks:
        d=dict(previous);d["generated_at"]=datetime.now(timezone.utc).isoformat();d["status"]="streams_unavailable";write_data(d);return
    data={"generated_at":datetime.now(timezone.utc).isoformat(),"status":"ok","version":"v9","source_type":"US social sentiment","watchlist":WATCHLIST,"sources":{"Stocktwits":{"status":"api","watchlist_symbols":len(WATCHLIST),"trending_symbols":len(trending),"monitored_symbols":len(stocks),"messages":len(all_items)}},"total_items":len(all_items),"items":all_items,"stocks":stocks}
    write_data(data);print(f"Wrote data.json symbols={len(stocks)} messages={len(all_items)}")
if __name__=="__main__":main()
