"""Morning Intelligence Brief — runs T-20 minutes before market open.

Gathers overnight global market data, news, and macro signals, then sends
everything to a single LLM call to produce a structured pre-session briefing.

The brief answers:
  - What happened overnight? (futures, international markets, news)
  - What is the macro backdrop? (geopolitics, supply chain, earnings, rates)
  - What sectors / themes are hot or risky today?
  - Which tickers from our watchlist are most likely to move?
  - What trading stance should we take this session?

Output feeds directly into the batch pipeline to bias candidate ranking.
"""
import asyncio
import logging
from datetime import datetime, timezone

import yfinance as yf

logger = logging.getLogger("moonshotx.morning_brief")

# ── Symbols to track overnight ────────────────────────────────────────────────
US_FUTURES = {
    "ES=F":  "S&P 500 futures",
    "NQ=F":  "NASDAQ futures",
    "YM=F":  "Dow futures",
    "RTY=F": "Russell 2000 futures",
}
INTL_INDICES = {
    "^N225":  "Nikkei 225 (Japan)",
    "^HSI":   "Hang Seng (Hong Kong)",
    "^GDAXI": "DAX (Germany)",
    "^FTSE":  "FTSE 100 (UK)",
    "^AXJO":  "ASX 200 (Australia)",
}
MACRO_INDICATORS = {
    "^VIX":  "VIX (fear index)",
    "GC=F":  "Gold futures",
    "CL=F":  "Crude oil futures",
    "DX=F":  "US Dollar index",
    "^TNX":  "10-yr Treasury yield",
}
NEWS_TICKERS = ["SPY", "QQQ", "^VIX"]     # pull headlines from these
MAX_HEADLINES = 10                          # headlines per ticker (deduplicated)


# ── Data gathering ────────────────────────────────────────────────────────────

def _fetch_price(symbol: str) -> dict | None:
    """Synchronous yfinance price fetch (run in thread)."""
    try:
        info = yf.Ticker(symbol).fast_info
        price = float(info.last_price)
        prev  = float(info.previous_close)
        chg   = round((price - prev) / prev * 100, 2) if prev else 0.0
        return {"symbol": symbol, "price": round(price, 2), "chg_pct": chg}
    except Exception:
        return None


def _fetch_news(symbols: list[str]) -> list[str]:
    """Pull recent deduplicated headlines from yfinance."""
    seen   = set()
    result = []
    for sym in symbols:
        try:
            items = yf.Ticker(sym).news or []
            for item in items[:MAX_HEADLINES]:
                title = (
                    item.get("content", {}).get("title")
                    or item.get("title", "")
                )
                if title and title not in seen:
                    seen.add(title)
                    result.append(title)
        except Exception:
            pass
    return result[:20]   # cap total headlines


async def gather_overnight_intel(alpaca) -> dict:
    """Fetch all overnight data concurrently. Returns structured intel dict."""
    all_symbols = {**US_FUTURES, **INTL_INDICES, **MACRO_INDICATORS}

    # Fetch prices concurrently
    price_tasks = [
        asyncio.to_thread(_fetch_price, sym) for sym in all_symbols
    ]
    news_task   = asyncio.to_thread(_fetch_news, NEWS_TICKERS)
    movers_task = alpaca.get_top_movers(top=20)

    results, headlines, top_movers = await asyncio.gather(
        asyncio.gather(*price_tasks),
        news_task,
        movers_task,
        return_exceptions=True,
    )

    # Organise into buckets
    futures_data = {}
    intl_data    = {}
    macro_data   = {}

    if isinstance(results, (list, tuple)):
        for item in results:
            if not item:
                continue
            sym = item["symbol"]
            entry = {"price": item["price"], "chg_pct": item["chg_pct"]}
            if sym in US_FUTURES:
                futures_data[f"{sym} ({US_FUTURES[sym]})"] = entry
            elif sym in INTL_INDICES:
                intl_data[f"{sym} ({INTL_INDICES[sym]})"] = entry
            elif sym in MACRO_INDICATORS:
                macro_data[f"{sym} ({MACRO_INDICATORS[sym]})"] = entry

    return {
        "us_futures":      futures_data,
        "intl_indices":    intl_data,
        "macro_indicators": macro_data,
        "headlines":       headlines if isinstance(headlines, list) else [],
        "pre_market_movers": top_movers if isinstance(top_movers, list) else [],
        "fetched_at":      datetime.now(timezone.utc).isoformat(),
    }


# ── LLM analysis ──────────────────────────────────────────────────────────────

