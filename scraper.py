import os, re, json, time
from datetime import datetime, timezone
from pathlib import Path
import requests
from bs4 import BeautifulSoup

OUT=Path("data.json")
HEADERS={"User-Agent":"Catlion/1.0 (personal research dashboard)"}
MAX_ITEMS=int(os.getenv("MAX_ITEMS","80"))
GEMINI_API_KEY=os.getenv("GEMINI_API_KEY","").strip()

def fetch(url):
    r=requests.get(url,headers=HEADERS,timeout=20)
    r.raise_for_status()
    return r.text

def ptt():
    # Conservative public-page reader. If PTT changes markup, this source simply returns [].
    url="https://www.ptt.cc/bbs/Stock/index.html"
    try:
        soup=BeautifulSoup(fetch(url),"html.parser")
        out=[]
        for a in soup.select("div.r-ent div.title a")[:MAX_ITEMS]:
            href=a.get("href")
            if href: out.append({"source":"PTT","title":a.get_text(" ",strip=True),"url":"https://www.ptt.cc"+href})
        return out
    except Exception as e:
        print("PTT:",e); return []

def dcard():
    # Dcard's public endpoints/markup can change. Keep this adapter isolated.
    # Start with the public search page and fail safely.
    url="https://www.dcard.tw/f/stock"
    try:
        soup=BeautifulSoup(fetch(url),"html.parser")
        out=[]
        for a in soup.select("a[href*='/f/stock/p/']")[:MAX_ITEMS]:
            title=a.get_text(" ",strip=True)
            href=a.get("href")
            if href and title:
                out.append({"source":"Dcard","title":title,"url":"https://www.dcard.tw"+href})
        # de-duplicate
        seen=set(); clean=[]
        for x in out:
            if x["url"] not in seen: seen.add(x["url"]); clean.append(x)
        return clean
    except Exception as e:
        print("Dcard:",e); return []

def detect_tickers(items):
    # Initial US ticker detector. Expand later with a maintained symbol list.
    pat=re.compile(r'(?<![A-Za-z])\$?[A-Z]{2,5}(?![A-Za-z])')
    buckets={}
    for item in items:
        text=item["title"]
        for t in set(x.replace("$","") for x in pat.findall(text)):
            if t in {"THE","AND","FOR","THIS","WITH","FROM","YOU","ARE","NOT","NEW","ALL"}: continue
            buckets.setdefault(t,[]).append(item)
    return buckets

def fallback(buckets):
    stocks=[]
    for t,items in sorted(buckets.items(),key=lambda kv:-len(kv[1]))[:20]:
        stocks.append({"ticker":t,"name":"","mentions":len(items),
                       "sentiment":{"bullish":0,"neutral":100,"bearish":0},
                       "summary":"尚未設定 GEMINI_API_KEY；目前只顯示討論量。",
                       "posts":items[:3]})
    return {"generated_at":datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "sources":["PTT","Dcard"],"status":"collector-only","stocks":stocks}

def analyze_with_gemini(buckets):
    from google import genai
    from google.genai import types
    client=genai.Client(api_key=GEMINI_API_KEY)
    compact=[]
    for t,items in sorted(buckets.items(),key=lambda kv:-len(kv[1]))[:20]:
        compact.append({"ticker":t,"posts":[x["title"][:300] for x in items[:12]]})
    prompt="""你是股票社群資料分類器。只根據提供的 PTT/Dcard 標題判斷討論情緒，不作投資建議。
輸出每個 ticker 的：name、bullish、neutral、bearish（整數百分比總和100）、summary。
如果資料不足，neutral 提高，不要猜測公司資訊。
資料：""" + json.dumps(compact,ensure_ascii=False)

    schema={"type":"object","properties":{"stocks":{"type":"array","items":{"type":"object","properties":{
      "ticker":{"type":"string"},"name":{"type":"string"},
      "bullish":{"type":"integer"},"neutral":{"type":"integer"},"bearish":{"type":"integer"},
      "summary":{"type":"string"}},"required":["ticker","name","bullish","neutral","bearish","summary"]}}},
      "required":["stocks"]}
    r=client.models.generate_content(model="gemini-2.5-flash-lite",contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json",response_schema=schema))
    ai=json.loads(r.text)
    by={x["ticker"]:x for x in ai.get("stocks",[])}
    stocks=[]
    for t,items in buckets.items():
        x=by.get(t,{})
        stocks.append({"ticker":t,"name":x.get("name",""),"mentions":len(items),
          "sentiment":{"bullish":x.get("bullish",0),"neutral":x.get("neutral",100),"bearish":x.get("bearish",0)},
          "summary":x.get("summary","資料不足。"),"posts":items[:3]})
    return {"generated_at":datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "sources":["PTT","Dcard"],"status":"live","stocks":stocks}

def main():
    items=ptt()+dcard()
    # basic URL/title de-duplication
    seen=set(); clean=[]
    for x in items:
        key=(x["source"],x["url"])
        if key not in seen: seen.add(key); clean.append(x)
    buckets=detect_tickers(clean)
    data=analyze_with_gemini(buckets) if GEMINI_API_KEY and buckets else fallback(buckets)
    OUT.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    print("Wrote",OUT,"items=",len(clean),"tickers=",len(buckets))

if __name__=="__main__": main()
