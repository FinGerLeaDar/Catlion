let DATA=null;
const $=s=>document.querySelector(s);
async function load(){
  try{
    const r=await fetch("data.json?"+Date.now());
    DATA=await r.json();
    render(DATA);
  }catch(e){
    $("#stocks").innerHTML='<div class="card">暫時讀取不到 data.json。</div>';
  }
}
function render(d){
  $("#updated").textContent=`更新：${d.generated_at||"—"}`;
  $("#sourceNote").textContent=`來源：${(d.sources||[]).join(" · ")}`;
  const stocks=d.stocks||[];
  const posts=stocks.reduce((n,s)=>n+(s.mentions||0),0);
  $("#stats").innerHTML=`
    <div class="stat">股票數量<b>${stocks.length}</b></div>
    <div class="stat">討論量<b>${posts}</b></div>
    <div class="stat">資料來源<b>${(d.sources||[]).length}</b></div>`;
  draw(stocks);
}
function draw(stocks){
  const q=($("#search").value||"").trim().toLowerCase();
  const list=stocks.filter(s=>!q||s.ticker.toLowerCase().includes(q)||String(s.name||"").toLowerCase().includes(q));
  $("#stocks").innerHTML=list.map(s=>{
    const b=s.sentiment?.bullish||0,n=s.sentiment?.neutral||0,be=s.sentiment?.bearish||0;
    return `<article class="card">
      <div class="ticker">${esc(s.ticker)}</div><div class="name">${esc(s.name||"")}</div>
      <div class="bar"><i style="width:${Math.max(0,Math.min(100,b))}%"></i></div>
      <div class="numbers"><span>🟢 ${b}%</span><span>⚪ ${n}%</span><span>🔴 ${be}%</span></div>
      <div class="summary">${esc(s.summary||"暫無摘要")}</div>
      <div class="links">${(s.posts||[]).slice(0,3).map(p=>`<a target="_blank" rel="noopener" href="${esc(p.url)}">${esc(p.source)}</a>`).join("")}</div>
    </article>`;
  }).join("") || '<div class="card">找不到相關股票。</div>';
}
function esc(v){return String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
$("#search").addEventListener("input",()=>DATA&&draw(DATA.stocks||[]));
load();
