"""Earnings blackout — skip tickers with upcoming earnings to avoid binary events."""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional
import yfinance as yf

logger = logging.getLogger("moonshotx.earnings")

# ── Config ────────────────────────────────────────────────────────────────────
BLACKOUT_DAYS_BEFORE = 2         # don't enter N days before earnings
BLACKOUT_DAYS_AFTER = 1          # don't enter N days after earnings (gap risk)
CACHE_TTL_SECONDS = 3600         # cache earnings dates for 1 hour

# ── Cache ─────────────────────────────────────────────────────────────────────
_earnings_cache: Dict[str, dict] = {}


def _fetch_earnings_date(ticker: str) -> Optional[datetime]:
    """Fetch next earnings date from yfinance. Returns None if unavailable."""
    try:
        t = yf.Ticker(ticker)
        cal = t.calendar
        if cal is None:
            return None
        import datetime as dt_module
        if isinstance(cal, dict):
            dates = cal.get("Earnings Date", [])
            if dates and len(dates) > 0:
                ed = dates[0]
                if isinstance(ed, dt_module.date):
                    return datetime(ed.year, ed.month, ed.day, tzinfo=timezone.utc)
                if hasattr(ed, "to_pydatetime"):
                    return ed.to_pydatetime().replace(tzinfo=timezone.utc)
        elif hasattr(cal, "columns"):
            if "Earnings Date" in cal.index:
                ed = cal.loc["Earnings Date"].iloc[0]
                if isinstance(ed, dt_module.date):
                    return datetime(ed.year, ed.month, ed.day, tzinfo=timezone.utc)
                if hasattr(ed, "to_pydatetime"):
                    return ed.to_pydatetime().replace(tzinfo=timezone.utc)
        return None
    except Exception as e:
        logger.debug(f"Earnings fetch error {ticker}: {e}")
        return None


async def get_earnings_date(ticker: str) -> Optional[datetime]:
    """Get cached or fresh earnings date."""
    now = datetime.now(timezone.utc)
    cached = _earnings_cache.get(ticker)
    if cached and (now - cached["fetched_at"]).total_seconds() < CACHE_TTL_SECONDS:
        return cached["date"]

    earnings_date = await asyncio.to_thread(_fetch_earnings_date, ticker)
    _earnings_cache[ticker] = {"date": earnings_date, "fetched_at": now}
    return earnings_date


async def is_in_blackout(ticker: str) -> tuple[bool, str]:
    """Check if ticker is in earnings blackout window."""
    earnings_date = await get_earnings_date(ticker)
    if earnings_date is None:
        # No earnings data — allow trading (most stocks won't have it)
        return False, "no_earnings_data"

    now = datetime.now(timezone.utc)
    days_until = (earnings_date.date() - now.date()).days

    if -BLACKOUT_DAYS_AFTER <= days_until <= BLACKOUT_DAYS_BEFORE:
        return True, f"earnings in {days_until}d ({earnings_date.strftime('%Y-%m-%d')})"

    return False, f"earnings clear ({days_until}d away)"


async def batch_check_blackout(tickers: list[str]) -> Dict[str, tuple[bool, str]]:
    """Check multiple tickers in parallel."""
    results = await asyncio.gather(
        *[is_in_blackout(t) for t in tickers],
        return_exceptions=True,
    )
    out = {}
    for ticker, result in zip(tickers, results):
        if isinstance(result, Exception):
            out[ticker] = (False, f"error: {result}")
        else:
            out[ticker] = result
    return out
