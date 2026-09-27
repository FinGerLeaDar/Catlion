(() => {
"use strict";
let DATA=null, CONFIG_WATCHLIST=[], WATCHLIST=[], filterMode="all", sortMode="my-order";
const DEFAULT_WATCHLIST=["ONDS","NVDA","AMD","TSLA","AAPL","MSFT","AMZN","META","GOOGL","AVGO","PLTR","SOFI","RKLB","SPY","QQQ"];
const SORT_OPTIONS={"my-order":"我的順序","score-desc":"Sentiment 高 → 低","score-asc":"Sentiment 低 → 高","bullish-desc":"Bullish % 高 → 低","bearish-desc":"Bearish % 高 → 低","messages-desc":"Messages 多 → 少","confidence-desc":"Confidence 高 → 低","price-desc":"Price 高 → 低","price-asc":"Price 低 → 高","ticker-asc":"Ticker A → Z"};
const $=s=>document.querySelector(s);
const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const num=(v,f=0)=>Number.isFinite(Number(v))?Number(v):f;
const clamp=v=>Math.max(0,Math.min(100,num(v)));
const safeUrl=v=>{try{const u=new URL(String(v||"#"),location.href);return u.protocol==="https:"||u.protocol==="http:"?esc(u.href):"#"}catch(_){return "#"}};
function formatDate(v){if(!v)return"—";const d=new Date(v);return Number.isNaN(d.getTime())?String(v):d.toLocaleString("zh-HK",{timeZone:"Asia/Hong_Kong",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit"})}
function setStatus(t,e=false){const x=$("#loadStatus");if(x){x.textContent=t;x.classList.toggle("status-error",e)}}
function normalizeWatchlist(a){return[...new Set((Array.isArray(a)?a:[]).map(x=>String(x||"").trim().toUpperCase()).filter(x=>/^[A-Z][A-Z0-9.-]{0,9}$/.test(x)))]}
function loadLocalWatchlist(){try{return normalizeWatchlist(JSON.parse(localStorage.getItem("catlion_watchlist")||"null"))}catch(_){return[]}}
function saveLocalWatchlist(a){localStorage.setItem("catlion_watchlist",JSON.stringify(normalizeWatchlist(a)))}
function clearLocalWatchlist(){localStorage.removeItem("catlion_watchlist")}
function watchlistRank(t){const i=WATCHLIST.indexOf(String(t||"").toUpperCase());return i<0?9999:i}
async function fetchJson(p){const r=await fetch(`${p}?v=${Date.now()}`,{cache:"no-store",headers:{Accept:"application/json"}});if(!r.ok)throw Error(`${p} HTTP ${r.status}`);return r.json()}
async function fetchData(){let e;for(const p of["./data.json","data.json"]){try{const d=await fetchJson(p);if(!d||!Array.isArray(d.stocks))throw Error(`${p} 沒有有效的 stocks[]`);return d}catch(x){e=x}}throw e||Error("無法讀取 data.json")}
async function fetchWatchlistConfig(data){try{const c=await fetchJson("./watchlist.json");if(c&&Array.isArray(c.watchlist)){CONFIG_WATCHLIST=normalizeWatchlist(c.watchlist);return}}catch(_){}CONFIG_WATCHLIST=normalizeWatchlist(data.watchlist);if(!CONFIG_WATCHLIST.length)CONFIG_WATCHLIST=DEFAULT_WATCHLIST.slice()}
async function load(){setStatus("正在讀取 data.json / watchlist.json…");try{DATA=await fetchData();await fetchWatchlistConfig(DATA);const local=loadLocalWatchlist();WATCHLIST=local.length?local:CONFIG_WATCHLIST.slice();render(DATA);bindControls();setStatus(local.length?`已載入 ${DATA.stocks.length} 隻；使用本機 Watchlist ${WATCHLIST.length} 隻`:`已載入 ${DATA.stocks.length} 隻；Watchlist ${WATCHLIST.length} 隻`)}catch(e){console.error(e);setStatus("資料讀取失敗",true);showError(e)}}
function render(data){const stocks=data.stocks.filter(Boolean);$("#updated").textContent="更新："+formatDate(data.generated_at);$("#stats").innerHTML=`<div class="stat"><span>監察股票 / ETF</span><b>${stocks.length}</b></div><div class="stat"><span>我的 Watchlist</span><b id="statWatchlist">${WATCHLIST.length}</b></div><div class="stat"><span>Trending 新發現</span><b id="statTrending">0</b></div>`;draw(stocks)}
function applyFilter(a){return a.filter(s=>filterMode==="all"||filterMode==="bullish"&&num(s.bullish)>=50||filterMode==="neutral"&&num(s.neutral)>=50||filterMode==="bearish"&&num(s.bearish)>=10)}
function compareStocks(a,b){
 if(sortMode==="my-order")return watchlistRank(a.ticker)-watchlistRank(b.ticker);
 if(sortMode==="score-desc")return num(b.sentiment_score)-num(a.sentiment_score);
 if(sortMode==="score-asc")return num(a.sentiment_score)-num(b.sentiment_score);
 if(sortMode==="bullish-desc")return num(b.bullish)-num(a.bullish);
 if(sortMode==="bearish-desc")return num(b.bearish)-num(a.bearish);
 if(sortMode==="messages-desc")return num(b.mention_count)-num(a.mention_count);
 if(sortMode==="confidence-desc")return num(b.confidence)-num(a.confidence);
 if(sortMode==="price-desc")return num(b.price,-Infinity)-num(a.price,-Infinity);
 if(sortMode==="price-asc")return num(a.price,Infinity)-num(b.price,Infinity);
 if(sortMode==="ticker-asc")return String(a.ticker||"").localeCompare(String(b.ticker||""));
 return 0;
}
function draw(stocks){
 const q=($("#search")?.value||"").trim().toLowerCase(), wt=new Set(WATCHLIST), filtered=applyFilter(stocks);
 const match=s=>!q||String(s.ticker||"").toLowerCase().includes(q)||String(s.name||"").toLowerCase().includes(q);
 const watchlist=filtered.filter(s=>wt.has(String(s.ticker||"").toUpperCase())).filter(match).sort(compareStocks);
 const trending=filtered.filter(s=>s.discovery==="trending"&&!wt.has(String(s.ticker||"").toUpperCase())).filter(match).sort((a,b)=>num(a.rank,9999)-num(b.rank,9999));
 const existing=new Set(stocks.map(s=>String(s.ticker||"").toUpperCase()));
 const missing=WATCHLIST.filter(t=>!existing.has(t)).filter(t=>!q||t.toLowerCase().includes(q)).filter(()=>filterMode==="all").map(t=>({ticker:t,name:"等待下一次 Stocktwits 更新",discovery:"watchlist",bullish:0,neutral:0,bearish:0,sentiment_score:50,confidence:0,mention_count:0,tagged_count:0,summary:"已加入 Watchlist，但 data.json 尚未有最新資料。下一次 GitHub Actions 更新後會開始收集。",messages:[],pending:true}));
 const allWatch=[...watchlist,...missing].sort(compareStocks);
 $("#watchlistStocks").innerHTML=allWatch.length?allWatch.map(renderCardSafe).join(""):emptyMessage(q?`找不到「${esc(q)}」的 Watchlist 股票。`:"目前沒有符合條件的 Watchlist。");
 $("#trendingStocks").innerHTML=trending.length?trending.map(renderCardSafe).join(""):emptyMessage(q?`找不到「${esc(q)}」的 Trending 股票。`:"今日沒有符合條件的 Trending 資料。");
 $("#statWatchlist").textContent=WATCHLIST.length;$("#statTrending").textContent=trending.length;
 $("#watchlistNote").textContent=`${WATCHLIST.length} 隻 · ${SORT_OPTIONS[sortMode]}`;$("#trendingNote").textContent=`${trending.length} 隻`;$("#clearSearch").style.display=q?"block":"none";
}
function renderCardSafe(s){try{return renderCard(s)}catch(e){console.error(e);return`<article class="card error-card"><b>${esc(s?.ticker||"UNKNOWN")}</b><div>此股票資料格式有問題。</div></article>`}}
function renderCard(s){
 const bull=num(s.bullish),neu=num(s.neutral),bear=num(s.bearish),score=num(s.sentiment_score,50),conf=Math.round(num(s.confidence)*100),msgs=Array.isArray(s.messages)?s.messages:[];
 const badge=s.discovery==="watchlist"?'<span class="badge watch">⭐ WATCHLIST</span>':'<span class="badge trend">🔥 TRENDING</span>',pending=s.pending?'<span class="badge pending">⏳ PENDING</span>':"";
 const tags=msgs.slice(0,3).map(m=>`<span class="message-tag">${esc(m?.sentiment||"message")}</span>`).join("");
 const pv=Number(s.price), price=Number.isFinite(pv)?`<div class="price">$${pv.toFixed(2)}<small>PRICE</small></div>`:`<div class="price muted">—<small>PRICE</small></div>`;
 return `<article class="card"><div class="card-head"><div><div class="ticker">${esc(s.ticker||"—")} ${badge}${pending}</div><div class="name">${esc(s.name||"")}${s.exchange?" · "+esc(s.exchange):""}</div></div><div class="card-metrics">${price}<div class="score">${score.toFixed(1)}<small>SENTIMENT / 100</small></div></div></div>
 <div class="bar" title="Bullish ${bull}%"><i style="width:${clamp(bull)}%"></i></div><div class="numbers"><span>🟢 ${bull}%</span><span>⚪ 未標記 ${neu}%</span><span>🔴 ${bear}%</span></div>
 <div class="meta">${num(s.mention_count)} messages · tagged ${num(s.tagged_count)} · confidence ${conf}%</div><div class="summary">${esc(s.summary||"暫無趨勢摘要。")}</div>
 <div class="links">${s.source_url?`<a target="_blank" rel="noopener noreferrer" href="${safeUrl(s.source_url)}">Stocktwits ↗</a>`:""}${tags}${s.price_source?`<span class="price-source">Price: ${esc(s.price_source)}</span>`:""}</div></article>`;
}
function emptyMessage(m){return`<div class="card empty">${m}<div class="hint">可以用 Manage Watchlist / Filter / Sort 調整顯示。</div></div>`}
function showError(e){$("#stats").innerHTML=`<div class="card empty"><b>⚠️ Catlion 暫時讀不到 data.json</b><div class="hint">${esc(e?.message||String(e))}<br><br>請按 Ctrl + F5 再試一次。</div></div>`;$("#watchlistStocks").innerHTML="";$("#trendingStocks").innerHTML=""}
function openManager(){const m=$("#watchlistModal"),l=$("#manageList");l.innerHTML=WATCHLIST.map(t=>`<div class="manage-row" draggable="true" data-ticker="${esc(t)}"><span class="drag">☷</span><b>${esc(t)}</b><span class="manage-spacer"></span><button type="button" class="remove-ticker" data-ticker="${esc(t)}">×</button></div>`).join("");m.classList.add("open");m.setAttribute("aria-hidden","false");bindDragAndDrop();l.querySelectorAll(".remove-ticker").forEach(b=>b.addEventListener("click",()=>removeTicker(b.dataset.ticker)))}
function closeManager(){const m=$("#watchlistModal");m.classList.remove("open");m.setAttribute("aria-hidden","true")}
function addTicker(){const i=$("#addTicker"),t=i.value.trim().toUpperCase();if(!/^[A-Z][A-Z0-9.-]{0,9}$/.test(t)){setStatus("Ticker 格式唔正確，例如 ONDS / NVDA / SPY",true);i.focus();return}if(WATCHLIST.includes(t)){setStatus(`${t} 已經喺 Watchlist`);i.value="";return}WATCHLIST.push(t);saveLocalWatchlist(WATCHLIST);i.value="";openManager();draw(DATA.stocks);setStatus(`${t} 已加入；下一次 collector 更新前會顯示 PENDING`)}
function removeTicker(t){WATCHLIST=WATCHLIST.filter(x=>x!==t);saveLocalWatchlist(WATCHLIST);openManager();draw(DATA.stocks);setStatus(`${t} 已移除`)}
function saveManagerOrder(){WATCHLIST=normalizeWatchlist([...document.querySelectorAll(".manage-row")].map(r=>r.dataset.ticker));saveLocalWatchlist(WATCHLIST);draw(DATA.stocks);closeManager();setStatus("Watchlist 順序已儲存到本機")}
function resetWatchlist(){WATCHLIST=CONFIG_WATCHLIST.slice();clearLocalWatchlist();openManager();draw(DATA.stocks);setStatus("已恢復 Repo Watchlist")}
function exportWatchlist(){const b=new Blob([JSON.stringify({watchlist:WATCHLIST},null,2)],{type:"application/json"}),u=URL.createObjectURL(b),a=document.createElement("a");a.href=u;a.download="watchlist.json";a.click();URL.revokeObjectURL(u);setStatus("已輸出 watchlist.json")}
function bindDragAndDrop(){const rows=[...document.querySelectorAll(".manage-row")];let dragging=null;rows.forEach(r=>{r.addEventListener("dragstart",()=>{dragging=r;r.classList.add("dragging")});r.addEventListener("dragend",()=>{r.classList.remove("dragging");dragging=null});r.addEventListener("dragover",e=>{e.preventDefault();if(!dragging||dragging===r)return;const rect=r.getBoundingClientRect();r.parentNode.insertBefore(dragging,e.clientY<rect.top+rect.height/2?r:r.nextSibling)})})}
function bindControls(){
 $("#search").addEventListener("input",()=>DATA&&draw(DATA.stocks));$("#clearSearch").addEventListener("click",()=>{$("#search").value="";$("#search").focus();if(DATA)draw(DATA.stocks)});
 $("#manageWatchlist").addEventListener("click",openManager);$("#closeModal").addEventListener("click",closeManager);$("#watchlistModal").addEventListener("click",e=>{if(e.target===$("#watchlistModal"))closeManager()});
 $("#addTickerBtn").addEventListener("click",addTicker);$("#addTicker").addEventListener("keydown",e=>{if(e.key==="Enter")addTicker()});$("#saveManager").addEventListener("click",saveManagerOrder);$("#resetWatchlist").addEventListener("click",resetWatchlist);$("#exportWatchlist").addEventListener("click",exportWatchlist);
 document.querySelectorAll("[data-filter]").forEach(b=>b.addEventListener("click",()=>{filterMode=b.dataset.filter;document.querySelectorAll("[data-filter]").forEach(x=>x.classList.toggle("active",x===b));if(DATA)draw(DATA.stocks)}));
 $("#sortSelect").addEventListener("change",e=>{sortMode=e.target.value;if(DATA)draw(DATA.stocks)});document.addEventListener("keydown",e=>{if(e.key==="Escape")closeManager()});
}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",load,{once:true});else load();
})();