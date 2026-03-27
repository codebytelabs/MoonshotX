"""Market regime detection using VIX, SPY momentum, and market breadth."""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict

import requests
import yfinance as yf

logger = logging.getLogger("moonshotx.regime")

REGIME_CACHE: Dict = {"regime": "neutral", "updated_at": None, "data": {}}
CACHE_TTL_SECONDS = 300  # 5 minutes

_CNN_FG_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
_CNN_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

_SECTOR_ETFS = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLC", "XLRE", "XLU", "XLB", "XLP"]


def _fetch_fear_greed(vix: float = 20.0, spy_20d: float = 0.0) -> float:
    """Fetch real Fear & Greed from CNN. Falls back to VIX/momentum formula."""
    try:
        r = requests.get(_CNN_FG_URL, headers=_CNN_HEADERS, timeout=6)
        r.raise_for_status()
        score = float(r.json()["fear_and_greed"]["score"])
        logger.debug(f"CNN Fear & Greed: {score:.1f}")
        return round(score, 1)
    except Exception as e:
        logger.warning(f"CNN Fear & Greed unavailable ({e}), using formula fallback")
        vix_fg = max(0.0, min(100.0, 100.0 - (vix - 10.0) * 4.0))
        mom_fg = max(0.0, min(100.0, 50.0 + spy_20d * 500.0))
        return round(0.6 * vix_fg + 0.4 * mom_fg, 1)


def _fetch_sector_breadth() -> float:
    """Real breadth: % of 11 S&P 500 sector ETFs above their 200-day SMA."""
    above = 0
    total = 0
    for sym in _SECTOR_ETFS:
        try:
            hist = yf.Ticker(sym).history(period="1y", interval="1d")
            if len(hist) >= 200:
                sma200 = float(hist["Close"].rolling(200).mean().iloc[-1])
                price = float(hist["Close"].iloc[-1])
                above += 1 if price > sma200 else 0
                total += 1
        except Exception:
            pass
    if total == 0:
        return 0.50
    breadth = above / total
    logger.debug(f"Sector breadth: {above}/{total} ETFs above 200-SMA = {breadth:.2f}")
    return round(breadth, 3)


def _fetch_regime_data() -> dict:
    """Synchronous fetch of regime inputs."""
    try:
        vix_ticker = yf.Ticker("^VIX")
        vix_hist = vix_ticker.history(period="5d", interval="1d")
        vix = float(vix_hist["Close"].iloc[-1]) if not vix_hist.empty else 20.0
    except Exception:
        vix = 20.0

    try:
        spy = yf.Ticker("SPY")
        spy_hist = spy.history(period="1mo", interval="1d")
        if len(spy_hist) >= 20:
            spy_20d = float((spy_hist["Close"].iloc[-1] - spy_hist["Close"].iloc[-20]) / spy_hist["Close"].iloc[-20])
        elif len(spy_hist) >= 2:
            spy_20d = float((spy_hist["Close"].iloc[-1] - spy_hist["Close"].iloc[0]) / spy_hist["Close"].iloc[0])
        else:
            spy_20d = 0.0
        spy_price = float(spy_hist["Close"].iloc[-1]) if not spy_hist.empty else 0.0
    except Exception:
        spy_20d = 0.0
        spy_price = 0.0

    fear_greed = _fetch_fear_greed(vix=vix, spy_20d=spy_20d)
    breadth = _fetch_sector_breadth()
    regime = _classify(vix, fear_greed, breadth, spy_20d)

    return {
        "regime": regime,
        "vix": round(vix, 2),
        "fear_greed": round(fear_greed, 1),
        "breadth": round(breadth, 3),
        "spy_20d_return": round(spy_20d * 100, 2),
        "spy_price": round(spy_price, 2),
    }


def _classify(vix: float, fg: float, breadth: float, spy_20d: float) -> str:
    if vix > 35 and breadth < 0.20:
        return "extreme_fear"
    if vix > 28 and breadth < 0.30:
        return "bear_mode"
    if vix > 22 or breadth < 0.40 or fg < 25:
        return "fear"
    if fg < 35 or spy_20d < -0.02 or (vix > 18 and breadth < 0.50):
        return "choppy"
    if fg > 70 and breadth > 0.60 and spy_20d > 0.03:
        return "bull"
    return "neutral"


class RegimeManager:
    async def get_current(self) -> dict:
        now = datetime.now(timezone.utc)
        if (
            REGIME_CACHE["updated_at"] is None
            or (now - REGIME_CACHE["updated_at"]).total_seconds() > CACHE_TTL_SECONDS
        ):
            try:
                data = await asyncio.to_thread(_fetch_regime_data)
                REGIME_CACHE.update(data)
                REGIME_CACHE["regime"] = data["regime"]
                REGIME_CACHE["updated_at"] = now
            except Exception as e:
                logger.error(f"Regime fetch error: {e}")
        return dict(REGIME_CACHE)

    def regime_allows_longs(self, regime: str) -> bool:
        return regime in ("bull", "neutral", "fear")

    def max_positions(self, regime: str) -> int:
        return {"bull": 5, "neutral": 4, "fear": 3, "choppy": 0, "bear_mode": 0, "extreme_fear": 0}.get(regime, 0)