def _build_brief_prompt(intel: dict, regime_data: dict, watchlist: list[str]) -> str:
    """Build the user prompt for the morning brief LLM call."""

    def fmt_table(data: dict) -> str:
        lines = []
        for name, vals in data.items():
            chg = vals.get("chg_pct", 0)
            arrow = "▲" if chg > 0 else ("▼" if chg < 0 else "─")
            lines.append(f"  {arrow} {name}: {vals.get('price')!s:>10}  ({chg:+.2f}%)")
        return "\n".join(lines) if lines else "  N/A"

    futures_str  = fmt_table(intel.get("us_futures", {}))
    intl_str     = fmt_table(intel.get("intl_indices", {}))
    macro_str    = fmt_table(intel.get("macro_indicators", {}))
    headlines    = intel.get("headlines", [])
    movers       = intel.get("pre_market_movers", [])[:10]
    current_reg  = regime_data.get("regime", "neutral")
    vix          = regime_data.get("vix", "N/A")
    fg           = regime_data.get("fear_greed_index", "N/A")

    news_block = "\n".join(f"  • {h}" for h in headlines[:12]) if headlines else "  No headlines available"
    movers_block = ", ".join(movers[:10]) if movers else "N/A"
    watchlist_str = ", ".join(watchlist[:30]) if watchlist else "N/A"

    return f"""You are the pre-market intelligence analyst for MoonshotX, an intraday momentum trading bot.
Market opens in ~15 minutes. Produce a crisp morning brief from the data below.

=== CURRENT REGIME ===
Regime: {current_reg}  |  VIX: {vix}  |  Fear & Greed: {fg}

=== US FUTURES (overnight) ===
{futures_str}

=== INTERNATIONAL MARKETS (overnight) ===
{intl_str}

=== MACRO INDICATORS ===
{macro_str}

=== PRE-MARKET TOP MOVERS ===
{movers_block}

=== OVERNIGHT NEWS HEADLINES ===
{news_block}

=== OUR WATCHLIST (evaluate these for today) ===
{watchlist_str}

Analyze everything above and respond ONLY with this JSON (no other text):
{{
  "expected_regime": "bull" | "neutral" | "fear" | "choppy" | "bear_mode",
  "trading_stance": "aggressive" | "normal" | "cautious" | "sit_out",
  "session_sentiment": "brief 1-sentence overall market mood",
  "hot_sectors": ["sector1", "sector2"],
  "avoid_sectors": ["sector3"],
  "key_themes": ["theme1 (e.g. tariff escalation)", "theme2"],
  "macro_risks": ["risk1", "risk2"],
  "top_picks": [
    {{"symbol": "TICK", "thesis": "1-sentence why it moves today", "confidence": 0.0-1.0}},
    {{"symbol": "TICK2", "thesis": "...", "confidence": 0.0-1.0}}
  ],
  "avoid_picks": ["SYM1", "SYM2"],
  "brief_summary": "2-3 sentence executive summary of what to expect today"
}}"""


async def run_morning_brief(
    alpaca,
    pipeline,
    regime_data: dict,
    watchlist: list[str],
) -> dict:
    """
    Run full morning brief: gather overnight data → one LLM call → structured intel.
    Returns the brief dict (also logged). Falls back to empty dict on any failure.
    """
    logger.info("[MORNING BRIEF] Gathering overnight intel...")
    try:
        intel = await gather_overnight_intel(alpaca)
    except Exception as e:
        logger.error(f"[MORNING BRIEF] Data gather failed: {e}")
        return {}

    # Log market snapshot
    for label, bucket in [
        ("Futures",  intel.get("us_futures", {})),
        ("Intl",     intel.get("intl_indices", {})),
        ("Macro",    intel.get("macro_indicators", {})),
    ]:
        for name, vals in bucket.items():
            chg = vals.get("chg_pct", 0)
            logger.info(f"[MORNING BRIEF] {label}: {name} {chg:+.2f}%")

    logger.info(f"[MORNING BRIEF] Headlines: {len(intel.get('headlines', []))} | "
                f"Pre-market movers: {len(intel.get('pre_market_movers', []))}")

    # One DEEP LLM call for macro analysis
    sys_p = (
        "You are MoonshotX pre-market intelligence analyst. "
        "Analyze global overnight data and produce a trading brief for the upcoming US session. "
        "Return ONLY valid JSON, no markdown, no code blocks."
    )
    user_p = _build_brief_prompt(intel, regime_data, watchlist)

    try:
        brief = await pipeline._call_llm(sys_p, user_p, model=pipeline.DEEP_MODEL, timeout=90)
    except Exception as e:
        logger.error(f"[MORNING BRIEF] LLM call failed: {e}")
        return {"raw_intel": intel}

    if not brief:
        logger.warning("[MORNING BRIEF] LLM returned empty response")
        return {"raw_intel": intel}

    brief["raw_intel"]  = intel
    brief["created_at"] = datetime.now(timezone.utc).isoformat()

    # Log the summary
    stance  = brief.get("trading_stance", "?")
    regime  = brief.get("expected_regime", "?")
    summary = brief.get("brief_summary", "")
    themes  = brief.get("key_themes", [])
    hot     = brief.get("hot_sectors", [])
    picks   = [p.get("symbol") for p in brief.get("top_picks", [])]

    logger.info(f"[MORNING BRIEF] ═══════════════════════════════════════")
    logger.info(f"[MORNING BRIEF] Stance={stance}  Regime={regime}")
    logger.info(f"[MORNING BRIEF] Themes: {themes}")
    logger.info(f"[MORNING BRIEF] Hot sectors: {hot}")
    logger.info(f"[MORNING BRIEF] Top picks: {picks}")
    logger.info(f"[MORNING BRIEF] Summary: {summary}")
    logger.info(f"[MORNING BRIEF] ═══════════════════════════════════════")

    return brief
