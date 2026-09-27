(() => {
  "use strict";

  let DATA = null;
  const WATCHLIST_ORDER = [
    "ONDS","NVDA","AMD","TSLA","AAPL","MSFT","AMZN","META","GOOGL","AVGO","PLTR","SOFI","RKLB","SPY","QQQ"
  ];

  const $ = (selector) => document.querySelector(selector);

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[char]));
  }

  function num(value, fallback = 0) {
    const n = Number(value);
    return Number.isFinite(n) ? n : fallback;
  }

  function clamp(value) {
    return Math.max(0, Math.min(100, num(value)));
  }

  function safeUrl(value) {
    const raw = String(value || "#");
    try {
      const url = new URL(raw, window.location.href);
      return (url.protocol === "https:" || url.protocol === "http:") ? esc(url.href) : "#";
    } catch (_) {
      return "#";
    }
  }

  function formatDate(value) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString("zh-HK", {
      timeZone: "Asia/Hong_Kong",
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit"
    });
  }

  function setStatus(text, error = false) {
    const el = $("#loadStatus");
    if (!el) return;
    el.textContent = text;
    el.classList.toggle("status-error", error);
  }

  function watchlistRank(ticker) {
    const index = WATCHLIST_ORDER.indexOf(String(ticker || "").toUpperCase());
    return index === -1 ? 9999 : index;
  }

  async function fetchData() {
    // Relative path is important for GitHub Pages project sites such as /Catlion/.
    const candidates = ["./data.json", "data.json"];
    let lastError = null;

    for (const path of candidates) {
      try {
        const url = `${path}?v=${Date.now()}`;
        const response = await fetch(url, {
          cache: "no-store",
          headers: { "Accept": "application/json" }
        });
        if (!response.ok) throw new Error(`${path} HTTP ${response.status}`);
        const data = await response.json();
        if (!data || !Array.isArray(data.stocks)) {
          throw new Error(`${path} 沒有有效的 stocks[]`);
        }
        return data;
      } catch (error) {
        lastError = error;
      }
    }

    throw lastError || new Error("無法讀取 data.json");
  }

  async function load() {
    setStatus("正在讀取 data.json…");
    try {
      const data = await fetchData();
      DATA = data;
      render(data);
      setStatus(`已載入 ${data.stocks.length} 隻股票 / ETF`);
    } catch (error) {
      console.error("Catlion data load error:", error);
      setStatus("資料讀取失敗", true);
      showError(error);
    }
  }

  function render(data) {
    const stocks = data.stocks.filter(Boolean);
    const watchlist = stocks.filter(s => s.discovery === "watchlist");
    const trending = stocks.filter(s => s.discovery === "trending");

    const source = data.sources && data.sources.Stocktwits ? data.sources.Stocktwits : {};
    const updated = $("#updated");
    if (updated) updated.textContent = "更新：" + formatDate(data.generated_at);

    const watchNote = $("#watchlistNote");
    const trendNote = $("#trendingNote");
    if (watchNote) watchNote.textContent = `${watchlist.length} 隻 · ${source.messages || 0} messages total`;
    if (trendNote) trendNote.textContent = `${trending.length} 隻`;

    const stats = $("#stats");
    if (stats) {
      stats.innerHTML = `
        <div class="stat"><span class="stat-label">監察股票 / ETF</span><b>${stocks.length}</b></div>
        <div class="stat"><span class="stat-label">固定 Watchlist</span><b>${watchlist.length}</b></div>
        <div class="stat"><span class="stat-label">Trending 新發現</span><b>${trending.length}</b></div>`;
    }

    draw(stocks);
  }

  function draw(stocks) {
    const input = $("#search");
    const q = (input ? input.value : "").trim().toLowerCase();

    const matches = stocks.filter((stock) => {
      if (!q) return true;
      const ticker = String(stock.ticker || "").toLowerCase();
      const name = String(stock.name || "").toLowerCase();
      return ticker.includes(q) || name.includes(q);
    });

    const watchlist = matches
      .filter(s => s.discovery === "watchlist")
      .sort((a, b) => watchlistRank(a.ticker) - watchlistRank(b.ticker));

    const trending = matches
      .filter(s => s.discovery === "trending")
      .sort((a, b) => Number(a.rank ?? 9999) - Number(b.rank ?? 9999));

    const watchEl = $("#watchlistStocks");
    const trendEl = $("#trendingStocks");

    if (watchEl) {
      watchEl.innerHTML = watchlist.length
        ? watchlist.map(renderCardSafe).join("")
        : emptyMessage(q ? `找不到「${esc(q)}」的 Watchlist 股票。` : "目前沒有 Watchlist 資料。");
    }

    if (trendEl) {
      trendEl.innerHTML = trending.length
        ? trending.map(renderCardSafe).join("")
        : emptyMessage(q ? `找不到「${esc(q)}」的 Trending 股票。` : "今日沒有額外 Trending 資料。");
    }

    const clear = $("#clearSearch");
    if (clear) clear.style.display = q ? "block" : "none";
  }

  function renderCardSafe(stock) {
    try {
      return renderCard(stock);
    } catch (error) {
      console.error("Card render error:", stock && stock.ticker, error);
      return `<article class="card error-card"><b>${esc(stock && stock.ticker || "UNKNOWN")}</b><div>此股票資料格式有問題。</div></article>`;
    }
  }

  function renderCard(stock) {
    const bullish = num(stock.bullish);
    const neutral = num(stock.neutral);
    const bearish = num(stock.bearish);
    const score = num(stock.sentiment_score, 50);
    const confidence = Math.round(num(stock.confidence) * 100);
    const messages = Array.isArray(stock.messages) ? stock.messages : [];
    const badge = stock.discovery === "watchlist"
      ? '<span class="badge watch">⭐ WATCHLIST</span>'
      : '<span class="badge trend">🔥 TRENDING</span>';

    const messageLinks = messages.slice(0, 3).map((message) => {
      const sentiment = esc(message && message.sentiment || "message");
      return `<a target="_blank" rel="noopener noreferrer" href="${safeUrl(message && message.url)}">${sentiment} ↗</a>`;
    }).join("");

    return `
      <article class="card">
        <div class="card-head">
          <div>
            <div class="ticker">${esc(stock.ticker || "—")} ${badge}</div>
            <div class="name">${esc(stock.name || "")}${stock.exchange ? " · " + esc(stock.exchange) : ""}</div>
          </div>
          <div class="score">${score.toFixed(1)}<small>SENTIMENT / 100</small></div>
        </div>
        <div class="bar" title="Bullish ${bullish}%"><i style="width:${clamp(bullish)}%"></i></div>
        <div class="numbers">
          <span>🟢 ${bullish}%</span>
          <span>⚪ 未標記 ${neutral}%</span>
          <span>🔴 ${bearish}%</span>
        </div>
        <div class="meta">${num(stock.mention_count)} messages · tagged ${num(stock.tagged_count)} · confidence ${confidence}%</div>
        <div class="summary">${esc(stock.summary || "暫無趨勢摘要。")}</div>
        <div class="links">
          <a target="_blank" rel="noopener noreferrer" href="${safeUrl(stock.source_url)}">Stocktwits ↗</a>
          ${messageLinks}
        </div>
      </article>`;
  }

  function emptyMessage(message) {
    return `<div class="card empty">${message}<div class="hint">清除搜尋可以恢復完整列表。</div></div>`;
  }

  function showError(error) {
    const message = error && error.message ? error.message : String(error);
    const stats = $("#stats");
    if (stats) {
      stats.innerHTML = `<div class="card empty"><b>⚠️ Catlion 暫時讀不到 data.json</b><div class="hint">${esc(message)}<br><br>請按 Ctrl + F5 再試一次。如果仍然失敗，將呢個錯誤畫面影畀我。</div></div>`;
    }
    const watch = $("#watchlistStocks");
    const trend = $("#trendingStocks");
    if (watch) watch.innerHTML = "";
    if (trend) trend.innerHTML = "";
  }

  function init() {
    const search = $("#search");
    const clear = $("#clearSearch");

    if (!search) {
      showError(new Error("找不到搜尋框 #search"));
      return;
    }

    search.addEventListener("input", () => {
      if (DATA) draw(DATA.stocks);
    });

    if (clear) {
      clear.addEventListener("click", () => {
        search.value = "";
        search.focus();
        if (DATA) draw(DATA.stocks);
      });
    }

    load();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
