"""Market regime detection using VIX, SPY momentum, and market breadth."""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict

import yfinance as yf

logger = logging.getLogger("moonshotx.regime")

REGIME_CACHE: Dict = {"regime": "neutral", "updated_at": None, "data": {}}
CACHE_TTL_SECONDS = 300  # 5 minutes


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

    # Estimate Fear & Greed from VIX (inverted + SPY momentum)
    vix_fg = max(0.0, min(100.0, 100.0 - (vix - 10.0) * 4.0))
    mom_fg = max(0.0, min(100.0, 50.0 + spy_20d * 500.0))
    fear_greed = round(0.6 * vix_fg + 0.4 * mom_fg, 1)

    # Simplified breadth: estimate from SPY vs 200-day SMA ratio
    try:
        spy_long = yf.Ticker("SPY").history(period="1y", interval="1d")
        sma_200 = float(spy_long["Close"].rolling(200).mean().iloc[-1]) if len(spy_long) >= 200 else spy_price * 0.95
        breadth = 0.65 if spy_price > sma_200 else 0.35
    except Exception:
        breadth = 0.50

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
