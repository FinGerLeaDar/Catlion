(() => {
  "use strict";

  let DATA = null;
  let CONFIG_WATCHLIST = [];
  let WATCHLIST = [];
  let filterMode = "all";
  let sortMode = "my-order";

  const DEFAULT_WATCHLIST = [
    "ONDS","NVDA","AMD","TSLA","AAPL","MSFT","AMZN","META","GOOGL","AVGO",
    "PLTR","SOFI","RKLB","SPY","QQQ"
  ];

  const SORT_OPTIONS = {
    "my-order": "我的順序",
    "score-desc": "Sentiment 高 → 低",
    "score-asc": "Sentiment 低 → 高",
    "bullish-desc": "Bullish % 高 → 低",
    "bearish-desc": "Bearish % 高 → 低",
    "messages-desc": "Messages 多 → 少",
    "confidence-desc": "Confidence 高 → 低",
    "ticker-asc": "Ticker A → Z"
  };

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

  function normalizeWatchlist(list) {
    return [...new Set(
      (Array.isArray(list) ? list : [])
        .map(x => String(x || "").trim().toUpperCase())
        .filter(x => /^[A-Z][A-Z0-9.-]{0,9}$/.test(x))
    )];
  }

  function loadLocalWatchlist() {
    try {
      const saved = JSON.parse(localStorage.getItem("catlion_watchlist") || "null");
      return normalizeWatchlist(saved);
    } catch (_) {
      return [];
    }
  }

  function saveLocalWatchlist(list) {
    localStorage.setItem("catlion_watchlist", JSON.stringify(normalizeWatchlist(list)));
  }

  function clearLocalWatchlist() {
    localStorage.removeItem("catlion_watchlist");
  }

  function watchlistRank(ticker) {
    const index = WATCHLIST.indexOf(String(ticker || "").toUpperCase());
    return index === -1 ? 9999 : index;
  }

  async function fetchJson(path) {
    const response = await fetch(`${path}?v=${Date.now()}`, {
      cache: "no-store",
      headers: { "Accept": "application/json" }
    });
    if (!response.ok) throw new Error(`${path} HTTP ${response.status}`);
    return response.json();
  }

  async function fetchData() {
    let lastError = null;
    for (const path of ["./data.json", "data.json"]) {
      try {
        const data = await fetchJson(path);
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

  async function fetchWatchlistConfig(data) {
    try {
      const config = await fetchJson("./watchlist.json");
      if (config && Array.isArray(config.watchlist)) {
        CONFIG_WATCHLIST = normalizeWatchlist(config.watchlist);
        return;
      }
    } catch (_) {}

    CONFIG_WATCHLIST = normalizeWatchlist(data.watchlist);
    if (!CONFIG_WATCHLIST.length) CONFIG_WATCHLIST = DEFAULT_WATCHLIST.slice();
  }

  async function load() {
    setStatus("正在讀取 data.json / watchlist.json…");
    try {
      DATA = await fetchData();
      await fetchWatchlistConfig(DATA);

      const local = loadLocalWatchlist();
      WATCHLIST = local.length ? local : CONFIG_WATCHLIST.slice();

      render(DATA);
      bindControls();
      setStatus(
        local.length
          ? `已載入 ${DATA.stocks.length} 隻；使用本機 Watchlist ${WATCHLIST.length} 隻`
          : `已載入 ${DATA.stocks.length} 隻；Watchlist ${WATCHLIST.length} 隻`
      );
    } catch (error) {
      console.error("Catlion load error:", error);
      setStatus("資料讀取失敗", true);
      showError(error);
    }
  }

  function render(data) {
    const stocks = data.stocks.filter(Boolean);
    const updated = $("#updated");
    if (updated) updated.textContent = "更新：" + formatDate(data.generated_at);

    const stats = $("#stats");
    if (stats) {
      stats.innerHTML = `
        <div class="stat"><span class="stat-label">監察股票 / ETF</span><b>${stocks.length}</b></div>
        <div class="stat"><span class="stat-label">我的 Watchlist</span><b id="statWatchlist">${WATCHLIST.length}</b></div>
        <div class="stat"><span class="stat-label">Trending 新發現</span><b id="statTrending">0</b></div>`;
    }

    draw(stocks);
  }

  function applyFilter(stocks) {
    return stocks.filter(stock => {
      if (filterMode === "all") return true;
      if (filterMode === "bullish") return num(stock.bullish) >= 50;
      if (filterMode === "neutral") return num(stock.neutral) >= 50;
      if (filterMode === "bearish") return num(stock.bearish) >= 10;
      return true;
    });
  }

  function compareStocks(a, b) {
    if (sortMode === "my-order") return watchlistRank(a.ticker) - watchlistRank(b.ticker);
    if (sortMode === "score-desc") return num(b.sentiment_score) - num(a.sentiment_score);
    if (sortMode === "score-asc") return num(a.sentiment_score) - num(b.sentiment_score);
    if (sortMode === "bullish-desc") return num(b.bullish) - num(a.bullish);
    if (sortMode === "bearish-desc") return num(b.bearish) - num(a.bearish);
    if (sortMode === "messages-desc") return num(b.mention_count) - num(a.mention_count);
    if (sortMode === "confidence-desc") return num(b.confidence) - num(a.confidence);
    if (sortMode === "ticker-asc") return String(a.ticker || "").localeCompare(String(b.ticker || ""));
    return 0;
  }

  function draw(stocks) {
    const q = ($("#search")?.value || "").trim().toLowerCase();
    const watchTickers = new Set(WATCHLIST);
    const filtered = applyFilter(stocks);

    const matchesSearch = (stock) => {
      if (!q) return true;
      return String(stock.ticker || "").toLowerCase().includes(q) ||
             String(stock.name || "").toLowerCase().includes(q);
    };

    const watchlist = filtered
      .filter(s => watchTickers.has(String(s.ticker || "").toUpperCase()))
      .filter(matchesSearch)
      .sort(compareStocks);

    const trending = filtered
      .filter(s => {
        const ticker = String(s.ticker || "").toUpperCase();
        return s.discovery === "trending" && !watchTickers.has(ticker);
      })
      .filter(matchesSearch)
      .sort((a, b) => Number(a.rank ?? 9999) - Number(b.rank ?? 9999));

    // New local additions appear immediately as PENDING until the next GitHub Actions run.
    const existing = new Set(stocks.map(s => String(s.ticker || "").toUpperCase()));
    const missing = WATCHLIST
      .filter(ticker => !existing.has(ticker))
      .filter(ticker => !q || ticker.toLowerCase().includes(q))
      .filter(() => filterMode === "all")
      .map(ticker => ({
        ticker,
        name: "等待下一次 Stocktwits 更新",
        discovery: "watchlist",
        bullish: 0, neutral: 0, bearish: 0,
        sentiment_score: 50, confidence: 0,
        mention_count: 0, tagged_count: 0,
        summary: "已加入 Watchlist，但 data.json 尚未有最新資料。下一次 GitHub Actions 更新後會開始收集。",
        messages: [], pending: true
      }));

    const allWatch = [...watchlist, ...missing].sort(compareStocks);

    $("#watchlistStocks").innerHTML = allWatch.length
      ? allWatch.map(renderCardSafe).join("")
      : emptyMessage(q ? `找不到「${esc(q)}」的 Watchlist 股票。` : "目前沒有符合條件的 Watchlist。");

    $("#trendingStocks").innerHTML = trending.length
      ? trending.map(renderCardSafe).join("")
      : emptyMessage(q ? `找不到「${esc(q)}」的 Trending 股票。` : "今日沒有符合條件的 Trending 資料。");

    const statWatch = $("#statWatchlist");
    if (statWatch) statWatch.textContent = WATCHLIST.length;

    const statTrend = $("#statTrending");
    if (statTrend) statTrend.textContent = trending.length;

    $("#watchlistNote").textContent = `${WATCHLIST.length} 隻 · ${SORT_OPTIONS[sortMode]}`;
    $("#trendingNote").textContent = `${trending.length} 隻`;
    $("#clearSearch").style.display = q ? "block" : "none";
  }

  function renderCardSafe(stock) {
    try {
      return renderCard(stock);
    } catch (error) {
      console.error("Card render error:", stock?.ticker, error);
      return `<article class="card error-card"><b>${esc(stock?.ticker || "UNKNOWN")}</b><div>此股票資料格式有問題。</div></article>`;
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
    const pending = stock.pending ? '<span class="badge pending">⏳ PENDING</span>' : "";

    const messageLinks = messages.slice(0, 3).map(message => {
      return `<a target="_blank" rel="noopener noreferrer" href="${safeUrl(message?.url)}">${esc(message?.sentiment || "message")} ↗</a>`;
    }).join("");

    return `
      <article class="card">
        <div class="card-head">
          <div>
            <div class="ticker">${esc(stock.ticker || "—")} ${badge}${pending}</div>
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
          ${stock.source_url ? `<a target="_blank" rel="noopener noreferrer" href="${safeUrl(stock.source_url)}">Stocktwits ↗</a>` : ""}
          ${messageLinks}
        </div>
      </article>`;
  }

  function emptyMessage(message) {
    return `<div class="card empty">${message}<div class="hint">可以用 Manage Watchlist / Filter / Sort 調整顯示。</div></div>`;
  }

  function showError(error) {
    const message = error?.message || String(error);
    $("#stats").innerHTML = `<div class="card empty"><b>⚠️ Catlion 暫時讀不到 data.json</b><div class="hint">${esc(message)}<br><br>請按 Ctrl + F5 再試一次。</div></div>`;
    $("#watchlistStocks").innerHTML = "";
    $("#trendingStocks").innerHTML = "";
  }

  function openManager() {
    const modal = $("#watchlistModal");
    const list = $("#manageList");
    if (!modal || !list) return;

    list.innerHTML = WATCHLIST.map(ticker => `
      <div class="manage-row" draggable="true" data-ticker="${esc(ticker)}">
        <span class="drag">☷</span>
        <b>${esc(ticker)}</b>
        <span class="manage-spacer"></span>
        <button type="button" class="remove-ticker" data-ticker="${esc(ticker)}" title="移除">×</button>
      </div>`).join("");

    modal.classList.add("open");
    modal.setAttribute("aria-hidden", "false");
    bindDragAndDrop();

    list.querySelectorAll(".remove-ticker").forEach(button => {
      button.addEventListener("click", () => removeTicker(button.dataset.ticker));
    });
  }

  function closeManager() {
    const modal = $("#watchlistModal");
    if (!modal) return;
    modal.classList.remove("open");
    modal.setAttribute("aria-hidden", "true");
  }

  function addTicker() {
    const input = $("#addTicker");
    const ticker = input.value.trim().toUpperCase();

    if (!/^[A-Z][A-Z0-9.-]{0,9}$/.test(ticker)) {
      setStatus("Ticker 格式唔正確，例如 ONDS / NVDA / SPY", true);
      input.focus();
      return;
    }

    if (WATCHLIST.includes(ticker)) {
      setStatus(`${ticker} 已經喺 Watchlist`);
      input.value = "";
      return;
    }

    WATCHLIST.push(ticker);
    saveLocalWatchlist(WATCHLIST);
    input.value = "";
    openManager();
    draw(DATA.stocks);
    setStatus(`${ticker} 已加入；下一次 collector 更新前會顯示 PENDING`);
  }

  function removeTicker(ticker) {
    WATCHLIST = WATCHLIST.filter(x => x !== ticker);
    saveLocalWatchlist(WATCHLIST);
    openManager();
    draw(DATA.stocks);
    setStatus(`${ticker} 已移除`);
  }

  function saveManagerOrder() {
    const tickers = [...document.querySelectorAll(".manage-row")]
      .map(row => row.dataset.ticker)
      .filter(Boolean);

    WATCHLIST = normalizeWatchlist(tickers);
    saveLocalWatchlist(WATCHLIST);
    draw(DATA.stocks);
    closeManager();
    setStatus("Watchlist 順序已儲存到本機");
  }

  function resetWatchlist() {
    WATCHLIST = CONFIG_WATCHLIST.slice();
    clearLocalWatchlist();
    openManager();
    draw(DATA.stocks);
    setStatus("已恢復 Repo Watchlist");
  }

  function exportWatchlist() {
    const payload = JSON.stringify({ watchlist: WATCHLIST }, null, 2);
    const blob = new Blob([payload], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "watchlist.json";
    a.click();
    URL.revokeObjectURL(url);
    setStatus("已輸出 watchlist.json；放返 repo 根目錄後，GitHub Actions 就會用新名單。");
  }

  function bindDragAndDrop() {
    const rows = [...document.querySelectorAll(".manage-row")];
    let dragging = null;

    rows.forEach(row => {
      row.addEventListener("dragstart", () => {
        dragging = row;
        row.classList.add("dragging");
      });
      row.addEventListener("dragend", () => {
        row.classList.remove("dragging");
        dragging = null;
      });
      row.addEventListener("dragover", event => {
        event.preventDefault();
        if (!dragging || dragging === row) return;
        const rect = row.getBoundingClientRect();
        const before = event.clientY < rect.top + rect.height / 2;
        row.parentNode.insertBefore(dragging, before ? row : row.nextSibling);
      });
    });
  }

  function bindControls() {
    $("#search").addEventListener("input", () => DATA && draw(DATA.stocks));

    $("#clearSearch").addEventListener("click", () => {
      $("#search").value = "";
      $("#search").focus();
      if (DATA) draw(DATA.stocks);
    });

    $("#manageWatchlist").addEventListener("click", openManager);
    $("#closeModal").addEventListener("click", closeManager);

    $("#watchlistModal").addEventListener("click", event => {
      if (event.target === $("#watchlistModal")) closeManager();
    });

    $("#addTickerBtn").addEventListener("click", addTicker);
    $("#addTicker").addEventListener("keydown", event => {
      if (event.key === "Enter") addTicker();
    });

    $("#saveManager").addEventListener("click", saveManagerOrder);
    $("#resetWatchlist").addEventListener("click", resetWatchlist);
    $("#exportWatchlist").addEventListener("click", exportWatchlist);

    document.querySelectorAll("[data-filter]").forEach(button => {
      button.addEventListener("click", () => {
        filterMode = button.dataset.filter;
        document.querySelectorAll("[data-filter]").forEach(b => b.classList.toggle("active", b === button));
        if (DATA) draw(DATA.stocks);
      });
    });

    $("#sortSelect").addEventListener("change", event => {
      sortMode = event.target.value;
      if (DATA) draw(DATA.stocks);
    });

    document.addEventListener("keydown", event => {
      if (event.key === "Escape") closeManager();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", load, { once: true });
  } else {
    load();
  }
})();