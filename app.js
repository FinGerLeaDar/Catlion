let DATA = null;

const $ = (selector) => document.querySelector(selector);
const WATCHLIST_ORDER = [
  "ONDS","NVDA","AMD","TSLA","AAPL","MSFT","AMZN","META","GOOGL","AVGO","PLTR","SOFI","RKLB","SPY","QQQ"
];

async function load() {
  try {
    const response = await fetch("data.json?" + Date.now(), { cache: "no-store" });
    if (!response.ok) throw new Error("data.json HTTP " + response.status);
    DATA = await response.json();
    render(DATA);
  } catch (error) {
    console.error(error);
    ["#watchlistStocks", "#trendingStocks"].forEach((id) => {
      $(id).innerHTML = '<div class="card empty">暫時讀取不到 data.json。<div class="hint">請稍後重新整理頁面。</div></div>';
    });
  }
}

function render(data) {
  const stocks = Array.isArray(data.stocks) ? data.stocks : [];
  const source = data.sources?.Stocktwits || {};
  const watchlist = stocks.filter(s => s.discovery === "watchlist");
  const trending = stocks.filter(s => s.discovery === "trending");

  $("#updated").textContent = "更新：" + formatDate(data.generated_at);
  $("#watchlistNote").textContent = `${watchlist.length} 隻 · ${source.messages || 0} messages total`;
  $("#trendingNote").textContent = `${trending.length} 隻`;

  $("#stats").innerHTML = `
    <div class="stat"><span class="stat-label">監察股票 / ETF</span><b>${stocks.length}</b></div>
    <div class="stat"><span class="stat-label">固定 Watchlist</span><b>${watchlist.length}</b></div>
    <div class="stat"><span class="stat-label">Trending 新發現</span><b>${trending.length}</b></div>
  `;

  draw(stocks);
}

function draw(stocks) {
  const q = ($("#search").value || "").trim().toLowerCase();
  const matches = stocks.filter((stock) =>
    !q ||
    String(stock.ticker || "").toLowerCase().includes(q) ||
    String(stock.name || "").toLowerCase().includes(q)
  );

  const watchlist = matches
    .filter(s => s.discovery === "watchlist")
    .sort((a, b) => watchlistRank(a.ticker) - watchlistRank(b.ticker));
  const trending = matches
    .filter(s => s.discovery === "trending")
    .sort((a, b) => Number(a.rank ?? 9999) - Number(b.rank ?? 9999) || String(a.ticker).localeCompare(String(b.ticker)));

  $("#watchlistStocks").innerHTML = watchlist.length
    ? watchlist.map(renderCard).join("")
    : emptyMessage(q ? `找不到「${esc(q)}」的 Watchlist 股票。` : "目前沒有 Watchlist 資料。");

  $("#trendingStocks").innerHTML = trending.length
    ? trending.map(renderCard).join("")
    : emptyMessage(q ? `找不到「${esc(q)}」的 Trending 股票。` : "今日沒有額外 Trending 資料。");

  $("#clearSearch").style.display = q ? "block" : "none";
}

function renderCard(stock) {
  const bullish = Number(stock.bullish || 0);
  const neutral = Number(stock.neutral || 0);
  const bearish = Number(stock.bearish || 0);
  const score = Number(stock.sentiment_score ?? 50);
  const confidence = Math.round(Number(stock.confidence || 0) * 100);
  const badge = stock.discovery === "watchlist"
    ? '<span class="badge watch">⭐ WATCHLIST</span>'
    : '<span class="badge trend">🔥 TRENDING</span>';

  return `
    <article class="card">
      <div class="card-head">
        <div>
          <div class="ticker">${esc(stock.ticker)} ${badge}</div>
          <div class="name">${esc(stock.name || "")}${stock.exchange ? " · " + esc(stock.exchange) : ""}</div>
        </div>
        <div class="score">${score.toFixed(1)}<small>SENTIMENT / 100</small></div>
      </div>

      <div class="bar" title="Bullish ${bullish}%"><i style="width:${Math.max(0, Math.min(100, bullish))}%"></i></div>

      <div class="numbers">
        <span>🟢 ${bullish}%</span>
        <span>⚪ 未標記 ${neutral}%</span>
        <span>🔴 ${bearish}%</span>
      </div>

      <div class="meta">
        ${stock.mention_count || 0} messages · tagged ${stock.tagged_count || 0} · confidence ${confidence}%
      </div>

      <div class="summary">${esc(stock.summary || "暫無趨勢摘要。")}</div>

      <div class="links">
        <a target="_blank" rel="noopener noreferrer" href="${esc(stock.source_url || "#")}">Stocktwits ↗</a>
        ${(stock.messages || []).slice(0, 3).map((message) =>
          `<a target="_blank" rel="noopener noreferrer" href="${esc(message.url || "#")}">${esc(message.sentiment || "message")} ↗</a>`
        ).join("")}
      </div>
    </article>
  `;
}

function emptyMessage(message) {
  return `<div class="card empty">${message}<div class="hint">清除搜尋可以恢復完整列表。</div></div>`;
}

function watchlistRank(ticker) {
  const index = WATCHLIST_ORDER.indexOf(String(ticker || "").toUpperCase());
  return index === -1 ? 9999 : index;
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);

  return date.toLocaleString("zh-HK", {
    timeZone: "Asia/Hong_Kong",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[char]));
}

$("#search").addEventListener("input", () => {
  if (DATA) draw(DATA.stocks || []);
});

$("#clearSearch").addEventListener("click", () => {
  $("#search").value = "";
  $("#search").focus();
  if (DATA) draw(DATA.stocks || []);
});

load();
