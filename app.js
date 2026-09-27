let DATA = null;

const $ = (selector) => document.querySelector(selector);

async function load() {
  try {
    const response = await fetch("data.json?" + Date.now());
    if (!response.ok) throw new Error("data.json HTTP " + response.status);
    DATA = await response.json();
    render(DATA);
  } catch (error) {
    console.error(error);
    $("#stocks").innerHTML =
      '<div class="card">暫時讀取不到 data.json。</div>';
  }
}

function render(data) {
  const stocks = Array.isArray(data.stocks) ? data.stocks : [];
  const source = data.sources?.Stocktwits || {};

  $("#updated").textContent = "更新：" + formatDate(data.generated_at);

  $("#sourceNote").textContent =
    `Stocktwits · Watchlist ${source.watchlist_symbols || 0} · ` +
    `Trending ${source.trending_symbols || 0} · ` +
    `${source.messages || 0} messages`;

  const watchlistCount = stocks.filter(s => s.discovery === "watchlist").length;
  const trendingOnlyCount = stocks.filter(s => s.discovery === "trending").length;

  $("#stats").innerHTML = `
    <div class="stat">監察股票 / ETF<b>${stocks.length}</b></div>
    <div class="stat">固定 Watchlist<b>${watchlistCount}</b></div>
    <div class="stat">Trending 新發現<b>${trendingOnlyCount}</b></div>
  `;

  draw(stocks);
}

function draw(stocks) {
  const q = ($("#search").value || "").trim().toLowerCase();

  const list = stocks
    .filter((stock) =>
      !q ||
      stock.ticker.toLowerCase().includes(q) ||
      String(stock.name || "").toLowerCase().includes(q)
    )
    .sort((a, b) => {
      const aw = a.discovery === "watchlist" ? 0 : 1;
      const bw = b.discovery === "watchlist" ? 0 : 1;
      if (aw !== bw) return aw - bw;
      return Number(b.sentiment_score || 0) - Number(a.sentiment_score || 0);
    });

  $("#stocks").innerHTML = list.map((stock) => {
    const bullish = Number(stock.bullish || 0);
    const neutral = Number(stock.neutral || 0);
    const bearish = Number(stock.bearish || 0);
    const score = Number(stock.sentiment_score ?? 50);
    const badge =
      stock.discovery === "watchlist"
        ? '<span class="badge watch">⭐ WATCHLIST</span>'
        : '<span class="badge trend">🔥 TRENDING</span>';

    return `
      <article class="card">
        <div class="card-head">
          <div>
            <div class="ticker">${esc(stock.ticker)} ${badge}</div>
            <div class="name">${esc(stock.name || "")}${stock.exchange ? " · " + esc(stock.exchange) : ""}</div>
          </div>
          <div class="score">${score.toFixed(1)}</div>
        </div>

        <div class="bar">
          <i style="width:${Math.max(0, Math.min(100, bullish))}%"></i>
        </div>

        <div class="numbers">
          <span>🟢 ${bullish}%</span>
          <span>⚪ 未標記 ${neutral}%</span>
          <span>🔴 ${bearish}%</span>
        </div>

        <div class="meta">
          ${stock.mention_count || 0} messages ·
          tagged ${stock.tagged_count || 0} ·
          confidence ${Math.round(Number(stock.confidence || 0) * 100)}%
        </div>

        <div class="summary">
          ${esc(stock.summary || "暫無趨勢摘要。")}
        </div>

        <div class="links">
          <a target="_blank" rel="noopener" href="${esc(stock.source_url)}">Stocktwits</a>
          ${(stock.messages || []).slice(0, 3).map((message) =>
            `<a target="_blank" rel="noopener" href="${esc(message.url)}">${esc(message.sentiment)}</a>`
          ).join("")}
        </div>
      </article>
    `;
  }).join("") || '<div class="card">找不到相關美股 / ETF。</div>';
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
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  }[char]));
}

$("#search").addEventListener("input", () => {
  if (DATA) draw(DATA.stocks || []);
});

load();
