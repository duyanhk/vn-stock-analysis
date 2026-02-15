document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("analyze-form");
  if (!form) return;

  const statusEl = document.getElementById("status");
  const downloadLink = document.getElementById("downloadLink");

  const runUrl = form.getAttribute("data-run-url");
  const runPeersUrl = form.getAttribute("data-run-peers-url") || "/run_peers";
  const downloadTemplate = form.getAttribute("data-download-url-template");
  const sampleTickersUrl = form.getAttribute("data-sample-tickers-url") || "/sample_tickers";

  // Store current records, symbol, market data, and shares outstanding
  let currentRecords = [];
  let currentSymbol = "";
  let currentMarketData = [];
  let currentCompanyName = null;
  let currentSectorIndustry = null;
  let currentPeers = [];
  let currentPeersNote = null;
  let currentPeerFilterMode = "all"; // "icb" | "broad" | "all" (default)
  let currentPeerValMetric = "pe"; // "pe" | "pb" | "ev" — which valuation metric to show in peer rows
  let currentPeerSortMode = "valuation"; // "valuation" (default, cheapest first) | "marketcap"
  let currentPeerScopeMode = "both"; // "around" | "top5" | "both" (default: top 5 + around)
  let currentPeerHaveDataOnly = true; // when true, only show peers with fetched valuation data (default on)
  let currentSharesOutstanding = null;
  let currentTimeframe = 5; // Default to 5 years
  let currentValuationTrendMode = "annual"; // "annual" (default) or "quarterly" (only when quarterly data exists)
  let currentFinancialsViewMode = "quarterly"; // "quarterly" | "annually" — which periods to show in Financials tab
  let currentEarningsMode = "actual"; // "actual" | "normalized" | "conservative" — used for quality, growth, valuation (chart unchanged)

  // Fetch available sample tickers
  (async function loadSampleTickersHint() {
    const hintEl = document.getElementById("sample-tickers-hint");
    if (!hintEl) return;
    try {
      const res = await fetch(sampleTickersUrl);
      const json = await res.json();
      const list = json.available_samples && Array.isArray(json.available_samples) ? json.available_samples : [];
      if (list.length > 0) {
        hintEl.textContent = `Available sample tickers: ${list.join(", ")}`;
        hintEl.style.display = "block";
      }
    } catch (_) {
      // ignore
    }
  })();

  function setStatus(message, kind) {
    if (!statusEl) return;
    statusEl.textContent = message || "";
    statusEl.className = "status";
    if (kind) {
      statusEl.classList.add(`status--${kind}`);
    }
  }

  function setLoading(isLoading) {
    const submitBtn = form.querySelector("button[type='submit']");
    const analyzeBtn = document.getElementById("analyze-btn");
    if (submitBtn) submitBtn.disabled = isLoading;
    if (analyzeBtn) analyzeBtn.disabled = isLoading;
  }

  function setFetchStatus(status, message) {
    const bar = document.getElementById("fetch-status-bar");
    const text = document.getElementById("fetch-status-text");
    if (!bar || !text) return;
    bar.className = "fetch-status-bar";
    if (status === "idle") {
      bar.style.display = "none";
      text.textContent = "";
      return;
    }
    bar.style.display = "block";
    text.textContent = message || status;
    if (status === "fetching_financials" || status === "fetching_peers" || status === "fetching_peer_valuations") {
      bar.classList.add("fetch-status-bar--active");
    } else if (status === "complete") {
      bar.classList.add("fetch-status-bar--complete");
    } else if (status === "error") {
      bar.classList.add("fetch-status-bar--error");
    }
  }

  function showEmptyState() {
    document.getElementById("empty-state").style.display = "flex";
    document.getElementById("section-quality").style.display = "none";
    document.getElementById("section-growth").style.display = "none";
    document.getElementById("section-valuation").style.display = "none";
    document.getElementById("section-tabs").style.display = "none";
    document.getElementById("stock-summary").style.display = "none";
  }

  function showDashboard() {
    document.getElementById("empty-state").style.display = "none";
    document.getElementById("section-quality").style.display = "block";
    document.getElementById("section-growth").style.display = "block";
    document.getElementById("section-valuation").style.display = "block";
    document.getElementById("section-tabs").style.display = "block";
    document.getElementById("stock-summary").style.display = "flex";
  }

  function formatPercent(value) {
    if (value == null || isNaN(value)) return "—";
    return (value * 100).toFixed(1) + "%";
  }

  function formatVND(value, isPrice = false) {
    if (value == null || isNaN(value)) return "—";
    
    // For prices (already in thousands), just add K suffix with 1 decimal
    if (isPrice) {
      return value.toFixed(1) + "K";
    }
    
    // For market cap and other large numbers, use appropriate suffix
    if (value >= 1e12) return (value / 1e12).toFixed(1) + "T";
    if (value >= 1e9) return (value / 1e9).toFixed(1) + "B";
    if (value >= 1e6) return (value / 1e6).toFixed(1) + "M";
    if (value >= 1e3) return (value / 1e3).toFixed(1) + "K";
    return value.toFixed(1);
  }

  function updateStockHeader(symbol, marketData, sharesOutstanding, companyName, sectorIndustry) {
    document.getElementById("stock-symbol").textContent = (symbol || "—").toUpperCase();
    document.getElementById("stock-name").textContent = (companyName && companyName.trim()) ? companyName.trim() : (symbol || "—");
    document.getElementById("stock-sector").textContent = (sectorIndustry && sectorIndustry.trim()) ? sectorIndustry.trim() : "—";
    const peerBtn = document.getElementById("peer-analysis-btn");
    if (peerBtn) peerBtn.style.display = (symbol && String(symbol).trim()) ? "inline-block" : "none";

    // Update price, 52W high-low, and market cap from market data (no extra backend — same payload)
    if (marketData && marketData.length > 0) {
      const latest = marketData[marketData.length - 1];
      if (latest.close != null) {
        document.getElementById("stock-price").textContent = formatVND(latest.close, true) + " VND";
      } else {
        document.getElementById("stock-price").textContent = "— VND";
      }

      const now = new Date();
      const cutoff = new Date(now);
      cutoff.setDate(cutoff.getDate() - 365);
      const last52w = marketData.filter((d) => {
        const t = typeof d.date === "string" ? new Date(d.date.replace(" 00:00:00", "")) : new Date(d.date);
        return !isNaN(t) && t >= cutoff && d.close != null && !isNaN(d.close);
      });
      const lineEl = document.getElementById("stock-52w-line");
      const barEl = document.getElementById("stock-52w-bar");
      const fillEl = document.getElementById("stock-52w-bar-fill");
      const tickerEl = document.getElementById("stock-52w-bar-ticker");
      const lowEl = document.getElementById("stock-52w-low");
      const highEl = document.getElementById("stock-52w-high");
      if (last52w.length > 0) {
        const high = Math.max(...last52w.map((d) => Number(d.close)));
        const low = Math.min(...last52w.map((d) => Number(d.close)));
        const current = latest.close != null ? Number(latest.close) : null;
        if (lowEl) lowEl.textContent = (low != null && !isNaN(low)) ? low.toFixed(1) : "—";
        if (highEl) highEl.textContent = (high != null && !isNaN(high)) ? high.toFixed(1) : "—";
        if (lineEl) lineEl.style.display = "flex";
        if (barEl && fillEl && tickerEl && current != null && high !== low) {
          const pct = Math.max(0, Math.min(1, (current - low) / (high - low)));
          fillEl.style.width = (pct * 100) + "%";
          tickerEl.style.left = (pct * 100) + "%";
          tickerEl.style.display = "block";
          barEl.style.display = "flex";
        } else if (barEl) {
          barEl.style.display = current != null && high === low ? "flex" : "none";
          if (fillEl) fillEl.style.width = "100%";
          if (tickerEl) tickerEl.style.display = high === low ? "block" : "none";
          if (tickerEl && high === low) tickerEl.style.left = "100%";
        }
      } else {
        if (lineEl) lineEl.style.display = "none";
        if (lowEl) lowEl.textContent = "—";
        if (highEl) highEl.textContent = "—";
        if (barEl) barEl.style.display = "none";
      }

      if (latest.close != null && sharesOutstanding != null && !isNaN(sharesOutstanding)) {
        const priceVND = latest.close * 1000;
        const marketCap = priceVND * sharesOutstanding;
        document.getElementById("stock-mktcap").textContent = formatVND(marketCap, false) + " VND";
      } else {
        document.getElementById("stock-mktcap").textContent = "— VND";
      }
    } else {
      const priceEl = document.getElementById("stock-price");
      if (priceEl) priceEl.textContent = "— VND";
      const lineEl = document.getElementById("stock-52w-line");
      if (lineEl) lineEl.style.display = "none";
      const low52El = document.getElementById("stock-52w-low");
      const high52El = document.getElementById("stock-52w-high");
      if (low52El) low52El.textContent = "—";
      if (high52El) high52El.textContent = "—";
      const barEl = document.getElementById("stock-52w-bar");
      if (barEl) barEl.style.display = "none";
      const mktcapEl = document.getElementById("stock-mktcap");
      if (mktcapEl) mktcapEl.textContent = "— VND";
    }
    // P/E and P/B header block is updated by updateHeaderPEPB() from valuation section (same data, no extra backend)
  }

  function getLatestValue(records, key) {
    const sorted = [...records]
      .filter((r) => r[key] != null && !isNaN(r[key]))
      .sort((a, b) => String(b.Period || "").localeCompare(String(a.Period || "")));
    return sorted.length > 0 ? sorted[0][key] : null;
  }

  function periodSortRank(p) {
    const s = String(p || "");
    if (s.endsWith("-FY")) return 5;
    if (s.endsWith("-Q4")) return 4;
    if (s.endsWith("-Q3")) return 3;
    if (s.endsWith("-Q2")) return 2;
    if (s.endsWith("-Q1")) return 1;
    return 0;
  }

  function getLatestValueWithPeriod(records, key) {
    const filtered = records.filter((r) => r[key] != null && !isNaN(r[key]));
    if (filtered.length === 0) return { value: null, period: null };

    const sorted = [...filtered].sort((a, b) => {
      const pa = String(a.Period || "");
      const pb = String(b.Period || "");
      const yearA = parseInt(pa.match(/^(\d{4})/)?.[1] || "0", 10);
      const yearB = parseInt(pb.match(/^(\d{4})/)?.[1] || "0", 10);
      if (yearA !== yearB) return yearB - yearA;
      return periodSortRank(pb) - periodSortRank(pa);
    });

    const latest = sorted[0];
    return { value: latest[key], period: latest.Period };
  }

  /** Parse Period "2024-Q2" or "2024-FY" to { year, q }. FY -> q = 4. */
  function parsePeriodToYearQ(period) {
    const s = String(period || "");
    const year = parseInt(s.match(/^(\d{4})/)?.[1] || "0", 10);
    if (s.endsWith("-Q4")) return { year, q: 4 };
    if (s.endsWith("-Q3")) return { year, q: 3 };
    if (s.endsWith("-Q2")) return { year, q: 2 };
    if (s.endsWith("-Q1")) return { year, q: 1 };
    if (s.endsWith("-FY")) return { year, q: 4 };
    return { year: 0, q: 0 };
  }

  /** Previous quarter: (y, q) -> (y, q-1) or (y-1, 4). */
  function previousQuarter(year, q) {
    if (q > 1) return { year, q: q - 1 };
    return { year: year - 1, q: 4 };
  }

  function quarterKey(year, q) {
    return `${year}-Q${q}`;
  }

  /** Parse market date "2024-06-15 00:00:00" or similar to { year, q }. */
  function parseDateToYearQ(dateStr) {
    const d = typeof dateStr === "string" ? new Date(dateStr.replace(" 00:00:00", "").trim()) : new Date(dateStr);
    if (isNaN(d.getTime())) return null;
    const year = d.getFullYear();
    const month = d.getMonth() + 1;
    const q = month <= 3 ? 1 : month <= 6 ? 2 : month <= 9 ? 3 : 4;
    return { year, q };
  }

  function getAnnualValues(records, key) {
    // Get annual (FY) values for a metric, sorted chronologically
    return records
      .filter((r) => String(r.Period || "").includes("-FY") && r[key] != null && !isNaN(r[key]))
      .sort((a, b) => String(a.Period || "").localeCompare(String(b.Period || "")))
      .map((r) => r[key]);
  }

  function getAnnualDataPoints(records, key) {
    // Get annual (FY) data points with period and value, sorted chronologically
    return records
      .filter((r) => String(r.Period || "").includes("-FY") && r[key] != null && !isNaN(r[key]))
      .sort((a, b) => String(a.Period || "").localeCompare(String(b.Period || "")))
      .map((r) => ({
        period: r.Period,
        value: r[key],
      }));
  }

  /** Sparkline data: FY points + latest quarter if that quarter is more recent than the latest FY. Deduplicated by period. */
  function getSparklineDataPoints(records, key) {
    let annual = getAnnualDataPoints(records, key);
    // Deduplicate by period (keep last) in case source has duplicate FY entries
    const seen = new Set();
    annual = annual.filter((p) => {
      const id = String(p.period || "");
      if (seen.has(id)) return false;
      seen.add(id);
      return true;
    });

    const latestFYPeriod = annual.length > 0 ? annual[annual.length - 1].period : "";
    const latestFYYear = latestFYPeriod ? parseInt(String(latestFYPeriod).match(/^(\d{4})/)?.[1] || "0", 10) : 0;

    const withKey = records.filter((r) => r[key] != null && !isNaN(r[key]));
    if (withKey.length === 0) return annual;

    const sortedAll = [...withKey].sort((a, b) => {
      const pa = String(a.Period || "");
      const pb = String(b.Period || "");
      const yearA = parseInt(pa.match(/^(\d{4})/)?.[1] || "0", 10);
      const yearB = parseInt(pb.match(/^(\d{4})/)?.[1] || "0", 10);
      if (yearA !== yearB) return yearA - yearB;
      return periodSortRank(pa) - periodSortRank(pb);
    });
    const latestRecord = sortedAll[sortedAll.length - 1];
    const latestPeriod = String(latestRecord.Period || "");
    const isQuarter = /-Q[1-4]$/i.test(latestPeriod);
    const latestRecordYear = latestPeriod ? parseInt(String(latestPeriod).match(/^(\d{4})/)?.[1] || "0", 10) : 0;
    const quarterMoreRecentThanFY = isQuarter && latestRecordYear > latestFYYear;

    if (quarterMoreRecentThanFY) {
      return [...annual, { period: latestRecord.Period, value: latestRecord[key] }];
    }
    return annual;
  }

  function calculateMedian(values) {
    if (!values || values.length === 0) return null;
    const sorted = [...values].sort((a, b) => a - b);
    const mid = Math.floor(sorted.length / 2);
    if (sorted.length % 2 === 0) {
      return (sorted[mid - 1] + sorted[mid]) / 2;
    }
    return sorted[mid];
  }

  /**
   * Compute 10-year medians for normalized earnings (from annual FY records only).
   * Returns { medianFinIncomeRatio, medianOtherProfitRatio, medianTaxRate } or nulls where not computable.
   * - Financial income ratio = Financial Income / (Cash + Cash Investment + Long Term Investments).
   * - Other profit ratio = (Profit Before Tax - Operating Profit) / Revenue.
   * - Tax rate = (Profit Before Tax - Net Profit) / Profit Before Tax.
   */
  function computeNormalizedEarningsMedians(records) {
    const annual = (records || [])
      .filter((r) => String(r.Period || "").endsWith("-FY"))
      .sort((a, b) => String(a.Period || "").localeCompare(String(b.Period || "")));
    const last10 = annual.slice(-10);
    if (last10.length === 0) return { medianFinIncomeRatio: null, medianOtherProfitRatio: null, medianTaxRate: null };

    const finRatios = [];
    const otherRatios = [];
    const taxRates = [];
    for (const r of last10) {
      const cash = r["Cash And Equivalent"];
      const cashInv = r["Cash Investment"];
      const lti = r["Long Term Investments"];
      const denom = (cash != null && !isNaN(cash) ? cash : 0) + (cashInv != null && !isNaN(cashInv) ? cashInv : 0) + (lti != null && !isNaN(lti) ? lti : 0);
      const finInc = r["Financial Income"];
      if (denom > 0 && finInc != null && !isNaN(finInc)) finRatios.push(finInc / denom);

      const rev = r.Revenue;
      const pbt = r["Profit Before Tax"];
      const op = r["Operating Income"];
      if (rev != null && !isNaN(rev) && rev !== 0 && pbt != null && !isNaN(pbt) && op != null && !isNaN(op)) {
        otherRatios.push((pbt - op) / rev);
      }
      const ni = r["Net Income"];
      if (pbt != null && !isNaN(pbt) && pbt !== 0 && ni != null && !isNaN(ni)) {
        taxRates.push((pbt - ni) / pbt);
      }
    }
    return {
      medianFinIncomeRatio: calculateMedian(finRatios),
      medianOtherProfitRatio: calculateMedian(otherRatios),
      medianTaxRate: calculateMedian(taxRates),
    };
  }

  /**
   * For one record, compute normalized net profit using:
   * 1. Normalized operating profit = actual operating profit - actual financial income + normalized financial income
   * 2. Normalized PBT = normalized operating profit - actual other profit + normalized other profit
   *    (actual other profit = PBT - Operating profit)
   * 3. Normalized net profit = Normalized PBT * (1 - median tax rate)
   */
  function computeNormalizedNetProfitForRecord(r, medians) {
    if (!medians) return null;
    const op = r["Operating Income"];
    const rev = r.Revenue;
    const pbt = r["Profit Before Tax"];
    const finIncActual = r["Financial Income"];
    const cash = r["Cash And Equivalent"];
    const cashInv = r["Cash Investment"];
    const lti = r["Long Term Investments"];
    if (op == null || isNaN(op)) return null;

    const denom = (cash != null && !isNaN(cash) ? cash : 0) + (cashInv != null && !isNaN(cashInv) ? cashInv : 0) + (lti != null && !isNaN(lti) ? lti : 0);
    const normFinInc = medians.medianFinIncomeRatio != null && !isNaN(medians.medianFinIncomeRatio) && denom > 0
      ? medians.medianFinIncomeRatio * denom
      : null;
    const finIncActualVal = finIncActual != null && !isNaN(finIncActual) ? finIncActual : 0;

    // 1. Normalized operating profit = actual operating profit - actual financial income + normalized financial income
    let normOpProfit = op - finIncActualVal;
    if (normFinInc != null) normOpProfit += normFinInc;

    // 2. Actual other profit = PBT - Operating profit; normalized other = median ratio * Revenue
    const actualOtherProfit = (pbt != null && !isNaN(pbt)) ? pbt - op : 0;
    const normOtherProfit = (medians.medianOtherProfitRatio != null && !isNaN(medians.medianOtherProfitRatio) && rev != null && !isNaN(rev))
      ? medians.medianOtherProfitRatio * rev
      : 0;
    const normPbt = normOpProfit - actualOtherProfit + normOtherProfit;

    // 3. Normalized net profit = Normalized PBT * (1 - median tax rate)
    const taxRate = medians.medianTaxRate;
    if (taxRate == null || isNaN(taxRate)) return null;
    return normPbt * (1 - taxRate);
  }

  /**
   * Conservative net profit:
   * (1) Conservative financial income = min(actual ratio, normalized ratio) × investment
   * (2) Conservative operating profit = actual operating profit - actual financial income + conservative financial income
   * (3) Conservative PBT = conservative operating profit - actual other + min(normalized other, actual other)
   * (4) Conservative net profit = conservative PBT × (1 - max(actual tax, normalized tax))
   */
  function computeConservativeNetProfitForRecord(r, medians) {
    const op = r["Operating Income"];
    const rev = r.Revenue;
    const pbt = r["Profit Before Tax"];
    const actualNet = r["Net Income"];
    const finIncActual = r["Financial Income"];
    const cash = r["Cash And Equivalent"];
    const cashInv = r["Cash Investment"];
    const lti = r["Long Term Investments"];
    if (op == null || isNaN(op) || pbt == null || isNaN(pbt)) return null;

    const investment = (cash != null && !isNaN(cash) ? cash : 0) + (cashInv != null && !isNaN(cashInv) ? cashInv : 0) + (lti != null && !isNaN(lti) ? lti : 0);
    const actualFinRatio = investment > 0 && finIncActual != null && !isNaN(finIncActual) ? finIncActual / investment : null;
    const normRatio = medians.medianFinIncomeRatio != null && !isNaN(medians.medianFinIncomeRatio) ? medians.medianFinIncomeRatio : null;
    const conservativeFinRatio = (actualFinRatio != null && normRatio != null)
      ? Math.min(actualFinRatio, normRatio)
      : (normRatio != null ? normRatio : actualFinRatio);
    const conservativeFinInc = (conservativeFinRatio != null && investment > 0) ? conservativeFinRatio * investment : 0;
    const finIncActualVal = finIncActual != null && !isNaN(finIncActual) ? finIncActual : 0;

    const conservativeOpProfit = op - finIncActualVal + conservativeFinInc;

    const actualOther = pbt - op;
    const normOther = (medians.medianOtherProfitRatio != null && !isNaN(medians.medianOtherProfitRatio) && rev != null && !isNaN(rev))
      ? medians.medianOtherProfitRatio * rev
      : actualOther;
    const conservativeOther = (normOther != null && actualOther != null && !isNaN(actualOther))
      ? Math.min(normOther, actualOther)
      : (normOther != null ? normOther : actualOther);
    // PBT = Op + other; so conservative PBT = conservative Op + conservative other (not "- actual + conservative" which wrongly collapses to Op when actual other === conservative other)
    const conservativePbt = conservativeOpProfit + (conservativeOther != null && !isNaN(conservativeOther) ? conservativeOther : 0);

    const actualTax = (pbt != null && !isNaN(pbt) && pbt !== 0 && actualNet != null && !isNaN(actualNet))
      ? (pbt - actualNet) / pbt
      : null;
    const normTax = medians.medianTaxRate != null && !isNaN(medians.medianTaxRate) ? medians.medianTaxRate : null;
    const conservativeTax = (actualTax != null && normTax != null)
      ? Math.max(actualTax, normTax)
      : (normTax != null ? normTax : actualTax);
    if (conservativeTax == null || isNaN(conservativeTax)) return null;
    return conservativePbt * (1 - conservativeTax);
  }

  /**
   * EBITDA = Profit Before Tax + Interest expense (add-back) + Depreciation expense.
   * Interest expense is stored as negative; add-back is -Interest Expense.
   * Returns { actual, normalized, conservative } in millions VND, or nulls where not computable.
   */
  function computeEBITDAForRecord(r, medians, normalizedNet, conservativeNet) {
    const pbt = r["Profit Before Tax"];
    const interestExpense = r["Interest Expense"];
    const dep = (r["Depreciation Expense"] != null && !isNaN(r["Depreciation Expense"])) ? Number(r["Depreciation Expense"]) : 0;
    const interestAddBack = (interestExpense != null && !isNaN(interestExpense)) ? -Number(interestExpense) : 0;

    const actual = (pbt != null && !isNaN(pbt)) ? pbt + interestAddBack + dep : null;

    let normalized = null;
    if (normalizedNet != null && !isNaN(normalizedNet) && medians.medianTaxRate != null && !isNaN(medians.medianTaxRate) && medians.medianTaxRate < 1) {
      const normPBT = normalizedNet / (1 - medians.medianTaxRate);
      normalized = normPBT + interestAddBack + dep;
    }

    let conservative = null;
    if (conservativeNet != null && !isNaN(conservativeNet)) {
      const actualNet = r["Net Income"];
      const actualTax = (pbt != null && !isNaN(pbt) && pbt !== 0 && actualNet != null && !isNaN(actualNet))
        ? (pbt - actualNet) / pbt
        : null;
      const normTax = medians.medianTaxRate != null && !isNaN(medians.medianTaxRate) ? medians.medianTaxRate : null;
      const conservativeTax = (actualTax != null && normTax != null)
        ? Math.max(actualTax, normTax)
        : (normTax != null ? normTax : actualTax);
      if (conservativeTax != null && !isNaN(conservativeTax) && conservativeTax < 1) {
        const consPBT = conservativeNet / (1 - conservativeTax);
        conservative = consPBT + interestAddBack + dep;
      }
    }

    return { actual, normalized, conservative };
  }

  /**
   * Enrich records with "Net Income (normalized)" and "Net Income (conservative)" using 10-year median ratios.
   * Also adds EBITDA (actual / normalized / conservative) and their T4Q.
   */
  function enrichRecordsWithNormalizedEarnings(records) {
    if (!records || records.length === 0) return records;
    const medians = computeNormalizedEarningsMedians(records);
    let out = records.map((r) => {
      const normalized = computeNormalizedNetProfitForRecord(r, medians);
      const conservative = computeConservativeNetProfitForRecord(r, medians);
      const ebitda = computeEBITDAForRecord(r, medians, normalized, conservative);
      return {
        ...r,
        "Net Income (normalized)": normalized,
        "Net Income (conservative)": conservative,
        "EBITDA": ebitda.actual,
        "EBITDA (normalized)": ebitda.normalized,
        "EBITDA (conservative)": ebitda.conservative
      };
    });
    out = addNormalizedT4Q(out);
    out = addConservativeT4Q(out);
    out = addEBITDAT4Q(out);
    return out;
  }

  /** Return the 4 quarter period strings ending at (year, q), e.g. 2024,2 -> ['2023-Q3','2023-Q4','2024-Q1','2024-Q2']. */
  function trailingFourQuarterPeriods(year, q) {
    const out = [];
    let y = year, qq = q;
    for (let i = 0; i < 4; i++) {
      out.unshift(quarterKey(y, qq));
      const prev = getPreviousQuarter(y, qq);
      y = prev.year;
      qq = prev.q;
    }
    return out;
  }

  /** Add "Net Income (normalized) T4Q" to each quarterly record that has 4 consecutive quarters of normalized data. */
  function addNormalizedT4Q(records) {
    if (!records || records.length === 0) return records;
    const byPeriod = {};
    records.forEach((r) => {
      const p = r.Period;
      if (p) byPeriod[p] = r;
    });
    return records.map((r) => {
      const period = r.Period;
      if (!period || period.indexOf("-Q") === -1) return r;
      const { year, q } = parsePeriodToYearQ(period);
      if (!q) return r;
      const t4qPeriods = trailingFourQuarterPeriods(year, q);
      if (!t4qPeriods.every((p) => byPeriod[p])) return r;
      const sum = t4qPeriods.reduce((acc, p) => {
        const v = byPeriod[p]["Net Income (normalized)"];
        return acc + (typeof v === "number" && !isNaN(v) ? v : 0);
      }, 0);
      return { ...r, "Net Income (normalized) T4Q": sum };
    });
  }

  /** Add "Net Income (conservative) T4Q" to each quarterly record (trailing 4 quarters). */
  function addConservativeT4Q(records) {
    if (!records || records.length === 0) return records;
    const byPeriod = {};
    records.forEach((r) => {
      const p = r.Period;
      if (p) byPeriod[p] = r;
    });
    return records.map((r) => {
      const period = r.Period;
      if (!period || period.indexOf("-Q") === -1) return r;
      const { year, q } = parsePeriodToYearQ(period);
      if (!q) return r;
      const t4qPeriods = trailingFourQuarterPeriods(year, q);
      if (!t4qPeriods.every((p) => byPeriod[p])) return r;
      const sum = t4qPeriods.reduce((acc, p) => {
        const v = byPeriod[p]["Net Income (conservative)"];
        return acc + (typeof v === "number" && !isNaN(v) ? v : 0);
      }, 0);
      return { ...r, "Net Income (conservative) T4Q": sum };
    });
  }

  /** Add "EBITDA T4Q", "EBITDA (normalized) T4Q", "EBITDA (conservative) T4Q" to each quarterly record. */
  function addEBITDAT4Q(records) {
    if (!records || records.length === 0) return records;
    const byPeriod = {};
    records.forEach((r) => {
      const p = r.Period;
      if (p) byPeriod[p] = r;
    });
    const keys = ["EBITDA", "EBITDA (normalized)", "EBITDA (conservative)"];
    const t4qKeys = ["EBITDA T4Q", "EBITDA (normalized) T4Q", "EBITDA (conservative) T4Q"];
    return records.map((r) => {
      const period = r.Period;
      if (!period || period.indexOf("-Q") === -1) return r;
      const { year, q } = parsePeriodToYearQ(period);
      if (!q) return r;
      const t4qPeriods = trailingFourQuarterPeriods(year, q);
      if (!t4qPeriods.every((p) => byPeriod[p])) return r;
      const add = {};
      keys.forEach((key, i) => {
        const sum = t4qPeriods.reduce((acc, p) => {
          const v = byPeriod[p][key];
          return acc + (typeof v === "number" && !isNaN(v) ? v : 0);
        }, 0);
        add[t4qKeys[i]] = sum;
      });
      return { ...r, ...add };
    });
  }

  function getEarningsKey() {
    if (currentEarningsMode === "normalized") return "Net Income (normalized)";
    if (currentEarningsMode === "conservative") return "Net Income (conservative)";
    return "Net Income";
  }

  function getEarningsT4QKey() {
    if (currentEarningsMode === "normalized") return "Net Income (normalized) T4Q";
    if (currentEarningsMode === "conservative") return "Net Income (conservative) T4Q";
    return "Net Income T4Q";
  }

  function getEBITDAKey() {
    if (currentEarningsMode === "normalized") return "EBITDA (normalized)";
    if (currentEarningsMode === "conservative") return "EBITDA (conservative)";
    return "EBITDA";
  }

  function getEBITDAT4QKey() {
    if (currentEarningsMode === "normalized") return "EBITDA (normalized) T4Q";
    if (currentEarningsMode === "conservative") return "EBITDA (conservative) T4Q";
    return "EBITDA T4Q";
  }

  /**
   * Return records with ROE, ROIC, Net Profit Margin recomputed from the given earnings key.
   * Used for quality section when earnings mode is normalized.
   */
  function getRecordsWithEarningsBasedRatios(records, earningsKey) {
    if (!records || records.length === 0) return records;
    if (earningsKey === "Net Income") return records; // use as-is
    return records.map((r) => {
      const ni = r[earningsKey];
      const eq = r.Equity;
      const rev = r.Revenue;
      const invCap = investedCapitalMillions(r);
      let ROE = null, ROIC = null, npm = null;
      if (eq != null && !isNaN(eq) && eq !== 0 && ni != null && !isNaN(ni)) ROE = ni / eq;
      if (invCap != null && invCap > 0 && ni != null && !isNaN(ni)) ROIC = ni / invCap;
      if (rev != null && !isNaN(rev) && rev !== 0 && ni != null && !isNaN(ni)) npm = ni / rev;
      return { ...r, ROE, ROIC, "Net Profit Margin": npm };
    });
  }

  function calculateCAGR(records, key, years) {
    // Get annual values for the metric
    const annual = records
      .filter((r) => String(r.Period || "").includes("-FY") && r[key] != null && !isNaN(r[key]))
      .sort((a, b) => String(a.Period || "").localeCompare(String(b.Period || "")));
    
    if (annual.length < 2) return null;
    
    // Get the latest year
    const latestRecord = annual[annual.length - 1];
    const latestMatch = String(latestRecord.Period).match(/^(\d{4})/);
    if (!latestMatch) return null;
    const latestYear = parseInt(latestMatch[1], 10);
    
    // Find the record from N years ago
    const targetYear = latestYear - years;
    const startRecord = annual.find((r) => {
      const match = String(r.Period).match(/^(\d{4})/);
      return match && parseInt(match[1], 10) === targetYear;
    });
    
    if (!startRecord) return null;
    
    const startValue = startRecord[key];
    const endValue = latestRecord[key];
    
    if (startValue <= 0 || endValue <= 0) return null;
    
    // CAGR = (End/Start)^(1/years) - 1
    return Math.pow(endValue / startValue, 1 / years) - 1;
  }

  /**
   * YoY growth: only when prev > 0 and curr > 0 (no explosions, no loss→profit in magnitude).
   * No ±30% clip: Direction handles sign transitions; raw YoY used for Stability and Resilience.
   * Deduplicates by Period so duplicate FY entries (e.g. from merged sources) don't produce 0% same-year pairs.
   */
  function getYoYGrowths(records, key) {
    let annual = (records || [])
      .filter((r) => String(r.Period || "").includes("-FY"))
      .sort((a, b) => String(a.Period || "").localeCompare(String(b.Period || "")));

    // Deduplicate by Period (keep last per period) so we never compare same year to same year
    const byPeriod = new Map();
    annual.forEach((r) => byPeriod.set(String(r.Period || ""), r));
    annual = Array.from(byPeriod.values()).sort((a, b) => String(a.Period || "").localeCompare(String(b.Period || "")));

    const yoyRates = [];
    for (let i = 1; i < annual.length; i++) {
      const prev = annual[i - 1][key];
      const curr = annual[i][key];
      if (prev == null || curr == null || isNaN(prev) || isNaN(curr)) continue;
      if (prev <= 0 || curr <= 0) continue;
      yoyRates.push((curr - prev) / prev);
    }
    return yoyRates;
  }

  /**
   * Transition scores per Negative value in growth ref.txt:
   * + → + : +1.0, − → + : +0.5, − → − : −0.5, + → − : −1.0
   */
  function getTransitionScore(prev, curr) {
    if (prev == null || curr == null || isNaN(prev) || isNaN(curr)) return null;
    const pPos = prev > 0;
    const cPos = curr > 0;
    if (pPos && cPos) return 1.0;
    if (!pPos && cPos) return 0.5;
    if (!pPos && !cPos) return -0.5;
    return -1.0;
  }

  function calculateMedianYoY(records, key) {
    const yoyRates = getYoYGrowths(records, key);
    if (yoyRates.length === 0) return null;
    return calculateMedian(yoyRates);
  }

  /**
   * Growth Quality Score (0–100).
   * Revenue only: 40% Positive Growth Ratio + 25% Stability + 35% Resilience (no Direction).
   * Net Income: 40% Positive Growth Ratio + 25% Stability + 25% Direction + 10% Resilience.
   * Positive Growth Ratio = % of valid YoY pairs with positive growth.
   * Returns { score, breakdown } for popup display.
   */
  function calculateGrowthQualityScore(records, key) {
    let annual = (records || [])
      .filter((r) => String(r.Period || "").includes("-FY"))
      .sort((a, b) => String(a.Period || "").localeCompare(String(b.Period || "")));
    const byPeriod = new Map();
    annual.forEach((r) => byPeriod.set(String(r.Period || ""), r));
    annual = Array.from(byPeriod.values()).sort((a, b) => String(a.Period || "").localeCompare(String(b.Period || "")));
    if (annual.length === 0) return null;

    const values = annual.map((r) => r[key]).filter((v) => v != null && !isNaN(v));
    if (values.length === 0) return null;

    const yoyRates = getYoYGrowths(records, key);
    const totalValidYoY = yoyRates.length;
    const positiveGrowth = totalValidYoY > 0 ? yoyRates.filter((r) => r > 0).length : 0;
    const positiveGrowthRatio = totalValidYoY > 0 ? positiveGrowth / totalValidYoY : 0.5;

    const isRevenue = key === "Revenue";
    let directionRaw = 0;
    let directionScoreNorm = 1;
    const transitionScores = [];
    if (!isRevenue) {
      for (let i = 1; i < annual.length; i++) {
        const prev = annual[i - 1][key];
        const curr = annual[i][key];
        const ts = getTransitionScore(prev, curr);
        if (ts != null) transitionScores.push(ts);
      }
      directionRaw = transitionScores.length === 0 ? 0 : transitionScores.reduce((a, b) => a + b, 0) / transitionScores.length;
      directionScoreNorm = (directionRaw + 1) / 2;
    }

    let stabilityScore = 0.5;
    let cv = 0;
    let mean = 0;
    let std = 0;
    if (yoyRates.length > 0) {
      mean = yoyRates.reduce((a, b) => a + b, 0) / yoyRates.length;
      const variance = yoyRates.reduce((sum, r) => sum + (r - mean) ** 2, 0) / yoyRates.length;
      std = Math.sqrt(variance);
      cv = Math.abs(mean) < 1e-9 ? (std < 1e-9 ? 0 : 2) : std / Math.abs(mean);
      const CV_MAX = 2;
      stabilityScore = Math.max(0, Math.min(1, 1 - cv / CV_MAX));
    }

    const worstDrawdown = yoyRates.length > 0 ? Math.min(...yoyRates) : 0;
    const downsidePenalty = worstDrawdown < 0 ? Math.min(Math.abs(worstDrawdown) / 0.3, 1) : 0;
    const resilienceScore = 1 - downsidePenalty;

    const resilienceWeight = isRevenue ? 0.35 : 0.1;
    const score = isRevenue
      ? (0.4 * positiveGrowthRatio + 0.25 * stabilityScore + resilienceWeight * resilienceScore) * 100
      : (0.4 * positiveGrowthRatio + 0.25 * stabilityScore + 0.25 * directionScoreNorm + 0.1 * resilienceScore) * 100;
    const finalScore = Math.max(0, Math.min(100, score));

    return {
      score: finalScore,
      breakdown: {
        positiveGrowthRatio: { weight: 0.4, ratio: positiveGrowthRatio, positive: positiveGrowth, total: totalValidYoY },
        stability: { weight: 0.25, cv, stabilityScore, mean, std },
        direction: { weight: 0.25, raw: directionRaw, scoreNorm: directionScoreNorm, transitions: transitionScores.length, skipDirection: isRevenue },
        resilience: { weight: resilienceWeight, worstDrawdown, downsidePenalty, resilienceScore },
      },
    };
  }

  /**
   * Map 0–100 score to 1–5 quality level for 5-dot display.
   * 0–20→1, 21–40→2, 41–60→3, 61–80→4, 81–100→5
   */
  function scoreToQualityLevel(score) {
    if (score == null || isNaN(score)) return 0;
    if (score <= 20) return 1;
    if (score <= 40) return 2;
    if (score <= 60) return 3;
    if (score <= 80) return 4;
    return 5;
  }

  /**
   * Render Growth Quality as 5 colored dots. 1–2=red, 3=yellow, 4–5=green.
   * Ranked = solid circle; non-ranked = hollow circle (CSS circles, equal size).
   */
  function renderGrowthQualityDots(score) {
    if (score == null || isNaN(score)) return "—";
    const level = scoreToQualityLevel(score);
    const colors = ["red", "red", "yellow", "green", "green"];
    const dots = [];
    for (let i = 0; i < 5; i++) {
      const filled = i < level;
      const color = colors[i];
      const cls = `growth-quality-dot growth-quality-dot--${color}${filled ? " growth-quality-dot--filled" : ""}`;
      dots.push(`<span class="${cls}" title="Quality level ${i + 1}" aria-hidden="true"></span>`);
    }
    return `<span class="growth-quality-dots">${dots.join("")}</span>`;
  }

  /**
   * Generate sparkline visualization.
   * @param {Array} dataPoints - Array of {period, value} objects
   * @param {string} format - 'percent' (default) or 'ratio' for formatting tooltip values
   */
  function generateSparkline(dataPoints, format = 'percent') {
    if (!dataPoints || dataPoints.length === 0) return "—";
    
    // 0-aligned: positive up, negative down; equal magnitude = equal height
    const magnitudes = dataPoints.map((d) => Math.abs(d.value));
    const maxMagnitude = Math.max(...magnitudes, 0.0001);
    
    const cells = dataPoints
      .map((d) => {
        const mag = Math.abs(d.value);
        const heightPct = mag === 0 ? 0 : (mag / maxMagnitude) * 100;
        const isNeg = d.value < 0;
        
        const year = String(d.period).replace("-FY", "");
        const formattedValue = format === 'ratio' 
          ? d.value.toFixed(2) 
          : (d.value * 100).toFixed(1) + "%";
        const tooltip = `${year}: ${formattedValue}`;
        
        const barClass = isNeg ? "sparkline-bar sparkline-bar--down" : "sparkline-bar sparkline-bar--up";
        const heightHalf = heightPct / 2;
        return `<div class="sparkline-cell" data-tooltip="${tooltip.replace(/"/g, "&quot;")}">
          <div class="sparkline-bar-wrap">
            <div class="${barClass}" style="height: ${heightHalf}%"></div>
          </div>
        </div>`;
      })
      .join("");
    return `<div class="sparkline-chart">${cells}</div>`;
  }

  function initSparklineTooltips() {
    let tooltipEl = null;
    
    document.querySelectorAll(".sparkline-cell").forEach((cell) => {
      cell.addEventListener("mouseenter", (e) => {
        const text = e.currentTarget.getAttribute("data-tooltip");
        if (!text) return;
        
        tooltipEl = document.createElement("div");
        tooltipEl.className = "sparkline-tooltip";
        tooltipEl.textContent = text;
        document.body.appendChild(tooltipEl);
        
        const updatePosition = () => {
          if (!tooltipEl || !tooltipEl.parentNode) return;
          const rect = cell.getBoundingClientRect();
          const x = rect.left + rect.width / 2 - tooltipEl.offsetWidth / 2;
          const y = rect.top - tooltipEl.offsetHeight - 6;
          tooltipEl.style.left = Math.max(4, x) + "px";
          tooltipEl.style.top = Math.max(4, y) + "px";
        };

        requestAnimationFrame(() => requestAnimationFrame(updatePosition));
      });
      
      cell.addEventListener("mouseleave", () => {
        if (tooltipEl && tooltipEl.parentNode) {
          tooltipEl.parentNode.removeChild(tooltipEl);
          tooltipEl = null;
        }
      });
      
      cell.addEventListener("mousemove", () => {
        if (tooltipEl && tooltipEl.parentNode) {
          const rect = cell.getBoundingClientRect();
          const x = rect.left + rect.width / 2 - tooltipEl.offsetWidth / 2;
          const y = rect.top - tooltipEl.offsetHeight - 6;
          tooltipEl.style.left = Math.max(4, x) + "px";
          tooltipEl.style.top = Math.max(4, y) + "px";
        }
      });
    });
  }

  /**
   * Calculate D/E (Debt/Equity) as interest-bearing debt over equity.
   * D/E = (Interest Bearing Debt Short Term + Interest Bearing Debt Long Term) / Equity
   */
  function calculateDERatios(records) {
    return records
      .filter((r) => r.Equity != null && !isNaN(r.Equity) && r.Equity !== 0)
      .map((r) => {
        const ibdShort = r["Interest Bearing Debt Short Term"] ?? 0;
        const ibdLong = r["Interest Bearing Debt Long Term"] ?? 0;
        const totalDebt = (typeof ibdShort === "number" ? ibdShort : 0) + (typeof ibdLong === "number" ? ibdLong : 0);
        return {
          Period: r.Period,
          "D/E": totalDebt / r.Equity,
        };
      });
  }

  function populateQualitySection(records) {
    const earningsKey = getEarningsKey();
    const qualityRecords = getRecordsWithEarningsBasedRatios(records, earningsKey);
    const roicData = getLatestValueWithPeriod(qualityRecords, "ROIC");
    const roeData = getLatestValueWithPeriod(qualityRecords, "ROE");
    const npmData = getLatestValueWithPeriod(qualityRecords, "Net Profit Margin");

    document.getElementById("quality-roic-value").textContent = formatPercent(roicData.value);
    document.getElementById("quality-roic-period").textContent = roicData.period ? `(${roicData.period})` : "";

    document.getElementById("quality-roe-value").textContent = formatPercent(roeData.value);
    document.getElementById("quality-roe-period").textContent = roeData.period ? `(${roeData.period})` : "";

    document.getElementById("quality-npm-value").textContent = formatPercent(npmData.value);
    document.getElementById("quality-npm-period").textContent = npmData.period ? `(${npmData.period})` : "";

    // Calculate D/E ratio
    const deRecords = calculateDERatios(records);
    const deData = getLatestValueWithPeriod(deRecords, "D/E");
    document.getElementById("quality-de-value").textContent = deData.value != null ? deData.value.toFixed(2) : "—";
    document.getElementById("quality-de-period").textContent = deData.period ? `(${deData.period})` : "";

    // Calculate medians from annual data within the filtered timeframe
    const roicValues = getAnnualValues(qualityRecords, "ROIC");
    const roeValues = getAnnualValues(qualityRecords, "ROE");
    const npmValues = getAnnualValues(qualityRecords, "Net Profit Margin");
    const deValues = getAnnualValues(deRecords, "D/E");

    const roicMedian = calculateMedian(roicValues);
    const roeMedian = calculateMedian(roeValues);
    const npmMedian = calculateMedian(npmValues);
    const deMedian = calculateMedian(deValues);

    const medLabel = `${currentTimeframe}Y med:`;
    document.getElementById("quality-roic-median").textContent = `${medLabel} ${formatPercent(roicMedian)}`;
    document.getElementById("quality-roe-median").textContent = `${medLabel} ${formatPercent(roeMedian)}`;
    document.getElementById("quality-npm-median").textContent = `${medLabel} ${formatPercent(npmMedian)}`;
    document.getElementById("quality-de-median").textContent = `${medLabel} ${deMedian != null ? deMedian.toFixed(2) : "—"}`;
    
    // Generate sparklines: FY + latest quarter if more recent than latest FY
    const roicDataPoints = getSparklineDataPoints(qualityRecords, "ROIC");
    const roeDataPoints = getSparklineDataPoints(qualityRecords, "ROE");
    const npmDataPoints = getSparklineDataPoints(qualityRecords, "Net Profit Margin");
    const deDataPoints = getSparklineDataPoints(deRecords, "D/E");
    
    document.getElementById("quality-roic-sparkline").innerHTML = generateSparkline(roicDataPoints, 'percent');
    document.getElementById("quality-roe-sparkline").innerHTML = generateSparkline(roeDataPoints, 'percent');
    document.getElementById("quality-npm-sparkline").innerHTML = generateSparkline(npmDataPoints, 'percent');
    document.getElementById("quality-de-sparkline").innerHTML = generateSparkline(deDataPoints, 'ratio');

    initSparklineTooltips();
  }

  function populateGrowthSection(records) {
    const filtered5 = filterByTimeframe(currentRecords, 5);
    const filtered10 = filterByTimeframe(currentRecords, 10);

    const qualityHelp = "Growth Quality (0–100): Positive Growth Ratio (40%) + Stability (25%) + Direction (25%) + Resilience (10%). Click for breakdown.";

    function setGrowthRow(metric, median5, median10, quality5, quality10, cagr5, cagr10) {
      document.getElementById(`growth-${metric}-median-yoy-5y`).textContent = formatPercent(median5);
      document.getElementById(`growth-${metric}-median-yoy-10y`).textContent = formatPercent(median10);

      const key = metric === "revenue" ? "Revenue" : getEarningsKey();
      const el5 = document.getElementById(`growth-${metric}-quality-5y`);
      const el10 = document.getElementById(`growth-${metric}-quality-10y`);
      el5.innerHTML = quality5 ? renderGrowthQualityDots(quality5.score) : "—";
      el10.innerHTML = quality10 ? renderGrowthQualityDots(quality10.score) : "—";
      el5.title = quality5 ? `Growth Quality (5Y): ${Math.round(quality5.score)}/100. ${qualityHelp}` : qualityHelp;
      el10.title = quality10 ? `Growth Quality (10Y): ${Math.round(quality10.score)}/100. ${qualityHelp}` : qualityHelp;
      el5.dataset.breakdown = quality5 ? JSON.stringify(quality5.breakdown) : "";
      el10.dataset.breakdown = quality10 ? JSON.stringify(quality10.breakdown) : "";
      el5.dataset.score = quality5 ? String(Math.round(quality5.score)) : "";
      el10.dataset.score = quality10 ? String(Math.round(quality10.score)) : "";
      el5.dataset.metric = key;
      el10.dataset.metric = key;
      el5.dataset.years = "5";
      el10.dataset.years = "10";

      document.getElementById(`growth-${metric}-cagr-5y`).textContent = formatPercent(cagr5);
      document.getElementById(`growth-${metric}-cagr-10y`).textContent = formatPercent(cagr10);
    }

    const revenueMedian5 = calculateMedianYoY(filtered5, "Revenue");
    const revenueMedian10 = calculateMedianYoY(filtered10, "Revenue");
    const revenueQuality5 = calculateGrowthQualityScore(filtered5, "Revenue");
    const revenueQuality10 = calculateGrowthQualityScore(filtered10, "Revenue");
    const revenueCAGR5 = calculateCAGR(currentRecords, "Revenue", 5);
    const revenueCAGR10 = calculateCAGR(currentRecords, "Revenue", 10);

    const incomeKey = getEarningsKey();
    const incomeMedian5 = calculateMedianYoY(filtered5, incomeKey);
    const incomeMedian10 = calculateMedianYoY(filtered10, incomeKey);
    const incomeQuality5 = calculateGrowthQualityScore(filtered5, incomeKey);
    const incomeQuality10 = calculateGrowthQualityScore(filtered10, incomeKey);
    const incomeCAGR5 = calculateCAGR(currentRecords, incomeKey, 5);
    const incomeCAGR10 = calculateCAGR(currentRecords, incomeKey, 10);

    setGrowthRow("revenue", revenueMedian5, revenueMedian10, revenueQuality5, revenueQuality10, revenueCAGR5, revenueCAGR10);
    setGrowthRow("income", incomeMedian5, incomeMedian10, incomeQuality5, incomeQuality10, incomeCAGR5, incomeCAGR10);

    requestAnimationFrame(() => {
      syncGrowthChartHeight();
      renderGrowthChart(records);
    });
  }

  function filterByTimeframe(records, years) {
    if (!years || years <= 0) return records;
    
    // Get all periods sorted descending
    const sorted = [...records]
      .filter((r) => r.Period != null)
      .sort((a, b) => String(b.Period || "").localeCompare(String(a.Period || "")));
    
    if (sorted.length === 0) return records;
    
    // Get the latest period's year
    const latestPeriod = sorted[0].Period;
    const match = String(latestPeriod).match(/^(\d{4})/);
    if (!match) return records;
    
    const latestYear = parseInt(match[1], 10);
    const cutoffYear = latestYear - years;
    
    // Filter records to only include periods from cutoffYear onwards
    return records.filter((r) => {
      const periodMatch = String(r.Period || "").match(/^(\d{4})/);
      if (!periodMatch) return false;
      const year = parseInt(periodMatch[1], 10);
      return year > cutoffYear;
    });
  }

  function formatNumber(val) {
    if (val == null || isNaN(val)) return "—";
    if (Math.abs(val) >= 1e12) return (val / 1e12).toFixed(1) + "T";
    if (Math.abs(val) >= 1e9) return (val / 1e9).toFixed(1) + "B";
    if (Math.abs(val) >= 1e6) return (val / 1e6).toFixed(1) + "M";
    if (Math.abs(val) >= 1e3) return (val / 1e3).toFixed(1) + "K";
    return val.toFixed(0);
  }

  /** Format financial figures (Revenue, Net Income) — data is already in millions; unit is dynamic (T/B/M/K).
   * - >= 1000 B → xx.y T (1 decimal)
   * - >= 100 B → no decimal, with thousand separators (e.g. 1,000 B)
   * - < 100 in current unit → 1 decimal
   */
  function formatFinancial(val) {
    if (val == null || isNaN(val)) return "—";
    const n = Number(val);
    const abs = Math.abs(n);
    const sign = n < 0 ? "-" : "";
    const fmt = (x, decimals) => {
      if (decimals === 0) return Math.round(x).toLocaleString("en-US");
      const s = x.toFixed(decimals);
      const [int, dec] = s.split(".");
      return parseInt(int, 10).toLocaleString("en-US") + (dec ? "." + dec : "");
    };
    if (abs >= 1e6) {
      const tVal = n / 1e6;
      return sign + (Math.abs(tVal) >= 100 ? fmt(tVal, 0) : tVal.toFixed(1)) + " T";
    }
    if (abs >= 1000) {
      const bVal = n / 1000;
      return sign + (Math.abs(bVal) >= 100 ? fmt(bVal, 0) : bVal.toFixed(1)) + " B";
    }
    if (abs >= 1) {
      return sign + (abs >= 100 ? fmt(n, 0) : n.toFixed(1)) + " M";
    }
    if (abs >= 0.001) return sign + (n * 1000).toFixed(1) + " K";
    return sign + n.toFixed(2) + " M";
  }

  function syncGrowthChartHeight() {
    const metricsEl = document.querySelector(".growth-metrics");
    const chartContainer = document.querySelector(".growth-chart-container");
    if (!metricsEl || !chartContainer) return;
    const h = metricsEl.offsetHeight;
    if (h > 0) {
      chartContainer.style.height = h + "px";
      const chartEl = document.getElementById("growth-chart");
      if (chartEl && chartEl.data && window.Plotly) {
        window.Plotly.Plots.resize(chartEl);
      }
    }
  }

  function renderGrowthChart(records) {
    const chartEl = document.getElementById("growth-chart");
    if (!chartEl || !window.Plotly) return;

    const showRevenue = document.getElementById("toggle-revenue")?.checked ?? true;
    const showIncome = document.getElementById("toggle-net-income")?.checked ?? true;
    const showIncomeNormalized = document.getElementById("toggle-net-income-normalized")?.checked ?? false;
    const showIncomeConservative = document.getElementById("toggle-net-income-conservative")?.checked ?? false;

    const filtered = filterByTimeframe(records, currentTimeframe);
    let annual = filtered
      .filter((r) => String(r.Period || "").includes("-FY"))
      .sort((a, b) => String(a.Period || "").localeCompare(String(b.Period || "")));

    // Include latest quarter (T4Q) if more recent than latest FY
    const latestFY = annual.length > 0 ? annual[annual.length - 1] : null;
    const latestFYPeriod = latestFY?.Period || "";
    const sortedAll = [...records].filter((r) => r.Period != null).sort((a, b) => {
      const pa = String(a.Period);
      const pb = String(b.Period);
      const yearA = parseInt(pa.match(/^(\d{4})/)?.[1] || "0", 10);
      const yearB = parseInt(pb.match(/^(\d{4})/)?.[1] || "0", 10);
      if (yearA !== yearB) return yearA - yearB;
      return periodSortRank(pa) - periodSortRank(pb);
    });
    const latestRecord = sortedAll[sortedAll.length - 1];
    const latestPeriod = String(latestRecord?.Period || "");
    const isQuarter = /-Q[1-4]$/i.test(latestPeriod);
    if (isQuarter && latestRecord && latestFYPeriod && String(latestPeriod).localeCompare(latestFYPeriod) > 0) {
      annual = [...annual, latestRecord];
    }

    const data = [];

    if (showRevenue && annual.some((r) => r.Revenue != null)) {
      const values = annual.map((r) => r.Revenue);
      const baseRecord = annual.find((r) => r.Revenue != null && r.Revenue > 0 && !isNaN(r.Revenue));
      const base = baseRecord?.Revenue;
      const canIndex = base != null;
      const indexed = canIndex ? values.map((v) => (v != null && !isNaN(v) ? (v / base) * 100 : null)) : values;
      data.push({
        x: annual.map((r) => r.Period),
        y: indexed,
        customdata: values.map((v) => (v != null ? formatFinancial(v) : "—")),
        type: "scatter",
        mode: "lines+markers",
        name: "Revenue",
        line: { color: "#38bdf8", width: 2 },
        hovertemplate: "%{x}<br>Revenue: %{customdata}<extra></extra>",
      });
    }

    if (showIncome && annual.some((r) => r["Net Income"] != null)) {
      const values = annual.map((r) => r["Net Income"]);
      const baseRecord = annual.find((r) => r["Net Income"] != null && r["Net Income"] > 0 && !isNaN(r["Net Income"]));
      const base = baseRecord?.["Net Income"];
      const canIndex = base != null;
      const indexed = canIndex ? values.map((v) => (v != null && !isNaN(v) ? (v / base) * 100 : null)) : values;
      data.push({
        x: annual.map((r) => r.Period),
        y: indexed,
        customdata: values.map((v) => (v != null ? formatFinancial(v) : "—")),
        type: "scatter",
        mode: "lines+markers",
        name: "Net Income",
        line: { color: "#166534", width: 2, dash: "dash" },
        hovertemplate: "%{x}<br>Net Income: %{customdata}<extra></extra>",
      });
    }

    if (showIncomeNormalized && annual.some((r) => r["Net Income (normalized)"] != null)) {
      const values = annual.map((r) => r["Net Income (normalized)"]);
      const baseRecord = annual.find((r) => r["Net Income (normalized)"] != null && r["Net Income (normalized)"] > 0 && !isNaN(r["Net Income (normalized)"]));
      const base = baseRecord?.["Net Income (normalized)"];
      const canIndex = base != null;
      const indexed = canIndex ? values.map((v) => (v != null && !isNaN(v) ? (v / base) * 100 : null)) : values;
      data.push({
        x: annual.map((r) => r.Period),
        y: indexed,
        customdata: values.map((v) => (v != null ? formatFinancial(v) : "—")),
        type: "scatter",
        mode: "lines+markers",
        name: "Net Income (normalized)",
        line: { color: "#16a34a", width: 2, dash: "dash" },
        hovertemplate: "%{x}<br>Net Income (normalized): %{customdata}<extra></extra>",
      });
    }

    if (showIncomeConservative && annual.some((r) => r["Net Income (conservative)"] != null)) {
      const values = annual.map((r) => r["Net Income (conservative)"]);
      const baseRecord = annual.find((r) => r["Net Income (conservative)"] != null && r["Net Income (conservative)"] > 0 && !isNaN(r["Net Income (conservative)"]));
      const base = baseRecord?.["Net Income (conservative)"];
      const canIndex = base != null;
      const indexed = canIndex ? values.map((v) => (v != null && !isNaN(v) ? (v / base) * 100 : null)) : values;
      data.push({
        x: annual.map((r) => r.Period),
        y: indexed,
        customdata: values.map((v) => (v != null ? formatFinancial(v) : "—")),
        type: "scatter",
        mode: "lines+markers",
        name: "Net Income (conservative)",
        line: { color: "#86efac", width: 2, dash: "dash" },
        hovertemplate: "%{x}<br>Net Income (conservative): %{customdata}<extra></extra>",
      });
    }

    const layout = {
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: { color: "#e5e7eb", size: 11 },
      margin: { t: 20, r: 20, b: 40, l: 60 },
      xaxis: {
        title: { text: "" },
        automargin: true,
        showgrid: true,
        gridwidth: 0.5,
        gridcolor: "rgba(148, 163, 184, 0.15)",
      },
      yaxis: {
        title: { text: "" },
        showgrid: true,
        gridwidth: 0.5,
        gridcolor: "rgba(148, 163, 184, 0.15)",
        tickformat: "d",
      },
      showlegend: false,
    };

    window.Plotly.newPlot(chartEl, data, layout, { responsive: true });
  }

  /**
   * Compute current market cap in VND from latest market data and shares outstanding.
   * Price in market data is in thousands (e.g. 65.4 = 65,400 VND).
   */
  function getCurrentMarketCapVND(marketData, sharesOutstanding) {
    if (!marketData || marketData.length === 0 || sharesOutstanding == null || isNaN(sharesOutstanding)) return null;
    const latest = marketData[marketData.length - 1];
    const close = latest?.close != null ? Number(latest.close) : null;
    if (close == null || isNaN(close)) return null;
    return close * 1000 * sharesOutstanding;
  }

  // --- Quarter helpers for valuation trend (quarterly by default; FY → Q4 T4Q) ---
  function quarterKey(year, q) {
    return year + "-Q" + q;
  }

  /** Parse Period (e.g. "2024-FY", "2025-Q2") to { year, q }. FY → q=4. */
  function parsePeriodToYearQ(period) {
    const s = String(period || "");
    const year = parseInt(s.match(/^(\d{4})/)?.[1] || "0", 10);
    if (s.endsWith("-FY")) return { year, q: 4 };
    const m = s.match(/-Q([1-4])$/);
    return { year, q: m ? parseInt(m[1], 10) : 0 };
  }

  /** Previous quarter: (y,q) → (y,q-1) or (y-1,4). */
  function getPreviousQuarter(year, q) {
    if (q >= 2) return { year, q: q - 1 };
    return { year: year - 1, q: 4 };
  }

  /** Parse market date string to { year, q }. */
  function parseDateToYearQ(dateStr) {
    const d = typeof dateStr === "string" ? new Date(dateStr.replace(" 00:00:00", "").trim()) : new Date(dateStr);
    if (isNaN(d)) return null;
    const year = d.getFullYear();
    const month = d.getMonth() + 1;
    const q = month <= 3 ? 1 : month <= 6 ? 2 : month <= 9 ? 3 : 4;
    return { year, q };
  }

  /**
   * Invested capital (millions) = Equity + Liability - Cash And Equivalent - Cash Investment.
   * Used to compute T4Q ROIC = Net Income T4Q / Invested Capital.
   */
  function investedCapitalMillions(r) {
    const eq = r.Equity;
    const liab = r.Liability;
    const cash = r["Cash And Equivalent"];
    const cashInv = r["Cash Investment"];
    if (eq == null || liab == null || isNaN(eq) || isNaN(liab)) return null;
    let cap = eq + liab;
    if (cash != null && !isNaN(cash)) cap -= cash;
    if (cashInv != null && !isNaN(cashInv)) cap -= cashInv;
    return cap > 0 ? cap : null;
  }

  /** Net debt (millions VND) from a single record: IBD short + IBD long - Cash. */
  function getNetDebtFromRecord(r) {
    if (!r) return 0;
    const ibdShort = (r["Interest Bearing Debt Short Term"] != null && !isNaN(r["Interest Bearing Debt Short Term"]))
      ? Number(r["Interest Bearing Debt Short Term"]) : 0;
    const ibdLong = (r["Interest Bearing Debt Long Term"] != null && !isNaN(r["Interest Bearing Debt Long Term"]))
      ? Number(r["Interest Bearing Debt Long Term"]) : 0;
    const cash = (r["Cash And Equivalent"] != null && !isNaN(r["Cash And Equivalent"]))
      ? Number(r["Cash And Equivalent"]) : 0;
    return ibdShort + ibdLong - cash;
  }

  /**
   * Build map quarterKey → { earningsMillions, equityMillions, roic, roicT4q, ebitdaMillions?, netDebtMillions? }.
   * Uses earningsKey and earningsT4QKey for Actual vs Normalized mode. Optional ebitdaKey/ebitdaT4QKey for EV/EBITDA.
   */
  function buildFinancialMapByQuarter(records, earningsKey, earningsT4QKey, ebitdaKey, ebitdaT4QKey) {
    const niKey = earningsKey || "Net Income";
    const t4qKey = earningsT4QKey || "Net Income T4Q";
    const ebitdaK = ebitdaKey ?? getEBITDAKey();
    const ebitdaT4qK = ebitdaT4QKey ?? getEBITDAT4QKey();
    const map = {};
    const list = records || [];
    list.forEach((r) => {
      const period = r.Period;
      if (!period || !String(period).endsWith("-FY")) return;
      const year = String(period).match(/^(\d{4})/)?.[1];
      if (!year) return;
      const key = year + "-Q4";
      const ni = r[niKey];
      const eq = r.Equity;
      const roic = r.ROIC;
      const ebitda = r[ebitdaK];
      const netDebt = getNetDebtFromRecord(r);
      if (ni != null && !isNaN(ni)) map[key] = { ...(map[key] || {}), earningsMillions: ni };
      if (eq != null && !isNaN(eq)) map[key] = { ...(map[key] || {}), equityMillions: eq };
      if (roic != null && !isNaN(roic)) map[key] = { ...(map[key] || {}), roic, roicT4q: roic };
      if (ebitda != null && !isNaN(ebitda)) map[key] = { ...(map[key] || {}), ebitdaMillions: ebitda };
      map[key] = { ...(map[key] || {}), netDebtMillions: netDebt };
    });
    list.forEach((r) => {
      const period = r.Period;
      if (!period) return;
      const { year, q } = parsePeriodToYearQ(period);
      if (!q) return;
      const key = quarterKey(year, q);
      if (key.endsWith("-Q4") && map[key]) return;
      if (String(period).endsWith("-FY")) return;
      const t4q = r[t4qKey];
      const eq = r.Equity;
      const roic = r.ROIC;
      const invCap = investedCapitalMillions(r);
      const ebitdaT4q = r[ebitdaT4qK];
      const netDebt = getNetDebtFromRecord(r);
      let roicT4q = null;
      if (t4q != null && !isNaN(t4q) && invCap != null && invCap > 0) roicT4q = t4q / invCap;
      if (t4q != null && !isNaN(t4q)) map[key] = { ...(map[key] || {}), earningsMillions: t4q };
      if (eq != null && !isNaN(eq)) map[key] = { ...(map[key] || {}), equityMillions: eq };
      if (roic != null && !isNaN(roic)) map[key] = { ...(map[key] || {}), roic };
      if (roicT4q != null && !isNaN(roicT4q)) map[key] = { ...(map[key] || {}), roicT4q };
      if (ebitdaT4q != null && !isNaN(ebitdaT4q)) map[key] = { ...(map[key] || {}), ebitdaMillions: ebitdaT4q };
      map[key] = { ...(map[key] || {}), netDebtMillions: netDebt };
    });
    return map;
  }

  /** True if we have any quarterly financial periods (e.g. 2024-Q1) with earnings or equity. */
  function hasQuarterlyFinancialData(records) {
    return (records || []).some((r) => {
      const p = String(r.Period || "");
      if (!/^\d{4}-Q[1-4]$/.test(p)) return false;
      const hasEarnings = r["Net Income T4Q"] != null && !isNaN(r["Net Income T4Q"]);
      const hasEquity = r.Equity != null && !isNaN(r.Equity);
      return hasEarnings || hasEquity;
    });
  }

  /**
   * FY financials by year: key = "2024" -> { earningsMillions, equityMillions, roic, ebitdaMillions?, netDebtMillions? } from Period "2024-FY".
   */
  function buildFinancialMapByYear(records, earningsKey, ebitdaKey) {
    const niKey = earningsKey || "Net Income";
    const ebitdaK = ebitdaKey ?? getEBITDAKey();
    const map = {};
    (records || []).forEach((r) => {
      const period = r.Period;
      if (!period || !String(period).endsWith("-FY")) return;
      const year = String(period).match(/^(\d{4})/)?.[1];
      if (!year) return;
      const ni = r[niKey];
      const eq = r.Equity;
      const roic = r.ROIC;
      const ebitda = r[ebitdaK];
      const netDebt = getNetDebtFromRecord(r);
      if (ni != null && !isNaN(ni)) map[year] = { ...(map[year] || {}), earningsMillions: ni };
      if (eq != null && !isNaN(eq)) map[year] = { ...(map[year] || {}), equityMillions: eq };
      if (roic != null && !isNaN(roic)) map[year] = { ...(map[year] || {}), roic };
      if (ebitda != null && !isNaN(ebitda)) map[year] = { ...(map[year] || {}), ebitdaMillions: ebitda };
      map[year] = { ...(map[year] || {}), netDebtMillions: netDebt };
    });
    return map;
  }

  /**
   * Group market data by calendar year; return array of { period, high, low, avg, closes }.
   * period = "2024", "2025", etc. Sorted chronologically.
   */
  function getAnnualPriceStats(marketData) {
    if (!marketData || marketData.length === 0) return [];
    const byYear = {};
    marketData.forEach((d) => {
      const dObj = typeof d.date === "string" ? new Date(d.date.replace(" 00:00:00", "").trim()) : new Date(d.date);
      if (isNaN(dObj)) return;
      const year = dObj.getFullYear();
      const key = String(year);
      const close = d.close != null ? Number(d.close) : null;
      if (close == null || isNaN(close)) return;
      if (!byYear[key]) byYear[key] = { period: key, closes: [] };
      byYear[key].closes.push(close);
    });
    const years = Object.keys(byYear).sort((a, b) => a.localeCompare(b));
    return years.map((key) => {
      const o = byYear[key];
      const closes = o.closes;
      return {
        period: key,
        high: Math.max(...closes),
        low: Math.min(...closes),
        avg: closes.reduce((s, v) => s + v, 0) / closes.length,
        closes,
      };
    });
  }

  /**
   * Group market data by quarter; return array of { period, high, low, avg } (close in thousands).
   * Sorted chronologically.
   */
  function getQuarterlyPriceStats(marketData) {
    if (!marketData || marketData.length === 0) return [];
    const byQuarter = {};
    marketData.forEach((d) => {
      const yq = parseDateToYearQ(d.date);
      if (!yq || d.close == null || isNaN(Number(d.close))) return;
      const key = quarterKey(yq.year, yq.q);
      const close = Number(d.close);
      if (!byQuarter[key]) byQuarter[key] = { period: key, highs: [], lows: [], closes: [] };
      byQuarter[key].closes.push(close);
      byQuarter[key].highs.push(close);
      byQuarter[key].lows.push(close);
    });
    const quarters = Object.keys(byQuarter).sort((a, b) => a.localeCompare(b));
    return quarters.map((key) => {
      const o = byQuarter[key];
      const highs = o.closes;
      const lows = o.closes;
      return {
        period: key,
        high: Math.max(...highs),
        low: Math.min(...lows),
        avg: highs.reduce((s, v) => s + v, 0) / highs.length,
        closes: o.closes,
      };
    });
  }

  /**
   * P/E and P/B trend. mode: 'annual' (default) or 'quarterly'.
   * - Annual + company HAS quarterly data: each day uses prior-quarter financials for its quarter; high/low/avg for the year = min/max/mean of all those daily P/E and P/B in that year.
   * - Annual + company has NO quarterly data: full year Y uses FY (Y-1) financials with year Y prices.
   * - Quarterly: one candle per quarter (Q uses Q-1 financials, high/low/avg for that quarter). Returns { peTrend, pbTrend }.
   */
  function buildValuationTrend(records, marketData, sharesOutstanding, mode = "annual") {
    if (sharesOutstanding == null || isNaN(sharesOutstanding)) {
      return { peTrend: [], pbTrend: [], evTrend: [] };
    }
    const latestClose = marketData && marketData.length > 0
      ? Number(marketData[marketData.length - 1].close)
      : null;
    const latestDateStr = marketData && marketData.length > 0 ? marketData[marketData.length - 1].date : null;

    const hasQuarterly = hasQuarterlyFinancialData(records);
    const useQuarterlyMode = mode === "quarterly" && hasQuarterly;

    if (useQuarterlyMode) {
      const financialMap = buildFinancialMapByQuarter(records, getEarningsKey(), getEarningsT4QKey());
      const priceQuarters = getQuarterlyPriceStats(marketData);
      if (priceQuarters.length === 0) return { peTrend: [], pbTrend: [], evTrend: [] };
      const peTrend = [];
      const pbTrend = [];
      const evTrend = [];

      priceQuarters.forEach((pq, i) => {
        const isLatest = i === priceQuarters.length - 1;
        const match = pq.period.match(/^(\d{4})-Q([1-4])$/);
        if (!match) return;
        const [, y, q] = match;
        const prev = getPreviousQuarter(parseInt(y, 10), parseInt(q, 10));
        const finKey = quarterKey(prev.year, prev.q);
        const fin = financialMap[finKey];
        if (!fin) return;

        const earningsVND = (fin.earningsMillions != null && !isNaN(fin.earningsMillions)) ? fin.earningsMillions * 1e6 : null;
        const equityVND = (fin.equityMillions != null && !isNaN(fin.equityMillions)) ? fin.equityMillions * 1e6 : null;
        const ebitdaVND = (fin.ebitdaMillions != null && !isNaN(fin.ebitdaMillions) && fin.ebitdaMillions > 0) ? fin.ebitdaMillions * 1e6 : null;
        const netDebtVND = (fin.netDebtMillions != null && !isNaN(fin.netDebtMillions)) ? fin.netDebtMillions * 1e6 : 0;
        const negativeEarnings = (fin.earningsMillions != null && !isNaN(fin.earningsMillions)) && fin.earningsMillions <= 0;
        const roic = (fin.roicT4q != null && !isNaN(fin.roicT4q)) ? fin.roicT4q : ((fin.roic != null && !isNaN(fin.roic)) ? fin.roic : null);

        const peValues = [];
        const pbValues = [];
        const evValues = [];
        pq.closes.forEach((close) => {
          const cap = close * 1000 * sharesOutstanding;
          if (earningsVND && earningsVND > 0) peValues.push(cap / earningsVND);
          if (equityVND && equityVND > 0) pbValues.push(cap / equityVND);
          if (ebitdaVND && ebitdaVND > 0) evValues.push((cap + netDebtVND) / ebitdaVND);
        });

        const peLow = peValues.length ? Math.min(...peValues) : null;
        const peHigh = peValues.length ? Math.max(...peValues) : null;
        const peAvg = peValues.length ? peValues.reduce((a, b) => a + b, 0) / peValues.length : null;
        let peCurrent = null;
        if (isLatest && latestClose != null && earningsVND && earningsVND > 0) {
          peCurrent = (latestClose * 1000 * sharesOutstanding) / earningsVND;
        }

        const pbLow = pbValues.length ? Math.min(...pbValues) : null;
        const pbHigh = pbValues.length ? Math.max(...pbValues) : null;
        const pbAvg = pbValues.length ? pbValues.reduce((a, b) => a + b, 0) / pbValues.length : null;
        let pbCurrent = null;
        if (isLatest && latestClose != null && equityVND && equityVND > 0) {
          pbCurrent = (latestClose * 1000 * sharesOutstanding) / equityVND;
        }

        const evLow = evValues.length ? Math.min(...evValues) : null;
        const evHigh = evValues.length ? Math.max(...evValues) : null;
        const evAvg = evValues.length ? evValues.reduce((a, b) => a + b, 0) / evValues.length : null;
        let evCurrent = null;
        if (isLatest && latestClose != null && ebitdaVND && ebitdaVND > 0) {
          evCurrent = ((latestClose * 1000 * sharesOutstanding) + netDebtVND) / ebitdaVND;
        }

        peTrend.push({ period: pq.period, low: peLow, high: peHigh, avg: peAvg, current: peCurrent, negativeEarnings, roic, roicQuarter: finKey });
        pbTrend.push({ period: pq.period, low: pbLow, high: pbHigh, avg: pbAvg, current: pbCurrent });
        evTrend.push({ period: pq.period, low: evLow, high: evHigh, avg: evAvg, current: evCurrent });
      });

      const QUARTERLY_TREND_QUARTERS = 12;
      const qSlice = Math.max(0, peTrend.length - QUARTERLY_TREND_QUARTERS);
      return { peTrend: peTrend.slice(qSlice), pbTrend: pbTrend.slice(qSlice), evTrend: evTrend.slice(qSlice) };
    }

    if (mode === "annual" && hasQuarterly) {
      // Annual view for companies WITH quarterly data: each day uses prior-quarter financials for its quarter; year high/low/avg = min/max/mean of all daily P/E and P/B in that year
      const financialMap = buildFinancialMapByQuarter(records, getEarningsKey(), getEarningsT4QKey());
      const byYear = {};
      (marketData || []).forEach((d) => {
        const yq = parseDateToYearQ(d.date);
        if (!yq || d.close == null || isNaN(Number(d.close))) return;
        const prev = getPreviousQuarter(yq.year, yq.q);
        const finKey = quarterKey(prev.year, prev.q);
        const fin = financialMap[finKey];
        if (!fin) return;
        const yearKey = String(yq.year);
        if (!byYear[yearKey]) byYear[yearKey] = { peValues: [], pbValues: [] };
        const cap = Number(d.close) * 1000 * sharesOutstanding;
        const earningsVND = (fin.earningsMillions != null && !isNaN(fin.earningsMillions)) ? fin.earningsMillions * 1e6 : null;
        const equityVND = (fin.equityMillions != null && !isNaN(fin.equityMillions)) ? fin.equityMillions * 1e6 : null;
        if (earningsVND && earningsVND > 0) byYear[yearKey].peValues.push(cap / earningsVND);
        if (equityVND && equityVND > 0) byYear[yearKey].pbValues.push(cap / equityVND);
      });
      const years = Object.keys(byYear).sort((a, b) => a.localeCompare(b));
      if (years.length === 0) return { peTrend: [], pbTrend: [], evTrend: [] };
      const peTrend = [];
      const pbTrend = [];
      const evTrend = [];
      const byYearEv = {};
      (marketData || []).forEach((d) => {
        const yq = parseDateToYearQ(d.date);
        if (!yq || d.close == null || isNaN(Number(d.close))) return;
        const prev = getPreviousQuarter(yq.year, yq.q);
        const finKey = quarterKey(prev.year, prev.q);
        const fin = financialMap[finKey];
        if (!fin) return;
        const yearKey = String(yq.year);
        const ebitdaVND = (fin.ebitdaMillions != null && !isNaN(fin.ebitdaMillions) && fin.ebitdaMillions > 0) ? fin.ebitdaMillions * 1e6 : null;
        const netDebtVND = (fin.netDebtMillions != null && !isNaN(fin.netDebtMillions)) ? fin.netDebtMillions * 1e6 : 0;
        if (ebitdaVND && ebitdaVND > 0) {
          if (!byYearEv[yearKey]) byYearEv[yearKey] = [];
          byYearEv[yearKey].push((Number(d.close) * 1000 * sharesOutstanding + netDebtVND) / ebitdaVND);
        }
      });
      const latestYQ = latestDateStr ? parseDateToYearQ(latestDateStr) : null;
      const prevForCurrent = latestYQ ? getPreviousQuarter(latestYQ.year, latestYQ.q) : null;
      const finForCurrent = prevForCurrent ? financialMap[quarterKey(prevForCurrent.year, prevForCurrent.q)] : null;
      const earningsVNDCurrent = finForCurrent?.earningsMillions != null ? finForCurrent.earningsMillions * 1e6 : null;
      const equityVNDCurrent = finForCurrent?.equityMillions != null ? finForCurrent.equityMillions * 1e6 : null;
      const ebitdaVNDCurrent = (finForCurrent?.ebitdaMillions != null && !isNaN(finForCurrent.ebitdaMillions) && finForCurrent.ebitdaMillions > 0) ? finForCurrent.ebitdaMillions * 1e6 : null;
      const netDebtVNDCurrent = (finForCurrent?.netDebtMillions != null && !isNaN(finForCurrent.netDebtMillions)) ? finForCurrent.netDebtMillions * 1e6 : 0;

      years.forEach((yearKey, i) => {
        const isLatest = i === years.length - 1;
        const o = byYear[yearKey];
        const evValues = byYearEv[yearKey] || [];
        const peLow = o.peValues.length ? Math.min(...o.peValues) : null;
        const peHigh = o.peValues.length ? Math.max(...o.peValues) : null;
        const peAvg = o.peValues.length ? o.peValues.reduce((a, b) => a + b, 0) / o.peValues.length : null;
        let peCurrent = null;
        if (isLatest && latestClose != null && earningsVNDCurrent && earningsVNDCurrent > 0) {
          peCurrent = (latestClose * 1000 * sharesOutstanding) / earningsVNDCurrent;
        }
        const pbLow = o.pbValues.length ? Math.min(...o.pbValues) : null;
        const pbHigh = o.pbValues.length ? Math.max(...o.pbValues) : null;
        const pbAvg = o.pbValues.length ? o.pbValues.reduce((a, b) => a + b, 0) / o.pbValues.length : null;
        let pbCurrent = null;
        if (isLatest && latestClose != null && equityVNDCurrent && equityVNDCurrent > 0) {
          pbCurrent = (latestClose * 1000 * sharesOutstanding) / equityVNDCurrent;
        }
        const evLow = evValues.length ? Math.min(...evValues) : null;
        const evHigh = evValues.length ? Math.max(...evValues) : null;
        const evAvg = evValues.length ? evValues.reduce((a, b) => a + b, 0) / evValues.length : null;
        let evCurrent = null;
        if (isLatest && latestClose != null && ebitdaVNDCurrent && ebitdaVNDCurrent > 0) {
          evCurrent = ((latestClose * 1000 * sharesOutstanding) + netDebtVNDCurrent) / ebitdaVNDCurrent;
        }
        const negativeEarnings = o.peValues.length === 0;
        const prevYear = String(parseInt(yearKey, 10) - 1);
        const t4qKeys = [prevYear + "-Q4", yearKey + "-Q1", yearKey + "-Q2", yearKey + "-Q3"];
        const roicByQuarter = {};
        t4qKeys.forEach((k) => {
          const v = financialMap[k];
          const roicVal = (v?.roicT4q != null && !isNaN(v.roicT4q)) ? v.roicT4q : v?.roic;
          if (roicVal != null && !isNaN(roicVal)) roicByQuarter[k] = roicVal;
        });
        const finQ4 = financialMap[prevYear + "-Q4"];
        const finQ3 = financialMap[yearKey + "-Q3"];
        const roicQ4 = (finQ4?.roicT4q != null && !isNaN(finQ4.roicT4q)) ? finQ4.roicT4q : finQ4?.roic;
        const roicQ3 = (finQ3?.roicT4q != null && !isNaN(finQ3.roicT4q)) ? finQ3.roicT4q : finQ3?.roic;
        const roic = roicQ4 != null ? roicQ4 : (roicQ3 != null ? roicQ3 : null);
        peTrend.push({ period: yearKey, low: peLow, high: peHigh, avg: peAvg, current: peCurrent, negativeEarnings, roic, roicByQuarter: Object.keys(roicByQuarter).length ? roicByQuarter : undefined });
        pbTrend.push({ period: yearKey, low: pbLow, high: pbHigh, avg: pbAvg, current: pbCurrent });
        evTrend.push({ period: yearKey, low: evLow, high: evHigh, avg: evAvg, current: evCurrent });
      });
      const ANNUAL_TREND_YEARS = 5;
      const ySlice = Math.max(0, peTrend.length - ANNUAL_TREND_YEARS);
      return { peTrend: peTrend.slice(ySlice), pbTrend: pbTrend.slice(ySlice), evTrend: evTrend.slice(ySlice) };
    }

    // Annual: company has NO quarterly data — full year Y uses FY (Y-1) financials with year Y prices
    const financialMapByYear = buildFinancialMapByYear(records, getEarningsKey());
    const priceYears = getAnnualPriceStats(marketData);
    if (priceYears.length === 0) return { peTrend: [], pbTrend: [], evTrend: [] };
    const peTrend = [];
    const pbTrend = [];
    const evTrend = [];

    priceYears.forEach((py, i) => {
      const isLatest = i === priceYears.length - 1;
      const year = parseInt(py.period, 10);
      const prevYearKey = String(year - 1);
      const fin = financialMapByYear[prevYearKey];
      if (!fin) return;

      const earningsVND = (fin.earningsMillions != null && !isNaN(fin.earningsMillions)) ? fin.earningsMillions * 1e6 : null;
      const equityVND = (fin.equityMillions != null && !isNaN(fin.equityMillions)) ? fin.equityMillions * 1e6 : null;
      const ebitdaVND = (fin.ebitdaMillions != null && !isNaN(fin.ebitdaMillions) && fin.ebitdaMillions > 0) ? fin.ebitdaMillions * 1e6 : null;
      const netDebtVND = (fin.netDebtMillions != null && !isNaN(fin.netDebtMillions)) ? fin.netDebtMillions * 1e6 : 0;
      const negativeEarnings = (fin.earningsMillions != null && !isNaN(fin.earningsMillions)) && fin.earningsMillions <= 0;
      const roic = (fin.roic != null && !isNaN(fin.roic)) ? fin.roic : null;

      const peValues = [];
      const pbValues = [];
      const evValues = [];
      py.closes.forEach((close) => {
        const cap = close * 1000 * sharesOutstanding;
        if (earningsVND && earningsVND > 0) peValues.push(cap / earningsVND);
        if (equityVND && equityVND > 0) pbValues.push(cap / equityVND);
        if (ebitdaVND && ebitdaVND > 0) evValues.push((cap + netDebtVND) / ebitdaVND);
      });

      const peLow = peValues.length ? Math.min(...peValues) : null;
      const peHigh = peValues.length ? Math.max(...peValues) : null;
      const peAvg = peValues.length ? peValues.reduce((a, b) => a + b, 0) / peValues.length : null;
      let peCurrent = null;
      if (isLatest && latestClose != null && earningsVND && earningsVND > 0) {
        peCurrent = (latestClose * 1000 * sharesOutstanding) / earningsVND;
      }

      const pbLow = pbValues.length ? Math.min(...pbValues) : null;
      const pbHigh = pbValues.length ? Math.max(...pbValues) : null;
      const pbAvg = pbValues.length ? pbValues.reduce((a, b) => a + b, 0) / pbValues.length : null;
      let pbCurrent = null;
      if (isLatest && latestClose != null && equityVND && equityVND > 0) {
        pbCurrent = (latestClose * 1000 * sharesOutstanding) / equityVND;
      }

      const evLow = evValues.length ? Math.min(...evValues) : null;
      const evHigh = evValues.length ? Math.max(...evValues) : null;
      const evAvg = evValues.length ? evValues.reduce((a, b) => a + b, 0) / evValues.length : null;
      let evCurrent = null;
      if (isLatest && latestClose != null && ebitdaVND && ebitdaVND > 0) {
        evCurrent = ((latestClose * 1000 * sharesOutstanding) + netDebtVND) / ebitdaVND;
      }

      peTrend.push({ period: py.period, low: peLow, high: peHigh, avg: peAvg, current: peCurrent, negativeEarnings, roic });
      pbTrend.push({ period: py.period, low: pbLow, high: pbHigh, avg: pbAvg, current: pbCurrent });
      evTrend.push({ period: py.period, low: evLow, high: evHigh, avg: evAvg, current: evCurrent });
    });

    const ANNUAL_TREND_YEARS_FY = 5;
    const fySlice = Math.max(0, peTrend.length - ANNUAL_TREND_YEARS_FY);
    return { peTrend: peTrend.slice(fySlice), pbTrend: pbTrend.slice(fySlice), evTrend: evTrend.slice(fySlice) };
  }

  /**
   * Candle-like sparkline: vertical bar from low to high, tick at average; for latest, tick at current.
   * trendItems: [{ period, low, high, avg, current?, negativeEarnings?, roic? }].
   * options: { negativeEarningsKey, getTooltipContent: (t, formatLabel) => string, getTooltipNote: (t) => string | undefined }.
   */
  function generateValuationCandleSparkline(trendItems, formatLabel, options = {}) {
    if (!trendItems || trendItems.length === 0) return "—";
    const valid = trendItems.filter((t) => t.low != null && t.high != null && t.avg != null);
    if (valid.length === 0) return "—";
    const allVals = valid.flatMap((t) => [t.low, t.high, t.avg, t.current].filter((v) => v != null && !isNaN(v)));
    const minVal = Math.min(...allVals);
    const maxVal = Math.max(...allVals);
    const range = Math.max(maxVal - minVal, 0.001);
    const negKey = options.negativeEarningsKey || null;
    const getTooltipContent = options.getTooltipContent || null;
    const getTooltipNote = options.getTooltipNote || null;

    const cells = trendItems.map((t, i) => {
      const isLatest = i === trendItems.length - 1;
      const hasData = t.low != null && t.high != null && t.avg != null && !isNaN(t.low) && !isNaN(t.high) && !isNaN(t.avg);
      const low = hasData ? t.low : minVal;
      const high = hasData ? t.high : maxVal;
      const avg = hasData ? t.avg : (low + high) / 2;
      const current = isLatest && t.current != null && !isNaN(t.current) ? t.current : null;

      const lowPct = ((low - minVal) / range) * 100;
      const highPct = ((high - minVal) / range) * 100;
      const avgPct = ((avg - minVal) / range) * 100;
      const currentPct = current != null ? ((current - minVal) / range) * 100 : null;

      const tooltipResult = getTooltipContent
        ? getTooltipContent(t, formatLabel)
        : (() => {
            const parts = hasData ? ["High " + formatLabel(high), "Low " + formatLabel(low), "Avg " + formatLabel(avg)] : ["No data"];
            if (current != null) parts.push("Current " + formatLabel(current));
            return t.period + ": " + parts.join(", ");
          })();

      const tooltipNote = getTooltipNote ? getTooltipNote(t) : undefined;
      const noteAttr = tooltipNote ? ` data-tooltip-note="${String(tooltipNote).replace(/"/g, "&quot;")}"` : "";
      const escAttr = (s) => String(s ?? "").replace(/"/g, "&quot;").replace(/\n/g, "&#10;");
      const isSections = tooltipResult && typeof tooltipResult === "object" && "period" in tooltipResult;
      const tooltipAttrs = isSections
        ? ` data-tooltip-period="${escAttr(tooltipResult.period)}" data-tooltip-metrics="${escAttr(tooltipResult.metrics)}" data-tooltip-roic="${escAttr(tooltipResult.roic ?? "")}"${noteAttr}`
        : ` data-tooltip="${escAttr(tooltipResult)}"${noteAttr}`;

      const isNegative = negKey && t[negKey];
      const wickClass = "valuation-candle-wick" + (!hasData ? " valuation-candle-wick--no-data" : "") + (isNegative ? " valuation-candle-wick--negative" : "");

      if (!hasData) {
        return `<div class="valuation-candle-cell valuation-candle-cell--no-data"${tooltipAttrs}>
          <div class="${wickClass}"></div>
        </div>`;
      }

      return `<div class="valuation-candle-cell"${tooltipAttrs}>
        <div class="${wickClass}" style="bottom: ${lowPct}%; top: ${100 - highPct}%;"></div>
        <div class="valuation-candle-avg" style="bottom: ${avgPct}%;"></div>
        ${currentPct != null ? `<div class="valuation-candle-current" style="bottom: ${currentPct}%;"></div>` : ""}
      </div>`;
    });
    const n = trendItems.length;
    const gap = 8;
    const annualClass = n <= 6 ? " valuation-candle-chart--annual" : "";
    return `<div class="valuation-candle-chart${annualClass}" style="--valuation-candle-n: ${n}; --valuation-candle-gap: ${gap}px;">${cells.join("")}</div>`;
  }

  /**
   * P/E earnings: use latest T4Q if there is a quarter more recent than the latest FY (later year),
   * otherwise use latest FY. Values are in millions VND.
   * Uses earningsKey and earningsT4QKey when provided (for Actual vs Normalized mode).
   */
  function getEarningsForPE(records, earningsKey, earningsT4QKey) {
    const niKey = earningsKey || "Net Income";
    const t4qKey = earningsT4QKey || "Net Income T4Q";
    const fyRecords = records.filter((r) => String(r.Period || "").endsWith("-FY") && r[niKey] != null && !isNaN(r[niKey]));
    const latestFY = fyRecords.length === 0 ? null : [...fyRecords].sort((a, b) => {
      const ya = parseInt(String(a.Period || "").match(/^(\d{4})/)?.[1] || "0", 10);
      const yb = parseInt(String(b.Period || "").match(/^(\d{4})/)?.[1] || "0", 10);
      return yb - ya;
    })[0];
    const t4q = getLatestValueWithPeriod(records, t4qKey);
    const fyYear = latestFY ? parseInt(String(latestFY.Period || "").match(/^(\d{4})/)?.[1] || 0, 10) : 0;
    const t4qYear = t4q?.period ? parseInt(String(t4q.period).match(/^(\d{4})/)?.[1] || 0, 10) : 0;
    if (t4q?.value != null && !isNaN(t4q.value) && t4qYear > fyYear) {
      return t4q.value;
    }
    if (latestFY && latestFY[niKey] != null && !isNaN(latestFY[niKey])) {
      return latestFY[niKey];
    }
    if (t4q?.value != null && !isNaN(t4q.value)) {
      return t4q.value;
    }
    return null;
  }

  /**
   * P/E = Market Cap / Earnings.
   * Earnings from getEarningsForPE (T4Q or FY, in millions VND); market cap in VND.
   */
  function calculatePE(records, marketCapVND) {
    if (marketCapVND == null || marketCapVND <= 0) return null;
    const earningsMillions = getEarningsForPE(records || [], getEarningsKey(), getEarningsT4QKey());
    if (earningsMillions == null || isNaN(earningsMillions) || earningsMillions <= 0) return null;
    const earningsVND = earningsMillions * 1e6;
    return marketCapVND / earningsVND;
  }

  /**
   * P/B = Market Cap / Equity.
   * Equity is in millions VND; market cap in VND. P/B = marketCapVND / (equity * 1e6).
   */
  function calculatePB(records, marketCapVND) {
    if (marketCapVND == null || marketCapVND <= 0) return null;
    const eq = getLatestValueWithPeriod(records, "Equity");
    const equity = eq?.value;
    if (equity == null || isNaN(equity) || equity <= 0) return null;
    const equityVND = equity * 1e6;
    return marketCapVND / equityVND;
  }

  /**
   * EBITDA for valuation: use latest T4Q if there is a quarter more recent than latest FY (later year),
   * otherwise use latest FY. Uses ebitdaKey and ebitdaT4QKey (matches current earnings mode).
   * Value in millions VND.
   */
  function getEBITDAForValuation(records, ebitdaKey, ebitdaT4QKey) {
    const key = ebitdaKey || "EBITDA";
    const t4qKey = ebitdaT4QKey || "EBITDA T4Q";
    const fyRecords = records.filter((r) => String(r.Period || "").endsWith("-FY") && r[key] != null && !isNaN(r[key]));
    const latestFY = fyRecords.length === 0 ? null : [...fyRecords].sort((a, b) => {
      const ya = parseInt(String(a.Period || "").match(/^(\d{4})/)?.[1] || "0", 10);
      const yb = parseInt(String(b.Period || "").match(/^(\d{4})/)?.[1] || "0", 10);
      return yb - ya;
    })[0];
    const t4q = getLatestValueWithPeriod(records, t4qKey);
    const fyYear = latestFY ? parseInt(String(latestFY.Period || "").match(/^(\d{4})/)?.[1] || 0, 10) : 0;
    const t4qYear = t4q?.period ? parseInt(String(t4q.period).match(/^(\d{4})/)?.[1] || 0, 10) : 0;
    if (t4q?.value != null && !isNaN(t4q.value) && t4qYear > fyYear) {
      return t4q.value;
    }
    if (latestFY && latestFY[key] != null && !isNaN(latestFY[key])) {
      return latestFY[key];
    }
    if (t4q?.value != null && !isNaN(t4q.value)) {
      return t4q.value;
    }
    return null;
  }

  /** Return the record with the latest period (same ordering as getLatestValueWithPeriod). */
  function getLatestRecord(records) {
    if (!records || records.length === 0) return null;
    const sorted = [...records].sort((a, b) => {
      const pa = String(a.Period || "");
      const pb = String(b.Period || "");
      const yearA = parseInt(pa.match(/^(\d{4})/)?.[1] || "0", 10);
      const yearB = parseInt(pb.match(/^(\d{4})/)?.[1] || "0", 10);
      if (yearA !== yearB) return yearB - yearA;
      return periodSortRank(pb) - periodSortRank(pa);
    });
    return sorted[0];
  }

  /**
   * Net debt (millions VND) = Interest Bearing Debt Short Term + Interest Bearing Debt Long Term - Cash And Equivalent.
   * Uses latest record by period. Returns 0 if data missing (EV = market cap).
   */
  function getNetDebtMillions(records) {
    const r = getLatestRecord(records || []);
    if (!r) return 0;
    const ibdShort = (r["Interest Bearing Debt Short Term"] != null && !isNaN(r["Interest Bearing Debt Short Term"]))
      ? Number(r["Interest Bearing Debt Short Term"]) : 0;
    const ibdLong = (r["Interest Bearing Debt Long Term"] != null && !isNaN(r["Interest Bearing Debt Long Term"]))
      ? Number(r["Interest Bearing Debt Long Term"]) : 0;
    const cash = (r["Cash And Equivalent"] != null && !isNaN(r["Cash And Equivalent"]))
      ? Number(r["Cash And Equivalent"]) : 0;
    return ibdShort + ibdLong - cash;
  }

  /**
   * EV/EBITDA = (Market Cap + Net Debt) / EBITDA.
   * EBITDA from getEBITDAForValuation (matches current earnings mode); EV in VND, EBITDA in millions VND.
   */
  function calculateEVEBITDA(records, marketCapVND) {
    if (marketCapVND == null || marketCapVND <= 0) return null;
    const ebitdaMillions = getEBITDAForValuation(records || [], getEBITDAKey(), getEBITDAT4QKey());
    if (ebitdaMillions == null || isNaN(ebitdaMillions) || ebitdaMillions <= 0) return null;
    const netDebtMillions = getNetDebtMillions(records || []);
    const evVND = marketCapVND + netDebtMillions * 1e6;
    return evVND / (ebitdaMillions * 1e6);
  }

  /**
   * Compute current P/E, P/B, EV/EBITDA and 52w high/low for the header. Uses same logic as valuation section.
   * Returns { currentPE, currentPB, currentEVEBITDA, pe52wLow, pe52wHigh, pb52wLow, pb52wHigh, ev52wLow, ev52wHigh }.
   */
  function computeHeaderPEPB(records, marketData, sharesOutstanding) {
    const out = {
      currentPE: null, currentPB: null, currentEVEBITDA: null,
      pe52wLow: null, pe52wHigh: null, pb52wLow: null, pb52wHigh: null, ev52wLow: null, ev52wHigh: null
    };
    if (!marketData || marketData.length === 0 || sharesOutstanding == null || isNaN(sharesOutstanding)) return out;
    const latest = marketData[marketData.length - 1];
    const currentMarketCapVND = (latest?.close != null) ? latest.close * 1000 * sharesOutstanding : null;
    if (currentMarketCapVND == null) return out;
    out.currentPE = calculatePE(records || [], currentMarketCapVND);
    out.currentPB = calculatePB(records || [], currentMarketCapVND);
    out.currentEVEBITDA = calculateEVEBITDA(records || [], currentMarketCapVND);

    const now = new Date();
    const cutoff52w = new Date(now);
    cutoff52w.setDate(cutoff52w.getDate() - 365);
    const last52w = marketData.filter((d) => {
      const t = typeof d.date === "string" ? new Date(d.date.replace(" 00:00:00", "")) : new Date(d.date);
      return !isNaN(t) && t >= cutoff52w && d.close != null && !isNaN(d.close);
    });
    if (last52w.length === 0) return out;

    const pe52wValues = [];
    const pb52wValues = [];
    const ev52wValues = [];
    const hasQuarterly = hasQuarterlyFinancialData(records || []);

    if (hasQuarterly) {
      const financialMap = buildFinancialMapByQuarter(records, getEarningsKey(), getEarningsT4QKey());
      last52w.forEach((d) => {
        const yq = parseDateToYearQ(d.date);
        if (!yq) return;
        const prev = getPreviousQuarter(yq.year, yq.q);
        const finKey = quarterKey(prev.year, prev.q);
        const fin = financialMap[finKey];
        if (!fin) return;
        const earningsVND = (fin.earningsMillions != null && !isNaN(fin.earningsMillions)) ? fin.earningsMillions * 1e6 : null;
        const equityVND = (fin.equityMillions != null && !isNaN(fin.equityMillions)) ? fin.equityMillions * 1e6 : null;
        const ebitdaVND = (fin.ebitdaMillions != null && !isNaN(fin.ebitdaMillions) && fin.ebitdaMillions > 0) ? fin.ebitdaMillions * 1e6 : null;
        const netDebtVND = (fin.netDebtMillions != null && !isNaN(fin.netDebtMillions)) ? fin.netDebtMillions * 1e6 : 0;
        const cap = Number(d.close) * 1000 * sharesOutstanding;
        if (earningsVND && earningsVND > 0) pe52wValues.push(cap / earningsVND);
        if (equityVND && equityVND > 0) pb52wValues.push(cap / equityVND);
        if (ebitdaVND && ebitdaVND > 0) ev52wValues.push((cap + netDebtVND) / ebitdaVND);
      });
    } else {
      const financialMapByYear = buildFinancialMapByYear(records, getEarningsKey());
      last52w.forEach((d) => {
        const t = typeof d.date === "string" ? new Date(d.date.replace(" 00:00:00", "")) : new Date(d.date);
        if (isNaN(t)) return;
        const year = t.getFullYear();
        const prevYearKey = String(year - 1);
        const fin = financialMapByYear[prevYearKey];
        if (!fin) return;
        const earningsVND = (fin.earningsMillions != null && !isNaN(fin.earningsMillions)) ? fin.earningsMillions * 1e6 : null;
        const equityVND = (fin.equityMillions != null && !isNaN(fin.equityMillions)) ? fin.equityMillions * 1e6 : null;
        const ebitdaVND = (fin.ebitdaMillions != null && !isNaN(fin.ebitdaMillions) && fin.ebitdaMillions > 0) ? fin.ebitdaMillions * 1e6 : null;
        const netDebtVND = (fin.netDebtMillions != null && !isNaN(fin.netDebtMillions)) ? fin.netDebtMillions * 1e6 : 0;
        const cap = Number(d.close) * 1000 * sharesOutstanding;
        if (earningsVND && earningsVND > 0) pe52wValues.push(cap / earningsVND);
        if (equityVND && equityVND > 0) pb52wValues.push(cap / equityVND);
        if (ebitdaVND && ebitdaVND > 0) ev52wValues.push((cap + netDebtVND) / ebitdaVND);
      });
    }

    out.pe52wLow = pe52wValues.length > 0 ? Math.min(...pe52wValues) : null;
    out.pe52wHigh = pe52wValues.length > 0 ? Math.max(...pe52wValues) : null;
    out.pb52wLow = pb52wValues.length > 0 ? Math.min(...pb52wValues) : null;
    out.pb52wHigh = pb52wValues.length > 0 ? Math.max(...pb52wValues) : null;
    out.ev52wLow = ev52wValues.length > 0 ? Math.min(...ev52wValues) : null;
    out.ev52wHigh = ev52wValues.length > 0 ? Math.max(...ev52wValues) : null;
    return out;
  }

  /**
   * Update P/E, P/B and EV/EBITDA blocks in the header (current value + 52w range bar). Same data source as valuation section.
   */
  function updateHeaderPEPB(summary) {
    if (!summary) summary = {};
    const currentPE = summary.currentPE;
    const currentPB = summary.currentPB;
    const currentEVEBITDA = summary.currentEVEBITDA;
    const pe52wLow = summary.pe52wLow;
    const pe52wHigh = summary.pe52wHigh;
    const pb52wLow = summary.pb52wLow;
    const pb52wHigh = summary.pb52wHigh;
    const ev52wLow = summary.ev52wLow;
    const ev52wHigh = summary.ev52wHigh;

    const peValEl = document.getElementById("stock-pe-value");
    const pbValEl = document.getElementById("stock-pb-value");
    const evValEl = document.getElementById("stock-ev-value");
    if (peValEl) peValEl.textContent = currentPE != null && !isNaN(currentPE) ? currentPE.toFixed(1) : "—";
    if (pbValEl) pbValEl.textContent = currentPB != null && !isNaN(currentPB) ? currentPB.toFixed(2) : "—";
    if (evValEl) evValEl.textContent = currentEVEBITDA != null && !isNaN(currentEVEBITDA) ? currentEVEBITDA.toFixed(1) : "—";

    function set52wBar(currentVal, low, high, lineEl, lowEl, highEl, barEl, fillEl, tickerEl, formatVal) {
      const line = document.getElementById(lineEl);
      const lowE = document.getElementById(lowEl);
      const highE = document.getElementById(highEl);
      const bar = document.getElementById(barEl);
      const fill = document.getElementById(fillEl);
      const ticker = document.getElementById(tickerEl);
      if (low != null && high != null) {
        if (line) line.style.display = "flex";
        if (lowE) lowE.textContent = formatVal(low);
        if (highE) highE.textContent = formatVal(high);
        if (bar && fill && ticker) {
          bar.style.display = "flex";
          if (low !== high && currentVal != null) {
            const pct = Math.max(0, Math.min(1, (currentVal - low) / (high - low)));
            fill.style.width = (pct * 100) + "%";
            ticker.style.left = (pct * 100) + "%";
            ticker.style.display = "block";
          } else {
            fill.style.width = "100%";
            ticker.style.display = "block";
            ticker.style.left = "100%";
          }
        }
      } else {
        if (line) line.style.display = "none";
        if (lowE) lowE.textContent = "—";
        if (highE) highE.textContent = "—";
        if (bar) bar.style.display = "none";
      }
    }
    set52wBar(currentPE, pe52wLow, pe52wHigh,
      "stock-pe-52w-line", "stock-pe-52w-low", "stock-pe-52w-high",
      "stock-pe-52w-bar", "stock-pe-52w-bar-fill", "stock-pe-52w-bar-ticker",
      (v) => (v != null ? v.toFixed(1) : "—"));
    set52wBar(currentPB, pb52wLow, pb52wHigh,
      "stock-pb-52w-line", "stock-pb-52w-low", "stock-pb-52w-high",
      "stock-pb-52w-bar", "stock-pb-52w-bar-fill", "stock-pb-52w-bar-ticker",
      (v) => (v != null ? v.toFixed(2) : "—"));
    set52wBar(currentEVEBITDA, ev52wLow, ev52wHigh,
      "stock-ev-52w-line", "stock-ev-52w-low", "stock-ev-52w-high",
      "stock-ev-52w-bar", "stock-ev-52w-bar-fill", "stock-ev-52w-bar-ticker",
      (v) => (v != null ? v.toFixed(1) : "—"));
  }

  function initValuationCandleTooltips() {
    const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    const unescapeAttr = (s) => String(s ?? "").replace(/&#10;/g, "\n");
    let tooltipEl = null;
    document.querySelectorAll(".valuation-candle-cell").forEach((cell) => {
      cell.addEventListener("mouseenter", (e) => {
        const period = e.currentTarget.getAttribute("data-tooltip-period");
        const hasSections = period != null;
        let text = hasSections ? null : e.currentTarget.getAttribute("data-tooltip");
        if (!hasSections && !text) return;
        if (hasSections) {
          const metrics = unescapeAttr(e.currentTarget.getAttribute("data-tooltip-metrics"));
          const roic = unescapeAttr(e.currentTarget.getAttribute("data-tooltip-roic"));
          const note = e.currentTarget.getAttribute("data-tooltip-note");
          tooltipEl = document.createElement("div");
          tooltipEl.className = "sparkline-tooltip sparkline-tooltip--sections";
          tooltipEl.innerHTML =
            '<div class="valuation-tooltip-period">' + escapeHtml(period) + "</div>" +
            '<div class="valuation-tooltip-metrics">' + escapeHtml(metrics).replace(/\n/g, "<br>") + "</div>" +
            (roic ? '<div class="valuation-tooltip-roic">' + escapeHtml(roic).replace(/\n/g, "<br>") + "</div>" : "") +
            (note ? '<div class="valuation-tooltip-note">' + escapeHtml(note) + "</div>" : "");
          document.body.appendChild(tooltipEl);
        } else {
          text = text.replace(/&#10;/g, "\n");
          const note = e.currentTarget.getAttribute("data-tooltip-note");
          tooltipEl = document.createElement("div");
          tooltipEl.className = "sparkline-tooltip sparkline-tooltip--multiline";
          if (note) {
            const mainEscaped = escapeHtml(text);
            tooltipEl.innerHTML = mainEscaped.replace(/\n/g, "<br>") + '<div class="valuation-tooltip-note">' + escapeHtml(note) + "</div>";
          } else {
            tooltipEl.textContent = text;
          }
          document.body.appendChild(tooltipEl);
        }
        const updatePosition = () => {
          if (!tooltipEl?.parentNode) return;
          const rect = cell.getBoundingClientRect();
          tooltipEl.style.left = Math.max(4, rect.left + rect.width / 2 - tooltipEl.offsetWidth / 2) + "px";
          tooltipEl.style.top = (rect.top - tooltipEl.offsetHeight - 6) + "px";
        };
        updatePosition();
        cell.addEventListener("mousemove", updatePosition);
        cell.addEventListener("mouseleave", () => {
          cell.removeEventListener("mousemove", updatePosition);
          if (tooltipEl?.parentNode) tooltipEl.remove();
          tooltipEl = null;
        }, { once: true });
      });
    });
  }

  /** Rebuild and render P/E, P/B and EV/EBITDA trend from currentRecords / currentMarketData / currentSharesOutstanding and currentValuationTrendMode. */
  function refreshValuationTrendFromCurrent() {
    const records = currentRecords;
    const marketData = currentMarketData;
    const sharesOutstanding = currentSharesOutstanding;
    const { peTrend, pbTrend, evTrend } = buildValuationTrend(records || [], marketData || [], sharesOutstanding, currentValuationTrendMode);
    const isAnnual = currentValuationTrendMode === "annual";
    const trendWindow = isAnnual ? "5Y" : "3Y";
    const trendLabel = isAnnual
      ? "5Y · Annual trend (High / Low / Avg, prior FY financials)"
      : "3Y · Quarterly trend (High / Low / Avg)";
    document.querySelectorAll(".valuation-trend-label").forEach((el) => { el.textContent = trendLabel; });

    const peTrendEl = document.getElementById("valuation-pe-trend");
    const pbTrendEl = document.getElementById("valuation-pb-trend");
    const hasQuarterlyForTrend = hasQuarterlyFinancialData(records || []);
    // Quarter view: show actual quarter (t.roicQuarter). Fallback: prior Q / T4Q / FY.
    const roicLabelForSingle = hasQuarterlyForTrend ? (isAnnual ? "T4Q" : "prior Q") : "FY";
    if (peTrendEl) {
      const peFormatLabel = (v) => (v != null ? v.toFixed(1) : "—");
      const peTooltipContent = (t, formatLabel) => {
        const period = t.period;
        const hasData = t.low != null && t.high != null && t.avg != null;
        const metrics = hasData
          ? "High " + formatLabel(t.high) + ", Low " + formatLabel(t.low) + ", Avg " + formatLabel(t.avg) + (t.current != null && !isNaN(t.current) ? ", Current " + formatLabel(t.current) : "")
          : "No data";
        let roic = "";
        if (t.roicByQuarter && typeof t.roicByQuarter === "object") {
          roic = Object.keys(t.roicByQuarter)
            .sort()
            .map((k) => {
              const v = t.roicByQuarter[k];
              return (v != null && !isNaN(v)) ? "ROIC " + k + ": " + (v * 100).toFixed(1) + "%" : "";
            })
            .filter(Boolean)
            .join("\n");
        } else if (t.roic != null && !isNaN(t.roic)) {
          const roicLabel = t.roicQuarter || roicLabelForSingle;
          roic = "ROIC (" + roicLabel + "): " + (t.roic * 100).toFixed(1) + "%";
        }
        return { period, metrics, roic };
      };
      // Trailing 4 quarters note: annual view (roicByQuarter) and quarter view (single T4Q roic)
      const peTooltipNote = (t) => ((t.roicByQuarter && typeof t.roicByQuarter === "object" && Object.keys(t.roicByQuarter).length > 0) || (!isAnnual && t.roic != null && !isNaN(t.roic)) ? "Trailing 4 quarters" : undefined);
      peTrendEl.innerHTML = generateValuationCandleSparkline(peTrend, peFormatLabel, {
        negativeEarningsKey: "negativeEarnings",
        getTooltipContent: peTooltipContent,
        getTooltipNote: peTooltipNote,
      });
      if (peTrend.length > 0) {
        const allPe = peTrend.flatMap((t) => [t.low, t.high, t.avg, t.current].filter((v) => v != null && !isNaN(v)));
        if (allPe.length > 0) {
          const peMin = Math.min(...allPe);
          const peMax = Math.max(...allPe);
          const el = document.getElementById("valuation-pe-range");
          if (el) el.textContent = `${trendWindow} range: ${peMin.toFixed(1)} – ${peMax.toFixed(1)}`;
        }
      }
    }
    if (pbTrendEl) {
      pbTrendEl.innerHTML = generateValuationCandleSparkline(pbTrend, (v) => (v != null ? v.toFixed(2) : "—"));
      if (pbTrend.length > 0) {
        const allPb = pbTrend.flatMap((t) => [t.low, t.high, t.avg, t.current].filter((v) => v != null && !isNaN(v)));
        if (allPb.length > 0) {
          const pbMin = Math.min(...allPb);
          const pbMax = Math.max(...allPb);
          const el = document.getElementById("valuation-pb-range");
          if (el) el.textContent = `${trendWindow} range: ${pbMin.toFixed(2)} – ${pbMax.toFixed(2)}`;
        }
      }
    }
    const evTrendEl = document.getElementById("valuation-ev-trend");
    if (evTrendEl && evTrend && evTrend.length > 0) {
      evTrendEl.innerHTML = generateValuationCandleSparkline(evTrend, (v) => (v != null ? v.toFixed(1) : "—"));
      const allEv = evTrend.flatMap((t) => [t.low, t.high, t.avg, t.current].filter((v) => v != null && !isNaN(v)));
      if (allEv.length > 0) {
        const evMin = Math.min(...allEv);
        const evMax = Math.max(...allEv);
        const el = document.getElementById("valuation-ev-range");
        if (el) el.textContent = `${trendWindow} range: ${evMin.toFixed(1)} – ${evMax.toFixed(1)}`;
      }
    } else if (evTrendEl) {
      evTrendEl.innerHTML = "—";
      const el = document.getElementById("valuation-ev-range");
      if (el) el.textContent = `${trendWindow} range: —`;
    }
    initValuationCandleTooltips();
  }

  function populateValuationSection(records, marketData, sharesOutstanding) {
    // Header P/E & P/B (current + 52w): same logic as valuation section — no extra backend
    const pePbSummary = computeHeaderPEPB(records, marketData, sharesOutstanding);
    updateHeaderPEPB(pePbSummary);

    const marketCapVND = getCurrentMarketCapVND(marketData, sharesOutstanding);

    // P/E (trailing): Market Cap / Net Income T4Q
    const pe = calculatePE(records || [], marketCapVND);
    document.getElementById("valuation-pe-value").textContent =
      pe != null && !isNaN(pe) ? pe.toFixed(1) : "—";
    document.getElementById("valuation-pe-range").textContent = "5Y range: —";
    document.getElementById("valuation-pe-industry").textContent = "Industry: —";

    // P/B: Market Cap / Equity
    const pb = calculatePB(records || [], marketCapVND);
    document.getElementById("valuation-pb-value").textContent =
      pb != null && !isNaN(pb) ? pb.toFixed(2) : "—";
    document.getElementById("valuation-pb-range").textContent = "5Y range: —";
    document.getElementById("valuation-pb-industry").textContent = "Industry: —";

    // EV/EBITDA: (Market Cap + Net Debt) / EBITDA; EBITDA = PBT + Interest add-back + Depreciation (actual / normalized / conservative per earnings mode)
    const evEbitda = calculateEVEBITDA(records || [], marketCapVND);
    document.getElementById("valuation-ev-value").textContent =
      evEbitda != null && !isNaN(evEbitda) ? evEbitda.toFixed(1) : "—";
    document.getElementById("valuation-ev-range").textContent = "5Y range: —";
    document.getElementById("valuation-ev-industry").textContent = "Industry: —";

    // P/E and P/B trend: annual by default; grey out "By quarter" when company has no quarterly data
    const hasQuarterly = hasQuarterlyFinancialData(records || []);
    const controlsEl = document.getElementById("valuation-trend-controls");
    if (controlsEl) {
      controlsEl.style.display = "flex";
      const annualBtn = controlsEl.querySelector('.valuation-trend-mode-btn[data-mode="annual"]');
      const quarterBtn = controlsEl.querySelector('.valuation-trend-mode-btn[data-mode="quarterly"]');
      if (annualBtn) annualBtn.classList.toggle("active", currentValuationTrendMode === "annual");
      if (quarterBtn) {
        quarterBtn.classList.toggle("active", currentValuationTrendMode === "quarterly" && hasQuarterly);
        if (hasQuarterly) {
          quarterBtn.classList.remove("valuation-trend-mode-btn--disabled");
          quarterBtn.setAttribute("aria-disabled", "false");
        } else {
          quarterBtn.classList.add("valuation-trend-mode-btn--disabled");
          quarterBtn.setAttribute("aria-disabled", "true");
        }
      }
    }
    refreshValuationTrendFromCurrent();
  }

  function populateDashboard(records, symbol, marketData, sharesOutstanding, companyName, sectorIndustry, peers, peersNote) {
    // New target company → clear cached peer valuations and full data
    Object.keys(peerValuationSummaryBySymbol).forEach((k) => { delete peerValuationSummaryBySymbol[k]; });
    Object.keys(peerValuationDataBySymbol).forEach((k) => { delete peerValuationDataBySymbol[k]; });
    peerValFetchedSymbols.clear();
    updateStockHeader(symbol, marketData, sharesOutstanding, companyName, sectorIndustry);
    
    // Filter records by current timeframe
    const filtered = filterByTimeframe(records, currentTimeframe);
    
    populateQualitySection(filtered);
    populateGrowthSection(filtered);
    populateValuationSection(records, marketData, sharesOutstanding);
    populatePeersSection(peers || [], peersNote ?? currentPeersNote ?? null);
    populateFinancialsSection(records);
    showDashboard();
  }

  /** Format market cap (VND) for display (e.g. "1.2 T" or "450 B"). */
  function formatMarketCapVND(value) {
    if (value == null || isNaN(value)) return "—";
    const v = Number(value);
    if (v >= 1e12) return (v / 1e12).toFixed(2) + " T";
    if (v >= 1e9) return (v / 1e9).toFixed(2) + " B";
    if (v >= 1e6) return (v / 1e6).toFixed(2) + " M";
    return v.toLocaleString();
  }

  // In-memory cache of peer valuations so they persist when switching ICB/Broad view
  const peerValuationSummaryBySymbol = {};
  const peerValFetchedSymbols = new Set();
  /** Full peer data (records, market_data, shares_outstanding) for analysis. Access via window.appPeerValuationData */
  const peerValuationDataBySymbol = {};

  const FINANCIALS_BALANCE_SHEET = [
    "Equity", "Liability", "Cash And Equivalent", "Cash Investment", "Long Term Investments",
    "Interest Bearing Debt Short Term", "Interest Bearing Debt Long Term"
  ];
  const FINANCIALS_INCOME_STATEMENT = [
    "Revenue", "Operating Income", "Financial Income", "Profit Before Tax", "Interest Expense",
    "Financial Expense", "Net Income", "Depreciation Expense",
    "Revenue T4Q", "Net Income T4Q", "Net Income (normalized)", "Net Income (conservative)",
    "ROE", "ROIC", "Net Profit Margin", "Revenue YoY Growth", "Net Income YoY Growth"
  ];
  const FINANCIALS_CASHFLOW = [
    "Depreciation Expense"
  ];
  const FINANCIALS_PERCENT_KEYS = new Set([
    "ROE", "ROIC", "Net Profit Margin", "Revenue YoY Growth", "Net Income YoY Growth",
    "ROE (Q)", "ROIC (Q)", "Net Profit Margin (Q)", "Revenue YoY Growth (Q)", "Net Income YoY Growth (Q)"
  ]);

  function populateFinancialsSection(records) {
    const stickyHeader = document.getElementById("financials-sticky-header");
    const placeholderEl = document.getElementById("financials-placeholder");
    const tablesScroll = document.getElementById("financials-scroll-container");
    const balanceEl = document.getElementById("financials-balance-sheet");
    const incomeEl = document.getElementById("financials-income-statement");
    const cashflowEl = document.getElementById("financials-cashflow");
    if (!stickyHeader || !placeholderEl || !tablesScroll || !balanceEl || !incomeEl || !cashflowEl) return;

    if (!records || records.length === 0) {
      stickyHeader.style.display = "none";
      placeholderEl.style.display = "block";
      placeholderEl.textContent = "Financial statements coming soon...";
      return;
    }

    const escapeHtml = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    const formatCell = (val, key) => {
      if (val == null || (typeof val === "number" && isNaN(val))) return "—";
      if (FINANCIALS_PERCENT_KEYS.has(key)) return formatPercent(val);
      return formatFinancial(val);
    };

    const isQuarterly = currentFinancialsViewMode === "quarterly";
    const periodFilter = (p) => {
      const s = String(p || "");
      if (isQuarterly) return /-Q[1-4]$/i.test(s);
      return s.endsWith("-FY");
    };
    let filteredRecords = records.filter((r) => r.Period != null && periodFilter(r.Period));
    if (filteredRecords.length === 0) {
      const altFilter = (p) => {
        const s = String(p || "");
        if (isQuarterly) return s.endsWith("-FY");
        return /-Q[1-4]$/i.test(s);
      };
      filteredRecords = records.filter((r) => r.Period != null && altFilter(r.Period));
    }
    const sortedRecords = [...filteredRecords].sort((a, b) => {
      const pa = String(a.Period);
      const pb = String(b.Period);
      const yearA = parseInt(pa.match(/^(\d{4})/)?.[1] || "0", 10);
      const yearB = parseInt(pb.match(/^(\d{4})/)?.[1] || "0", 10);
      if (yearA !== yearB) return yearA - yearB;
      if (isQuarterly) {
        const qA = parseInt(pa.match(/-Q([1-4])$/i)?.[1] || "0", 10);
        const qB = parseInt(pb.match(/-Q([1-4])$/i)?.[1] || "0", 10);
        return qA - qB;
      }
      return pa.localeCompare(pb);
    });

    const periods = [...new Set(sortedRecords.map((r) => r.Period))].slice(0, 20);
    const byPeriod = {};
    sortedRecords.forEach((r) => { byPeriod[r.Period] = r; });

    const periodHeaderEl = document.getElementById("financials-period-header");
    if (periodHeaderEl) {
      let ph = '<table class="financials-table"><thead><tr><th>Metric</th>';
      periods.forEach((p) => { ph += `<th>${escapeHtml(p)}</th>`; });
      ph += "</tr></thead></table>";
      periodHeaderEl.innerHTML = ph;
    }

    function renderStatement(container, title, metricKeys) {
      const available = metricKeys.filter((k) => sortedRecords.some((r) => r[k] != null && !isNaN(r[k])));
      if (available.length === 0) {
        container.innerHTML = "";
        return;
      }
      let html = `<h4 class="financials-statement-title">${escapeHtml(title)}</h4>`;
      html += '<table class="financials-table"><tbody>';
      available.forEach((key) => {
        html += `<tr><td class="financials-metric-name">${escapeHtml(key)}</td>`;
        periods.forEach((p) => {
          const r = byPeriod[p];
          const val = r ? r[key] : null;
          html += `<td class="financials-metric-value">${escapeHtml(formatCell(val, key))}</td>`;
        });
        html += "</tr>";
      });
      html += "</tbody></table>";
      container.innerHTML = html;
    }

    renderStatement(balanceEl, "Balance Sheet", FINANCIALS_BALANCE_SHEET);
    renderStatement(incomeEl, "Income Statement", FINANCIALS_INCOME_STATEMENT);
    renderStatement(cashflowEl, "Cash Flow Statement", FINANCIALS_CASHFLOW);

    const periodScroll = document.getElementById("financials-period-scroll");
    function scrollFinancialsToRight() {
      const scrollEl = periodScroll || tablesScroll;
      const maxScroll = scrollEl.scrollWidth - scrollEl.clientWidth;
      if (maxScroll > 0) {
        const pos = maxScroll;
        if (periodScroll) periodScroll.scrollLeft = pos;
        tablesScroll.scrollLeft = pos;
      }
    }

    const hasAny = balanceEl.innerHTML || incomeEl.innerHTML || cashflowEl.innerHTML;
    stickyHeader.style.display = hasAny ? "block" : "none";
    tablesScroll.style.display = hasAny ? "block" : "none";
    placeholderEl.style.display = hasAny ? "none" : "block";
    if (hasAny) {
      scrollFinancialsToRight();
      requestAnimationFrame(scrollFinancialsToRight);
      setTimeout(scrollFinancialsToRight, 50);
    }

    document.querySelectorAll(".financials-view-btn").forEach((btn) => {
      const isActive = btn.getAttribute("data-mode") === currentFinancialsViewMode;
      btn.classList.toggle("active", isActive);
      btn.setAttribute("aria-pressed", isActive ? "true" : "false");
    });
  }

  function populatePeersSection(peers, peersNote) {
    const container = document.getElementById("tab-peers");
    if (!container) return;
    if (!peers || peers.length === 0) {
      const hasSymbol = !!(currentSymbol && currentSymbol.trim());
      const btnHtml = hasSymbol
        ? '<button type="button" class="fetch-peers-tab-btn" id="fetch-peers-tab-btn">Fetch peers</button>'
        : "";
      container.innerHTML = `<div class="peers-empty-wrap"><p class="placeholder">No peer data. Run analysis with live API to see industry peers.</p>${btnHtml}</div>`;
      const btn = document.getElementById("fetch-peers-tab-btn");
      if (btn) btn.addEventListener("click", performFetchPeers);
      return;
    }
    const escapeHtml = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    const peersToShow = getPeersForModal();
    const icbActive = currentPeerFilterMode === "icb";
    const broadActive = currentPeerFilterMode === "broad";
    const allActive = currentPeerFilterMode === "all";
    const industryName = (currentSectorIndustry || "—").trim();
    const toolbarHtml = `<div class="peers-toolbar">
      <span class="peers-industry-label">ICB industry:</span>
      <span class="peers-industry-name">${escapeHtml(industryName)}</span>
      <span class="peers-view-label">View:</span>
      <button type="button" class="peers-view-btn ${allActive ? "active" : ""}" data-mode="all" aria-pressed="${allActive}">All</button>
      <button type="button" class="peers-view-btn ${icbActive ? "active" : ""}" data-mode="icb" aria-pressed="${icbActive}">ICB</button>
      <button type="button" class="peers-view-btn ${broadActive ? "active" : ""}" data-mode="broad" aria-pressed="${broadActive}">Broad sector</button>
    </div>`;
    const rows = peersToShow.map((p) => {
      const name = (p.company_name || p.symbol || "—").trim();
      const cap = formatMarketCapVND(p.market_cap);
      const sector = (p.sector_industry || "—").trim() || "—";
      const ours = p.is_our_company ? " <span class=\"peer-badge-ours\">(Our company)</span>" : "";
      return `<tr class="${p.is_our_company ? "peer-row-ours" : ""}">
        <td>${escapeHtml(p.symbol)}${ours}</td>
        <td>${escapeHtml(name)}</td>
        <td class="peer-sector">${escapeHtml(sector)}</td>
        <td class="peer-cap">${escapeHtml(cap)}</td>
        <td>${p.rank != null ? escapeHtml(String(p.rank)) : "—"}</td>
      </tr>`;
    }).join("");
    const noteHtml = peersNote ? `<p class="peers-note">${escapeHtml(peersNote)}</p>` : "";
    container.innerHTML =
      toolbarHtml +
      noteHtml +
      '<div class="peers-table-wrap">' +
      '<table class="peers-table">' +
      '<thead><tr><th>Symbol</th><th>Company</th><th>ICB industry</th><th>Market cap (VND)</th><th>Rank</th></tr></thead>' +
      '<tbody>' + rows + "</tbody>" +
      "</table></div>";
    container.querySelectorAll(".peers-view-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const mode = btn.getAttribute("data-mode");
        if (mode === "icb" || mode === "broad" || mode === "all") {
          currentPeerFilterMode = mode;
          populatePeersSection(currentPeers, currentPeersNote);
          const peerModalEl = document.getElementById("peer-analysis-modal");
          if (peerModalEl && peerModalEl.classList.contains("peer-analysis-modal--open")) {
            renderPeerAnalysisModalContent();
          }
        }
      });
    });
  }

  function normalizeSector(s) {
    if (s == null || typeof s !== "string") return "";
    return s.trim().replace(/\s*[·\-–—]\s*/g, " · ").trim();
  }

  function getPeersForModal() {
    if (!currentPeers || currentPeers.length === 0) return [];
    if (currentPeerFilterMode === "broad" || currentPeerFilterMode === "all") return currentPeers;
    const sector = normalizeSector(currentSectorIndustry);
    if (!sector) return currentPeers;
    const hasAnySector = currentPeers.some((p) => (p.sector_industry || "").trim() !== "");
    if (!hasAnySector) return currentPeers;
    return currentPeers.filter((p) => p.is_our_company || normalizeSector(p.sector_industry) === sector);
  }

  /** ICB peers only (sector-filtered). Used for combined fetch. */
  function getICBPeers() {
    if (!currentPeers || currentPeers.length === 0) return [];
    const sector = normalizeSector(currentSectorIndustry);
    if (!sector) return currentPeers;
    const hasAnySector = currentPeers.some((p) => (p.sector_industry || "").trim() !== "");
    if (!hasAnySector) return currentPeers;
    return currentPeers.filter((p) => p.is_our_company || normalizeSector(p.sector_industry) === sector);
  }

  /** Return symbols for the current scope (around target or top 5). MECE with scopeFiltered display logic. */
  function getScopeFilteredSymbols(peerList, scopeMode) {
    if (!peerList || peerList.length === 0) return [];
    const num = (v) => (v != null && !isNaN(Number(v)) ? Number(v) : null);
    const getCap = (p) => {
      const n = num(p.market_cap);
      if (n != null) return n;
      return -Infinity;
    };
    const sorted = [...peerList].sort((a, b) => getCap(b) - getCap(a));
    const ourIdx = sorted.findIndex((p) => p.is_our_company);
    let indices = new Set();
    const addAround = () => {
      if (ourIdx >= 0) {
        if (ourIdx === 0) {
          [0, 1, 2, 3, 4].forEach((i) => { if (i < sorted.length) indices.add(i); });
        } else if (ourIdx === sorted.length - 1) {
          [ourIdx - 4, ourIdx - 3, ourIdx - 2, ourIdx - 1, ourIdx].forEach((i) => { if (i >= 0) indices.add(i); });
        } else {
          [ourIdx - 2, ourIdx - 1, ourIdx, ourIdx + 1, ourIdx + 2].forEach((i) => { if (i >= 0 && i < sorted.length) indices.add(i); });
        }
      }
      if (indices.size === 0) {
        [0, 1, 2, 3, 4].forEach((i) => { if (i < sorted.length) indices.add(i); });
      }
    };
    const addTop5 = () => {
      [0, 1, 2, 3, 4].forEach((i) => { if (i < sorted.length) indices.add(i); });
    };
    if (scopeMode === "around") {
      addAround();
    } else if (scopeMode === "both") {
      addTop5();
      addAround();
    } else {
      addTop5();
    }
    return [...indices].sort((a, b) => a - b).map((i) => (sorted[i].symbol || "").trim().toUpperCase()).filter(Boolean);
  }

  /** Return peer objects for the given scope. Used when view is "all" to merge ICB + Broader. */
  function getScopeFilteredPeers(peerList, scopeMode) {
    if (!peerList || peerList.length === 0) return [];
    const num = (v) => (v != null && !isNaN(Number(v)) ? Number(v) : null);
    const getCap = (p) => {
      const n = num(p.market_cap);
      if (n != null) return n;
      return -Infinity;
    };
    const sorted = [...peerList].sort((a, b) => getCap(b) - getCap(a));
    const ourIdx = sorted.findIndex((p) => p.is_our_company);
    let indices = new Set();
    const addAround = () => {
      if (ourIdx >= 0) {
        if (ourIdx === 0) {
          [0, 1, 2, 3, 4].forEach((i) => { if (i < sorted.length) indices.add(i); });
        } else if (ourIdx === sorted.length - 1) {
          [ourIdx - 4, ourIdx - 3, ourIdx - 2, ourIdx - 1, ourIdx].forEach((i) => { if (i >= 0) indices.add(i); });
        } else {
          [ourIdx - 2, ourIdx - 1, ourIdx, ourIdx + 1, ourIdx + 2].forEach((i) => { if (i >= 0 && i < sorted.length) indices.add(i); });
        }
      }
      if (indices.size === 0) {
        [0, 1, 2, 3, 4].forEach((i) => { if (i < sorted.length) indices.add(i); });
      }
    };
    const addTop5 = () => {
      [0, 1, 2, 3, 4].forEach((i) => { if (i < sorted.length) indices.add(i); });
    };
    if (scopeMode === "around") {
      addAround();
    } else if (scopeMode === "both") {
      addTop5();
      addAround();
    } else {
      addTop5();
    }
    return [...indices].sort((a, b) => a - b).map((i) => sorted[i]);
  }

  function renderPeerAnalysisModalContent() {
    const colAdjacent = document.getElementById("peer-analysis-col-adjacent");
    const colTop5 = document.getElementById("peer-analysis-col-top5");
    if (!colAdjacent || !colTop5) return;
    const peersToShow = getPeersForModal();
    const escapeHtml = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    const m = currentPeerValMetric;
    const lowKey = m === "pe" ? "peLow" : m === "pb" ? "pbLow" : "evLow";
    const highKey = m === "pe" ? "peHigh" : m === "pb" ? "pbHigh" : "evHigh";
    const currentKey = m === "pe" ? "peCurrent" : m === "pb" ? "pbCurrent" : "evCurrent";
    const formatVal = m === "pb" ? (v) => (v != null ? v.toFixed(2) : "—") : (v) => (v != null ? v.toFixed(1) : "—");
    const peerRow = (p, oursLabel, globalMin, globalMax, globalAvg, isSameICB) => {
      const name = (p.company_name || p.symbol || "—").trim();
      const sym = (p.symbol || "").trim().toUpperCase();
      const capVal = (peerValuationSummaryBySymbol[sym] || {}).market_cap ?? p.market_cap;
      const cap = formatMarketCapVND(capVal);
      const title = escapeHtml(name || sym || "");
      const cached = peerValuationSummaryBySymbol[sym] || {};
      const low = cached[lowKey];
      const high = cached[highKey];
      const current = cached[currentKey];
      const hasRange = low != null && high != null && !isNaN(low) && !isNaN(high);
      const hasScale = globalMin != null && globalMax != null && globalMax > globalMin;
      let rangeLeft = 0, rangeWidth = 100, fillWidthPct = 0, tickerPct = 50;
      if (hasScale && hasRange) {
        const span = globalMax - globalMin;
        rangeLeft = Math.max(0, Math.min(100, ((low - globalMin) / span) * 100));
        rangeWidth = Math.max(2, Math.min(100 - rangeLeft, ((high - low) / span) * 100));
        const rangeSpan = high - low;
        fillWidthPct = rangeSpan > 0 && current != null && !isNaN(current)
          ? Math.max(0, Math.min(rangeWidth, ((current - low) / rangeSpan) * rangeWidth))
          : 0;
        tickerPct = current != null && !isNaN(current)
          ? Math.max(0, Math.min(100, ((current - globalMin) / span) * 100))
          : 50;
      }
      const barVisible = hasRange && hasScale;
      let avgPct = null;
      if (hasScale && globalAvg != null && !isNaN(globalAvg)) {
        const span = globalMax - globalMin;
        avgPct = Math.max(0, Math.min(100, ((globalAvg - globalMin) / span) * 100));
      }
      const avgLineHtml = avgPct != null ? `<div class="peer-val-bar-avg" style="left: ${avgPct}%" title="Sector median"></div>` : "";
      const curFmt = current != null && !isNaN(current) ? formatVal(current) : "—";
      const tooltip52w = hasRange ? `52w: ${formatVal(low)} – ${formatVal(high)}` : "";
      const barHtml = barVisible
        ? `<span class="peer-val-bar-wrap" title="${escapeHtml(tooltip52w)}">
            <div class="peer-val-bar" role="img" aria-label="${m === "pe" ? "P/E" : m === "pb" ? "P/B" : "EV/EBITDA"} 52w range">
              <div class="peer-val-bar-track">
                <div class="peer-val-bar-range" style="left: ${rangeLeft}%; width: ${rangeWidth}%"></div>
                <div class="peer-val-bar-fill" style="left: ${rangeLeft}%; width: ${fillWidthPct}%"></div>
                ${avgLineHtml}
                <div class="peer-val-bar-ticker" style="left: ${tickerPct}%"></div>
              </div>
            </div>
          </span>`
        : `<span class="peer-val-chip peer-val-no-data">${m === "pe" ? "P/E" : m === "pb" ? "P/B" : "EV/EBITDA"}: ${escapeHtml(cached[m] != null ? cached[m] : "—")}</span>`;
      const curDisplay = barVisible ? curFmt : (cached[m] != null ? cached[m] : "—");
      const icbClass = isSameICB ? " peer-analysis-row-icb" : "";
      return `<div class="peer-analysis-row ${p.is_our_company ? "peer-analysis-row-ours" : ""}${icbClass}" data-symbol="${escapeHtml(sym)}">
        <span class="peer-analysis-symbol-wrap">
          <span class="peer-analysis-symbol">${escapeHtml(p.symbol)}${oursLabel}</span>
          <span class="peer-analysis-symbol-info" role="img" aria-label="${title}">
            <span class="peer-analysis-symbol-info-icon">i</span>
            <span class="peer-analysis-symbol-tooltip">${title}</span>
          </span>
        </span>
        <div class="peer-analysis-main">
          <span class="peer-analysis-multiples">${barHtml}</span>
          <span class="peer-val-current">${escapeHtml(curDisplay)}</span>
        </div>
        <span class="peer-analysis-cap">${escapeHtml(cap)}</span>
      </div>`;
    };
    if (peersToShow.length === 0) {
      colAdjacent.innerHTML = "<p class=\"peer-analysis-empty\">No peer data. Run analysis with live API to see industry peers.</p>";
      colTop5.innerHTML = "<p class=\"peer-analysis-empty\">No peer data.</p>";
      const postFetchEl = document.getElementById("peer-analysis-post-fetch");
      const colTitleSimpleEl = document.getElementById("peer-analysis-col-title-simple");
      if (postFetchEl) postFetchEl.style.display = "none";
      if (colTitleSimpleEl) colTitleSimpleEl.style.display = "none";
    } else {
      const hasFetched = peerValFetchedSymbols.size > 0;
      const postFetchEl = document.getElementById("peer-analysis-post-fetch");
      const colTitleEl = document.getElementById("peer-analysis-col-title");
      const colTitleSimpleEl = document.getElementById("peer-analysis-col-title-simple");
      if (postFetchEl) postFetchEl.style.display = hasFetched ? "block" : "none";
      if (colTitleSimpleEl) colTitleSimpleEl.style.display = hasFetched ? "none" : "block";
      const num = (v) => (v != null && !isNaN(Number(v)) ? Number(v) : null);
      const getVal = (p) => {
        const sym = (p.symbol || "").trim().toUpperCase();
        const c = peerValuationSummaryBySymbol[sym];
        const cur = c ? c[currentKey] : null;
        return cur != null && !isNaN(cur) ? cur : Infinity;
      };
      const getCap = (p) => {
        const sym = (p.symbol || "").trim().toUpperCase();
        const cached = peerValuationSummaryBySymbol[sym];
        const capVal = (cached && cached.market_cap != null) ? cached.market_cap : p.market_cap;
        const n = num(capVal);
        if (n != null) return n;
        return -Infinity;
      };
      const sortedByCap = [...peersToShow].sort((a, b) => getCap(b) - getCap(a));
      const ourIdxByCap = sortedByCap.findIndex((p) => p.is_our_company);
      let scopeFiltered = peersToShow;
      if (currentPeerFilterMode === "all" && currentPeerScopeMode === "both") {
        // All view + Both scope: union of ICB (top5+around) and Broader (top5+around)
        const icbPeers = getICBPeers();
        const broadPeers = currentPeers || [];
        const icbSyms = new Set(getScopeFilteredSymbols(icbPeers, "both"));
        const broadSyms = new Set(getScopeFilteredSymbols(broadPeers, "both"));
        const allSyms = new Set([...icbSyms, ...broadSyms]);
        // Build from currentPeers by symbol set — no ICB-first ordering; sort will determine final order
        scopeFiltered = (broadPeers || []).filter((p) => {
          const s = (p.symbol || "").trim().toUpperCase();
          return s && allSyms.has(s);
        });
      } else if (currentPeerScopeMode === "around") {
        const indices = new Set();
        if (ourIdxByCap >= 0) {
          if (ourIdxByCap === 0) {
            [0, 1, 2, 3, 4].forEach((i) => { if (i < sortedByCap.length) indices.add(i); });
          } else if (ourIdxByCap === sortedByCap.length - 1) {
            [ourIdxByCap - 4, ourIdxByCap - 3, ourIdxByCap - 2, ourIdxByCap - 1, ourIdxByCap].forEach((i) => { if (i >= 0) indices.add(i); });
          } else {
            [ourIdxByCap - 2, ourIdxByCap - 1, ourIdxByCap, ourIdxByCap + 1, ourIdxByCap + 2].forEach((i) => { if (i >= 0 && i < sortedByCap.length) indices.add(i); });
          }
        }
        scopeFiltered = indices.size > 0 ? [...indices].sort((a, b) => a - b).map((i) => sortedByCap[i]) : sortedByCap.slice(0, 5);
      } else if (currentPeerScopeMode === "both") {
        const indices = new Set();
        [0, 1, 2, 3, 4].forEach((i) => { if (i < sortedByCap.length) indices.add(i); });
        if (ourIdxByCap >= 0) {
          if (ourIdxByCap === 0) {
            [0, 1, 2, 3, 4].forEach((i) => { if (i < sortedByCap.length) indices.add(i); });
          } else if (ourIdxByCap === sortedByCap.length - 1) {
            [ourIdxByCap - 4, ourIdxByCap - 3, ourIdxByCap - 2, ourIdxByCap - 1, ourIdxByCap].forEach((i) => { if (i >= 0) indices.add(i); });
          } else {
            [ourIdxByCap - 2, ourIdxByCap - 1, ourIdxByCap, ourIdxByCap + 1, ourIdxByCap + 2].forEach((i) => { if (i >= 0 && i < sortedByCap.length) indices.add(i); });
          }
        }
        scopeFiltered = [...indices].sort((a, b) => a - b).map((i) => sortedByCap[i]);
      } else {
        scopeFiltered = sortedByCap.slice(0, 5);
      }
      // Fetch uses getScopeFilteredSymbols (same logic) → display = scopeFiltered only (MECE)
      let combinedForDisplay = scopeFiltered;
      // "Have data only" only applies after we have fetched; before fetch, show all peers in scope
      if (hasFetched && currentPeerHaveDataOnly) {
        combinedForDisplay = combinedForDisplay.filter((p) => {
          const sym = (p.symbol || "").trim().toUpperCase();
          return sym && peerValuationSummaryBySymbol[sym];
        });
      }
      const targetInTop5 = ourIdxByCap >= 0 && ourIdxByCap < 5;
      const symStr = (p) => (p.symbol || "").trim().toUpperCase();
      const sorted = [...combinedForDisplay].sort((a, b) => {
        if (currentPeerSortMode === "valuation") {
          const va = getVal(a);
          const vb = getVal(b);
          const diff = va - vb;
          return diff !== 0 ? diff : symStr(a).localeCompare(symStr(b));
        }
        const diff = getCap(b) - getCap(a);
        return diff !== 0 ? diff : symStr(a).localeCompare(symStr(b));
      });
      const displayedSyms = [...new Set([
        ...sorted.map((p) => (p.symbol || "").trim().toUpperCase()),
        (currentSymbol || "").trim().toUpperCase()
      ].filter(Boolean))];
      let globalMin = null, globalMax = null;
      displayedSyms.forEach((sym) => {
        const c = peerValuationSummaryBySymbol[sym];
        if (!c) return;
        const l = c[lowKey], h = c[highKey];
        if (l != null && !isNaN(l)) globalMin = globalMin == null ? l : Math.min(globalMin, l);
        if (h != null && !isNaN(h)) globalMax = globalMax == null ? h : Math.max(globalMax, h);
      });
      if (globalMin != null && globalMax != null && globalMax <= globalMin) globalMax = globalMin + 0.01;
      let globalAvg = null;
      const currentVals = [];
      displayedSyms.forEach((sym) => {
        const c = peerValuationSummaryBySymbol[sym];
        if (!c) return;
        const cur = c[currentKey];
        if (cur != null && !isNaN(cur)) currentVals.push(cur);
      });
      if (currentVals.length > 0) globalAvg = currentVals.reduce((a, b) => a + b, 0) / currentVals.length;
      const scaleWrapEl = document.getElementById("peer-val-scale-wrap");
      const scaleMinEl = document.getElementById("peer-val-scale-min");
      const scaleMaxEl = document.getElementById("peer-val-scale-max");
      const scaleAvgEl = document.getElementById("peer-val-scale-avg");
      if (scaleWrapEl && scaleMinEl && scaleMaxEl && scaleAvgEl) {
        scaleWrapEl.style.display = "flex";
        scaleMinEl.textContent = globalMin != null ? formatVal(globalMin) : "—";
        scaleMaxEl.textContent = globalMax != null ? formatVal(globalMax) : "—";
        scaleAvgEl.textContent = globalAvg != null ? formatVal(globalAvg) : "—";
      }
      if (colTitleEl) {
        colTitleEl.style.display = hasFetched ? "none" : "";
        if (!hasFetched) colTitleEl.textContent = "Peers";
      }
      const targetSector = normalizeSector(currentSectorIndustry);
      colAdjacent.innerHTML = sorted.map((p) => {
        const sym = (p.symbol || "").trim().toUpperCase();
        const isSameICB = !p.is_our_company && targetSector && normalizeSector(p.sector_industry) === targetSector;
        return peerRow(p, "", globalMin, globalMax, globalAvg, isSameICB);
      }).join("");
      colTop5.innerHTML = "";
    }
  }

  function showNeedPeersModal() {
    const modal = document.getElementById("need-peers-modal");
    if (modal) {
      modal.classList.add("need-peers-modal--open");
      modal.setAttribute("aria-hidden", "false");
    }
  }

  function closeNeedPeersModal() {
    const modal = document.getElementById("need-peers-modal");
    if (modal) {
      modal.classList.remove("need-peers-modal--open");
      modal.setAttribute("aria-hidden", "true");
    }
  }

  function openPeerAnalysisModal() {
    if (currentSymbol && (!currentPeers || currentPeers.length === 0)) {
      showNeedPeersModal();
      return;
    }
    const modal = document.getElementById("peer-analysis-modal");
    if (!modal) return;
    modal.querySelectorAll(".peer-analysis-mode-btn").forEach((b) => {
      const isActive = b.getAttribute("data-mode") === currentPeerFilterMode;
      b.classList.toggle("active", isActive);
      b.setAttribute("aria-pressed", isActive ? "true" : "false");
    });
    modal.querySelectorAll(".peer-analysis-metric-btn").forEach((b) => {
      const isActive = b.getAttribute("data-metric") === currentPeerValMetric;
      b.classList.toggle("active", isActive);
      b.setAttribute("aria-pressed", isActive ? "true" : "false");
    });
    modal.querySelectorAll(".peer-val-sort-btn").forEach((b) => {
      const isActive = b.getAttribute("data-sort") === currentPeerSortMode;
      b.classList.toggle("active", isActive);
      b.setAttribute("aria-pressed", isActive ? "true" : "false");
    });
    modal.querySelectorAll(".peer-val-scope-btn").forEach((b) => {
      const isActive = b.getAttribute("data-scope") === currentPeerScopeMode;
      b.classList.toggle("active", isActive);
      b.setAttribute("aria-pressed", isActive ? "true" : "false");
    });
    const haveDataBtn = document.getElementById("peer-val-have-data-btn");
    if (haveDataBtn) {
      haveDataBtn.classList.toggle("active", currentPeerHaveDataOnly);
      haveDataBtn.setAttribute("aria-pressed", currentPeerHaveDataOnly ? "true" : "false");
    }
    renderPeerAnalysisModalContent();
    modal.classList.add("peer-analysis-modal--open");
    modal.setAttribute("aria-hidden", "false");
  }

  function closePeerAnalysisModal() {
    const modal = document.getElementById("peer-analysis-modal");
    const fetchChoiceEl = document.getElementById("peer-valuation-fetch-choice");
    if (fetchChoiceEl) fetchChoiceEl.style.display = "none";
    if (modal) {
      modal.classList.remove("peer-analysis-modal--open");
      modal.setAttribute("aria-hidden", "true");
    }
  }

  // Tab switching
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tab = btn.getAttribute("data-tab");
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-pane").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(`tab-${tab}`).classList.add("active");
      if (tab === "financials") {
        requestAnimationFrame(() => {
          const periodScroll = document.getElementById("financials-period-scroll");
          const tablesScroll = document.getElementById("financials-scroll-container");
          const scrollEl = periodScroll || tablesScroll;
          if (scrollEl) {
            const maxScroll = scrollEl.scrollWidth - scrollEl.clientWidth;
            if (maxScroll > 0) {
              if (periodScroll) periodScroll.scrollLeft = maxScroll;
              if (tablesScroll) tablesScroll.scrollLeft = maxScroll;
            }
          }
        });
      }
    });
  });

  // Sync horizontal scroll: period header (with scrollbar) drives body tables
  (function initFinancialsScrollSync() {
    const periodScroll = document.getElementById("financials-period-scroll");
    const tablesScroll = document.getElementById("financials-scroll-container");
    if (periodScroll && tablesScroll) {
      periodScroll.addEventListener("scroll", () => {
        tablesScroll.scrollLeft = periodScroll.scrollLeft;
      });
    }
  })();

  // Growth chart toggles
  ["toggle-revenue", "toggle-net-income", "toggle-net-income-normalized", "toggle-net-income-conservative"].forEach((id) => {
    const toggle = document.getElementById(id);
    if (toggle) {
      toggle.addEventListener("change", () => {
        if (currentRecords.length > 0) {
          renderGrowthChart(currentRecords);
        }
      });
    }
  });

  // Valuation trend mode: By year (default) / By quarter (disabled when no quarterly data)
  document.getElementById("valuation-trend-controls")?.addEventListener("click", (e) => {
    const btn = e.target.closest(".valuation-trend-mode-btn");
    if (!btn || !currentRecords.length) return;
    if (btn.classList.contains("valuation-trend-mode-btn--disabled")) return;
    const mode = btn.getAttribute("data-mode");
    if (mode !== "annual" && mode !== "quarterly") return;
    currentValuationTrendMode = mode;
    document.querySelectorAll(".valuation-trend-mode-btn").forEach((b) => {
      b.classList.toggle("active", b.getAttribute("data-mode") === mode);
    });
    refreshValuationTrendFromCurrent();
  });

  // Growth Quality modal — same thresholds as 5 dots: 0–40→red, 41–60→yellow, 61–100→green
  function scoreToHealthClass(pct) {
    if (pct == null || isNaN(pct)) return "growth-quality-breakdown-score--gray";
    if (pct <= 40) return "growth-quality-breakdown-score--red";
    if (pct <= 60) return "growth-quality-breakdown-score--yellow";
    return "growth-quality-breakdown-score--green";
  }

  function buildBreakdownHTML(breakdown, metric) {
    const pgr = breakdown.positiveGrowthRatio || breakdown.positiveYearRatio;
    const s = breakdown.stability;
    const d = breakdown.direction;
    const r = breakdown.resilience;
    if (!pgr || !s || !r) return "";
    const isRevenue = metric === "Revenue";

    const pgrPct = (pgr.ratio * 100);
    const stabPct = (s.stabilityScore * 100);
    const resPct = (r.resilienceScore * 100);
    const resilienceWeightPct = (r.weight * 100).toFixed(0);

    const pgrColor = scoreToHealthClass(pgrPct);
    const stabColor = scoreToHealthClass(stabPct);
    const resColor = scoreToHealthClass(resPct);

    if (isRevenue) {
      return `
      <div class="growth-quality-breakdown-item">
        <div class="growth-quality-breakdown-header">
          <span class="growth-quality-breakdown-name">1. Positive Growth Ratio (40% weight)</span>
          <span class="growth-quality-breakdown-score ${pgrColor}">${pgrPct.toFixed(0)}%</span>
        </div>
        <p class="growth-quality-breakdown-desc">% of valid YoY pairs with positive growth.</p>
        <div class="growth-quality-breakdown-detail">
          ${pgr.positive} / ${pgr.total} years with positive growth
        </div>
      </div>
      <div class="growth-quality-breakdown-item">
        <div class="growth-quality-breakdown-header">
          <span class="growth-quality-breakdown-name">2. Stability (25% weight)</span>
          <span class="growth-quality-breakdown-score ${stabColor}">${stabPct.toFixed(0)}%</span>
        </div>
        <p class="growth-quality-breakdown-desc">Low volatility of valid YoY. CV = std(YoY) / |mean(YoY)|</p>
        <div class="growth-quality-breakdown-detail">
          Mean YoY: ${(s.mean * 100).toFixed(1)}%, Std: ${(s.std * 100).toFixed(1)}%, CV: ${s.cv.toFixed(2)}
        </div>
      </div>
      <div class="growth-quality-breakdown-item">
        <div class="growth-quality-breakdown-header">
          <span class="growth-quality-breakdown-name">3. Resilience (${resilienceWeightPct}% weight)</span>
          <span class="growth-quality-breakdown-score ${resColor}">${resPct.toFixed(0)}%</span>
        </div>
        <p class="growth-quality-breakdown-desc">How bad the worst valid YoY is. Penalty = min(|worst YoY| / 30%, 1).</p>
        <div class="growth-quality-breakdown-detail">
          Worst YoY: ${(r.worstDrawdown * 100).toFixed(1)}%, Penalty: ${(r.downsidePenalty * 100).toFixed(0)}%
        </div>
      </div>
    `;
    }

    const dirPct = (d && d.scoreNorm != null) ? (d.scoreNorm * 100) : 0;
    const dirColor = scoreToHealthClass(dirPct);

    return `
      <div class="growth-quality-breakdown-item">
        <div class="growth-quality-breakdown-header">
          <span class="growth-quality-breakdown-name">1. Positive Growth Ratio (40% weight)</span>
          <span class="growth-quality-breakdown-score ${pgrColor}">${pgrPct.toFixed(0)}%</span>
        </div>
        <p class="growth-quality-breakdown-desc">% of valid YoY pairs with positive growth.</p>
        <div class="growth-quality-breakdown-detail">
          ${pgr.positive} / ${pgr.total} years with positive growth
        </div>
      </div>
      <div class="growth-quality-breakdown-item">
        <div class="growth-quality-breakdown-header">
          <span class="growth-quality-breakdown-name">2. Stability (25% weight)</span>
          <span class="growth-quality-breakdown-score ${stabColor}">${stabPct.toFixed(0)}%</span>
        </div>
        <p class="growth-quality-breakdown-desc">Low volatility of valid YoY. CV = std(YoY) / |mean(YoY)|</p>
        <div class="growth-quality-breakdown-detail">
          Mean YoY: ${(s.mean * 100).toFixed(1)}%, Std: ${(s.std * 100).toFixed(1)}%, CV: ${s.cv.toFixed(2)}
        </div>
      </div>
      <div class="growth-quality-breakdown-item">
        <div class="growth-quality-breakdown-header">
          <span class="growth-quality-breakdown-name">3. Direction (25% weight)</span>
          <span class="growth-quality-breakdown-score ${dirColor}">${dirPct.toFixed(0)}%</span>
        </div>
        <p class="growth-quality-breakdown-desc">Transition scores: +→+ 1.0, −→+ 0.5, −→− −0.5, +→− −1.0. Normalized to [0,1].</p>
        <div class="growth-quality-breakdown-detail">
          Raw mean: ${d.raw.toFixed(2)} → norm: ${(d.scoreNorm * 100).toFixed(0)}% (${d.transitions} transitions)
        </div>
      </div>
      <div class="growth-quality-breakdown-item">
        <div class="growth-quality-breakdown-header">
          <span class="growth-quality-breakdown-name">4. Resilience (10% weight)</span>
          <span class="growth-quality-breakdown-score ${resColor}">${resPct.toFixed(0)}%</span>
        </div>
        <p class="growth-quality-breakdown-desc">How bad the worst valid YoY is. Penalty = min(|worst YoY| / 30%, 1).</p>
        <div class="growth-quality-breakdown-detail">
          Worst YoY: ${(r.worstDrawdown * 100).toFixed(1)}%, Penalty: ${(r.downsidePenalty * 100).toFixed(0)}%
        </div>
      </div>
    `;
  }

  function showGrowthQualityModal(el) {
    const breakdownJson = el.dataset.breakdown;
    const score = el.dataset.score;
    const metric = el.dataset.metric || "";
    const years = el.dataset.years || "";
    if (!breakdownJson || !score) return;

    const modal = document.getElementById("growth-quality-modal");
    const breakdown = JSON.parse(breakdownJson);
    const totalScoreNum = parseFloat(score) || 0;
    const totalScoreEl = document.getElementById("modal-total-score");

    document.getElementById("modal-title").textContent = `Growth Quality — ${metric}${years ? ` (${years}Y)` : ""}`;
    totalScoreEl.textContent = `${score} / 100`;
    totalScoreEl.className = "growth-quality-score-value " + scoreToHealthClass(totalScoreNum);
    document.getElementById("modal-breakdown").innerHTML = buildBreakdownHTML(breakdown, metric);

    modal.classList.add("growth-quality-modal--open");
    modal.setAttribute("aria-hidden", "false");
  }

  function closeGrowthQualityModal() {
    const modal = document.getElementById("growth-quality-modal");
    modal.classList.remove("growth-quality-modal--open");
    modal.setAttribute("aria-hidden", "true");
  }

  document.querySelectorAll(".growth-quality-clickable").forEach((el) => {
    el.addEventListener("click", () => showGrowthQualityModal(el));
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        showGrowthQualityModal(el);
      }
    });
  });

  const modalEl = document.getElementById("growth-quality-modal");
  if (modalEl) {
    modalEl.querySelector(".growth-quality-modal-backdrop")?.addEventListener("click", closeGrowthQualityModal);
    modalEl.querySelector(".growth-quality-modal-close")?.addEventListener("click", closeGrowthQualityModal);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && modalEl.classList.contains("growth-quality-modal--open")) {
        closeGrowthQualityModal();
      }
    });
  }

  document.getElementById("peer-analysis-btn")?.addEventListener("click", openPeerAnalysisModal);
  const peerModalEl = document.getElementById("peer-analysis-modal");
  if (peerModalEl) {
    peerModalEl.querySelector(".peer-analysis-modal-backdrop")?.addEventListener("click", closePeerAnalysisModal);
    peerModalEl.querySelector(".peer-analysis-modal-close")?.addEventListener("click", closePeerAnalysisModal);
    // Single instant tooltip: position with fixed so it's never cut off; no native title (no second delayed tooltip)
    peerModalEl.addEventListener("mouseover", (e) => {
      const trigger = e.target.closest(".peer-analysis-symbol-info");
      if (!trigger) return;
      const tooltip = trigger.querySelector(".peer-analysis-symbol-tooltip");
      if (!tooltip) return;
      const rect = trigger.getBoundingClientRect();
      tooltip.style.left = "0";
      tooltip.style.top = "0";
      tooltip.style.visibility = "visible";
      tooltip.style.opacity = "0";
      const w = tooltip.offsetWidth;
      const h = tooltip.offsetHeight;
      const pad = 8;
      let left = rect.left + rect.width / 2 - w / 2;
      let top = rect.top - h - 4;
      left = Math.max(pad, Math.min(left, window.innerWidth - w - pad));
      if (top < pad) top = rect.bottom + 4;
      top = Math.max(pad, Math.min(top, window.innerHeight - h - pad));
      tooltip.style.left = left + "px";
      tooltip.style.top = top + "px";
      tooltip.style.opacity = "1";
    });
    peerModalEl.addEventListener("mouseout", (e) => {
      const trigger = e.target.closest(".peer-analysis-symbol-info");
      if (!trigger || trigger.contains(e.relatedTarget)) return;
      const tooltip = trigger.querySelector(".peer-analysis-symbol-tooltip");
      if (tooltip) {
        tooltip.style.visibility = "hidden";
        tooltip.style.opacity = "0";
      }
    });
    peerModalEl.querySelectorAll(".peer-analysis-mode-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const mode = btn.getAttribute("data-mode");
        if (mode === "icb" || mode === "broad" || mode === "all") {
          currentPeerFilterMode = mode;
          peerModalEl.querySelectorAll(".peer-analysis-mode-btn").forEach((b) => {
            const isActive = b.getAttribute("data-mode") === mode;
            b.classList.toggle("active", isActive);
            b.setAttribute("aria-pressed", isActive ? "true" : "false");
          });
          const fetchChoiceEl = document.getElementById("peer-valuation-fetch-choice");
          if (fetchChoiceEl) fetchChoiceEl.style.display = "none";
          renderPeerAnalysisModalContent();
        }
      });
    });
    peerModalEl.querySelectorAll(".peer-analysis-metric-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const metric = btn.getAttribute("data-metric");
        if (metric === "pe" || metric === "pb" || metric === "ev") {
          currentPeerValMetric = metric;
          peerModalEl.querySelectorAll(".peer-analysis-metric-btn").forEach((b) => {
            const isActive = b.getAttribute("data-metric") === metric;
            b.classList.toggle("active", isActive);
            b.setAttribute("aria-pressed", isActive ? "true" : "false");
          });
          renderPeerAnalysisModalContent();
        }
      });
    });
    peerModalEl.querySelectorAll(".peer-val-sort-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const sort = btn.getAttribute("data-sort");
        if (sort === "valuation" || sort === "marketcap") {
          currentPeerSortMode = sort;
          peerModalEl.querySelectorAll(".peer-val-sort-btn").forEach((b) => {
            const isActive = b.getAttribute("data-sort") === sort;
            b.classList.toggle("active", isActive);
            b.setAttribute("aria-pressed", isActive ? "true" : "false");
          });
          renderPeerAnalysisModalContent();
        }
      });
    });
    peerModalEl.querySelectorAll(".peer-val-scope-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const scope = btn.getAttribute("data-scope");
        if (scope === "around" || scope === "top5" || scope === "both") {
          currentPeerScopeMode = scope;
          peerModalEl.querySelectorAll(".peer-val-scope-btn").forEach((b) => {
            const isActive = b.getAttribute("data-scope") === scope;
            b.classList.toggle("active", isActive);
            b.setAttribute("aria-pressed", isActive ? "true" : "false");
          });
          renderPeerAnalysisModalContent();
        }
      });
    });
    const haveDataBtn = document.getElementById("peer-val-have-data-btn");
    if (haveDataBtn) {
      haveDataBtn.addEventListener("click", () => {
        currentPeerHaveDataOnly = !currentPeerHaveDataOnly;
        haveDataBtn.classList.toggle("active", currentPeerHaveDataOnly);
        haveDataBtn.setAttribute("aria-pressed", currentPeerHaveDataOnly ? "true" : "false");
        renderPeerAnalysisModalContent();
      });
    }
    (function initPeerValuationButtons() {
      const runPeerValuationsUrl = document.getElementById("analyze-form")?.getAttribute("data-peer-valuations-url") || "/run_peer_valuations";
      const placeholder = document.getElementById("peer-valuation-results-placeholder");
      const tableWrap = document.getElementById("peer-valuation-results-table-wrap");
      const peerName = (sym) => (currentPeers || []).find((p) => (p.symbol || "").toUpperCase() === (sym || "").toUpperCase())?.company_name || sym;
      function getICBPeerSymbols() {
        const sector = normalizeSector(currentSectorIndustry);
        if (!sector || !currentPeers || !currentPeers.length) return [];
        const ourSym = (currentSymbol || "").trim().toUpperCase();
        return [...new Set(
          currentPeers
            .filter((p) => normalizeSector(p.sector_industry) === sector && (p.symbol || "").trim().toUpperCase() !== ourSym)
            .map((p) => (p.symbol || "").trim().toUpperCase())
            .filter(Boolean)
        )];
      }
      async function fetchPeerValuations(symbols, targetSymbol, scope) {
        if (!symbols.length) return;
        targetSymbol = (targetSymbol || currentSymbol || "").trim().toUpperCase();
        scope = (scope || "icb").toLowerCase();
        const uniqueSymbols = [...new Set(symbols.map((s) => (s || "").trim().toUpperCase()).filter(Boolean))];
        const symbolsToFetch = uniqueSymbols.filter((s) => !peerValFetchedSymbols.has(s) && s !== targetSymbol);
        if (!symbolsToFetch.length) {
          // Nothing new to fetch; just re-render using cached valuations
          if (placeholder) {
            placeholder.textContent = "";
            placeholder.style.display = "none";
          }
          renderPeerAnalysisModalContent();
          return;
        }
        const btns = document.querySelectorAll(".peer-analysis-valuation-btn");
        btns.forEach((b) => { b.disabled = true; });
        setFetchStatus("fetching_peer_valuations", "Fetching peer valuations…");
        if (placeholder) {
          placeholder.textContent = "Fetching 52w price and financial data…";
          placeholder.style.display = "block";
        }
        if (tableWrap) tableWrap.style.display = "none";
        const payload = { symbols: symbolsToFetch, target_symbol: targetSymbol, scope };
        const icbSymbols = getICBPeerSymbols();
        if (icbSymbols.length) payload.icb_symbols = icbSymbols;
        if ((scope === "broader" || scope === "all") && currentPeers && currentPeers.length) {
          const market_caps = {};
          currentPeers.forEach((p) => {
            const s = (p.symbol || "").toUpperCase();
            if (s && (p.market_cap != null)) market_caps[s] = Number(p.market_cap);
          });
          if (Object.keys(market_caps).length) payload.market_caps = market_caps;
        }
        try {
          const res = await fetch(runPeerValuationsUrl, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          const json = await res.json();
          const list = json.peer_valuations || [];
          const errs = json.errors || {};
          if (list.length === 0 && Object.keys(errs).length > 0) {
            const errMsg = "Failed: " + Object.values(errs).join("; ");
            if (placeholder) placeholder.textContent = errMsg;
            setFetchStatus("error", errMsg);
            return;
          }
          // Map valuations back into existing peer rows. Store full data for analysis; use same valuation logic as target.
          list.forEach((item) => {
            const rawRecords = item.records || [];
            const md = item.market_data || [];
            const shares = item.shares_outstanding;
            const sym = (item.symbol || "").trim().toUpperCase();
            if (!sym) return;
            // Enrich records with EBITDA etc. (same as target company) before computing valuation
            const enrichedRecords = enrichRecordsWithNormalizedEarnings(rawRecords);
            // Store full data for user analysis (enriched records, market_data, shares_outstanding; same format as target)
            peerValuationDataBySymbol[sym] = {
              records: enrichedRecords,
              market_data: md,
              shares_outstanding: shares
            };
            if (typeof window !== "undefined") window.appPeerValuationData = peerValuationDataBySymbol;
            const summary = computeHeaderPEPB(enrichedRecords, md, shares);
            const pe = summary.pe52wLow != null && summary.pe52wHigh != null
              ? `${Number(summary.pe52wLow).toFixed(1)} – ${Number(summary.pe52wHigh).toFixed(1)}` : "—";
            const pb = summary.pb52wLow != null && summary.pb52wHigh != null
              ? `${Number(summary.pb52wLow).toFixed(2)} – ${Number(summary.pb52wHigh).toFixed(2)}` : "—";
            const ev = summary.ev52wLow != null && summary.ev52wHigh != null
              ? `${Number(summary.ev52wLow).toFixed(1)} – ${Number(summary.ev52wHigh).toFixed(1)}` : "—";
            const latest = md.length > 0 ? md[md.length - 1] : null;
            const marketCap = (latest?.close != null && shares != null && !isNaN(shares))
              ? latest.close * 1000 * shares : null;
            peerValuationSummaryBySymbol[sym] = {
              pe, pb, ev,
              peLow: summary.pe52wLow, peHigh: summary.pe52wHigh, peCurrent: summary.currentPE,
              pbLow: summary.pb52wLow, pbHigh: summary.pb52wHigh, pbCurrent: summary.currentPB,
              evLow: summary.ev52wLow, evHigh: summary.ev52wHigh, evCurrent: summary.currentEVEBITDA,
              market_cap: marketCap
            };
            peerValFetchedSymbols.add(sym);
          });
          renderPeerAnalysisModalContent();
          // Also ensure the target company's own valuation is shown, even if backend (e.g. sample mode) did not
          // return it in the peer_valuations list. We compute it from the current dashboard data.
          (function updateTargetValuationFromCurrent() {
            const sym = (currentSymbol || "").trim().toUpperCase();
            if (!sym || !currentRecords || !currentRecords.length || !currentMarketData || !currentMarketData.length) return;
            // Store full target data for analysis (currentRecords are already enriched)
            peerValuationDataBySymbol[sym] = {
              records: currentRecords,
              market_data: currentMarketData,
              shares_outstanding: currentSharesOutstanding
            };
            if (typeof window !== "undefined") window.appPeerValuationData = peerValuationDataBySymbol;
            const summary = computeHeaderPEPB(currentRecords || [], currentMarketData || [], currentSharesOutstanding);
            const pe = summary.pe52wLow != null && summary.pe52wHigh != null
              ? `${Number(summary.pe52wLow).toFixed(1)} – ${Number(summary.pe52wHigh).toFixed(1)}` : "—";
            const pb = summary.pb52wLow != null && summary.pb52wHigh != null
              ? `${Number(summary.pb52wLow).toFixed(2)} – ${Number(summary.pb52wHigh).toFixed(2)}` : "—";
            const ev = summary.ev52wLow != null && summary.ev52wHigh != null
              ? `${Number(summary.ev52wLow).toFixed(1)} – ${Number(summary.ev52wHigh).toFixed(1)}` : "—";
            const tgtCap = getCurrentMarketCapVND(currentMarketData, currentSharesOutstanding);
            peerValuationSummaryBySymbol[sym] = {
              pe, pb, ev,
              peLow: summary.pe52wLow, peHigh: summary.pe52wHigh, peCurrent: summary.currentPE,
              pbLow: summary.pb52wLow, pbHigh: summary.pb52wHigh, pbCurrent: summary.currentPB,
              evLow: summary.ev52wLow, evHigh: summary.ev52wHigh, evCurrent: summary.currentEVEBITDA,
              market_cap: tgtCap
            };
            peerValFetchedSymbols.add(sym);
            renderPeerAnalysisModalContent();
          })();
          if (placeholder) {
            placeholder.textContent = list.length ? "" : "No valuation data returned.";
            placeholder.style.display = list.length ? "none" : "block";
          }
          setFetchStatus("complete", list.length ? "Peer valuations complete" : "No valuation data");
        } catch (e) {
          if (placeholder) placeholder.textContent = "Error: " + (e.message || String(e));
          setFetchStatus("error", "Peer valuations failed: " + (e.message || String(e)));
        } finally {
          btns.forEach((b) => { b.disabled = false; });
        }
      }
      const fetchChoiceEl = document.getElementById("peer-valuation-fetch-choice");
      const fetchAllBtn = document.getElementById("peer-valuation-fetch-all-btn");
      const fetchViewBtn = document.getElementById("peer-valuation-fetch-view-btn");

      function doFetchAll() {
        if (fetchChoiceEl) fetchChoiceEl.style.display = "none";
        const icbPeers = getICBPeers();
        const broadPeers = currentPeers || [];
        const icbSymbols = getScopeFilteredSymbols(icbPeers, currentPeerScopeMode);
        const broadSymbols = getScopeFilteredSymbols(broadPeers, currentPeerScopeMode);
        const symbols = [...new Set([...icbSymbols, ...broadSymbols, (currentSymbol || "").toUpperCase()].filter((s) => s))];
        fetchPeerValuations(symbols, currentSymbol, "all");
      }

      function doFetchCurrentView() {
        if (fetchChoiceEl) fetchChoiceEl.style.display = "none";
        const peers = getPeersForModal();
        const symbols = [...new Set(getScopeFilteredSymbols(peers, currentPeerScopeMode).concat((currentSymbol || "").toUpperCase()).filter((s) => s))];
        const scope = currentPeerFilterMode === "icb" ? "icb" : "broader";
        fetchPeerValuations(symbols, currentSymbol, scope);
      }

      document.getElementById("peer-valuation-fetch-btn")?.addEventListener("click", () => {
        if (currentPeerFilterMode === "all") {
          doFetchAll();
        } else {
          if (fetchChoiceEl) fetchChoiceEl.style.display = "flex";
        }
      });

      fetchAllBtn?.addEventListener("click", () => doFetchAll());
      fetchViewBtn?.addEventListener("click", () => doFetchCurrentView());
    })();
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && peerModalEl.classList.contains("peer-analysis-modal--open")) {
        closePeerAnalysisModal();
      }
    });
  }

  // Earnings mode: Actual / Normalized / Conservative (quality, growth, valuation use chosen earnings; chart unchanged)
  document.querySelectorAll(".earnings-mode-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const mode = btn.getAttribute("data-mode");
      if (mode !== "actual" && mode !== "normalized" && mode !== "conservative") return;
      currentEarningsMode = mode;
      document.querySelectorAll(".earnings-mode-btn").forEach((b) => b.classList.toggle("active", b.getAttribute("data-mode") === mode));
      if (currentRecords.length > 0 && currentSymbol) {
        populateDashboard(currentRecords, currentSymbol, currentMarketData, currentSharesOutstanding, currentCompanyName, currentSectorIndustry, currentPeers, currentPeersNote);
      }
    });
  });

  // Financials view: Quarterly / Annually
  document.querySelectorAll(".financials-view-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const mode = btn.getAttribute("data-mode");
      if (mode !== "quarterly" && mode !== "annually") return;
      currentFinancialsViewMode = mode;
      document.querySelectorAll(".financials-view-btn").forEach((b) => {
        b.classList.toggle("active", b.getAttribute("data-mode") === mode);
        b.setAttribute("aria-pressed", b.getAttribute("data-mode") === mode ? "true" : "false");
      });
      if (currentRecords.length > 0) populateFinancialsSection(currentRecords);
    });
  });

  // Timeframe selector
  document.querySelectorAll(".timeframe-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const years = parseInt(btn.getAttribute("data-years"), 10);
      if (isNaN(years)) return;
      
      currentTimeframe = years;
      
      document.querySelectorAll(".timeframe-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      
      // Re-render dashboard with new timeframe
      if (currentRecords.length > 0 && currentSymbol) {
        populateDashboard(currentRecords, currentSymbol, currentMarketData, currentSharesOutstanding, currentCompanyName, currentSectorIndustry, currentPeers, currentPeersNote);
      }
    });
  });

  // Fetch options modal: show when user starts a fetch (Enter or Analyze)
  function showFetchOptionsModal(symbol) {
    const modal = document.getElementById("fetch-options-modal");
    const symbolEl = document.getElementById("fetch-options-symbol");
    if (modal && symbolEl) {
      symbolEl.textContent = symbol;
      modal.classList.add("fetch-options-modal--open");
      modal.setAttribute("aria-hidden", "false");
    }
  }

  function closeFetchOptionsModal() {
    const modal = document.getElementById("fetch-options-modal");
    if (modal) {
      modal.classList.remove("fetch-options-modal--open");
      modal.setAttribute("aria-hidden", "true");
    }
  }

  async function performFetch(symbol, includePeers) {
    closeFetchOptionsModal();
    setLoading(true);
    setStatus("Analyzing...", "loading");
    setFetchStatus("fetching_financials", includePeers ? "Fetching financials and peer list…" : "Fetching financials…");
    document.getElementById("stock-summary").style.display = "flex";
    const sampleCallout = document.getElementById("sample-callout");
    if (sampleCallout) sampleCallout.style.display = "none";

    try {
      const res = await fetch(runUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol, include_peers: includePeers }),
      });

      const json = await res.json();

      if (!res.ok) {
        setStatus(json.error || "Failed to fetch data", "error");
        setFetchStatus("error", json.error || "Failed");
        setLoading(false);
        return;
      }

      const records = json.records || [];
      const marketData = json.market || [];
      const sharesOutstanding = json.shares_outstanding ?? null;
      const actualSymbol = json.actual_symbol || symbol;
      const availableSamples = json.available_samples || [];
      const companyName = json.company_name ?? null;
      const sectorIndustry = json.sector_industry ?? null;
      const peers = json.peers || [];
      const peersNote = json.peers_note || null;

      if (actualSymbol !== symbol) {
        const list = availableSamples.length ? ` Available sample tickers: ${availableSamples.join(", ")}.` : "";
        sampleCallout.textContent = `Showing sample for ${actualSymbol}. Requested ticker "${symbol}" not available.${list}`;
        sampleCallout.style.display = "block";
      }

      if (records.length === 0) {
        setStatus("No data returned", "error");
        setFetchStatus("error", "No data returned");
        setLoading(false);
        return;
      }

      currentRecords = enrichRecordsWithNormalizedEarnings(records);
      currentSymbol = actualSymbol;
      currentMarketData = marketData;
      currentSharesOutstanding = sharesOutstanding;
      currentCompanyName = companyName;
      currentSectorIndustry = sectorIndustry;
      currentPeers = peers;
      currentPeersNote = peersNote;

      populateDashboard(currentRecords, actualSymbol, marketData, sharesOutstanding, companyName, sectorIndustry, peers, peersNote);

      if (downloadLink) {
        downloadLink.href = downloadTemplate.replace("__SYMBOL__", actualSymbol);
        downloadLink.style.display = "inline-block";
      }

      setStatus(`Analysis complete for ${actualSymbol}`, "success");
      setFetchStatus("complete", `Analysis complete for ${actualSymbol}`);
      const earningsWrap = document.getElementById("earnings-mode-wrap");
      if (earningsWrap) earningsWrap.style.display = "flex";
      setLoading(false);
    } catch (err) {
      setStatus("Network error: " + err.message, "error");
      setFetchStatus("error", "Network error: " + err.message);
      setLoading(false);
    }
  }

  // Auto-uppercase symbol input (tickers are case-sensitive)
  document.getElementById("symbol-input")?.addEventListener("input", (e) => {
    const el = e.target;
    const start = el.selectionStart;
    el.value = el.value.toUpperCase();
    el.setSelectionRange(start, start);
  });

  // Form submission: show fetch options (Enter or submit button)
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const symbolInput = document.getElementById("symbol-input");
    const symbol = (symbolInput?.value?.trim() || "").toUpperCase();
    if (!symbol) return;
    if (symbolInput) symbolInput.value = symbol;
    showFetchOptionsModal(symbol);
  });

  // Analyze button: same as form submit
  document.getElementById("analyze-btn")?.addEventListener("click", () => {
    const symbolInput = document.getElementById("symbol-input");
    const symbol = (symbolInput?.value?.trim() || "").toUpperCase();
    if (!symbol) return;
    if (symbolInput) symbolInput.value = symbol;
    showFetchOptionsModal(symbol);
  });

  // Fetch options modal buttons
  document.getElementById("fetch-options-financial-only")?.addEventListener("click", () => {
    const symbolInput = document.getElementById("symbol-input");
    const symbol = (symbolInput?.value?.trim() || "").toUpperCase();
    if (symbol) {
      if (symbolInput) symbolInput.value = symbol;
      performFetch(symbol, false);
    }
  });
  document.getElementById("fetch-options-with-peers")?.addEventListener("click", () => {
    const symbolInput = document.getElementById("symbol-input");
    const symbol = (symbolInput?.value?.trim() || "").toUpperCase();
    if (symbol) {
      if (symbolInput) symbolInput.value = symbol;
      performFetch(symbol, true);
    }
  });

  // Need peers modal: fetch peers on demand, then open peer analysis
  async function performFetchPeers() {
    if (!currentSymbol) return;
    closeNeedPeersModal();
    setFetchStatus("fetching_peers", "Fetching peer list…");
    try {
      const res = await fetch(runPeersUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol: currentSymbol }),
      });
      const json = await res.json();
      if (!res.ok) {
        setFetchStatus("error", json.error || "Failed to fetch peers");
        setStatus(json.error || "Failed to fetch peers", "error");
        return;
      }
      currentPeers = json.peers || [];
      currentPeersNote = json.peers_note || null;
      if (json.company_name != null) currentCompanyName = json.company_name;
      if (json.sector_industry != null) currentSectorIndustry = json.sector_industry;
      if (json.market && json.market.length) currentMarketData = json.market;
      if (json.shares_outstanding != null) currentSharesOutstanding = json.shares_outstanding;
      setFetchStatus("complete", "Peer list fetched");
      populatePeersSection(currentPeers, currentPeersNote);
      openPeerAnalysisModal();
    } catch (err) {
      setFetchStatus("error", "Network error: " + err.message);
      setStatus("Network error: " + err.message, "error");
    }
  }

  document.getElementById("need-peers-cancel")?.addEventListener("click", closeNeedPeersModal);
  document.getElementById("need-peers-fetch")?.addEventListener("click", performFetchPeers);

  document.addEventListener("keydown", (e) => {
    const fetchModal = document.getElementById("fetch-options-modal");
    if (e.key === "Enter" && fetchModal?.classList.contains("fetch-options-modal--open")) {
      e.preventDefault();
      const symbolInput = document.getElementById("symbol-input");
      const symbol = (symbolInput?.value?.trim() || "").toUpperCase();
      if (symbol) {
        if (symbolInput) symbolInput.value = symbol;
        performFetch(symbol, false);
      }
      return;
    }
    if (e.key !== "Escape") return;
    if (fetchModal?.classList.contains("fetch-options-modal--open")) {
      closeFetchOptionsModal();
    } else if (document.getElementById("need-peers-modal")?.classList.contains("need-peers-modal--open")) {
      closeNeedPeersModal();
    }
  });

  window.addEventListener("resize", () => {
    if (document.getElementById("growth-chart")?.data) syncGrowthChartHeight();
  });

  // Initial state
  showEmptyState();
});
