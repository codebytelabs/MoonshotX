"""Alpaca Markets REST API client (paper trading)."""
import asyncio
import logging
import requests
from typing import Optional, Dict, Any

logger = logging.getLogger("moonshotx.alpaca")


class AlpacaClient:
    def __init__(self, api_key: str, secret_key: str, base_url: str = "https://paper-api.alpaca.markets"):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": secret_key,
            "Content-Type": "application/json",
        })

    def _get(self, path: str) -> Any:
        r = self.session.get(f"{self.base_url}{path}")
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, data: dict) -> Any:
        r = self.session.post(f"{self.base_url}{path}", json=data)
        r.raise_for_status()
        return r.json()

    def _delete(self, path: str) -> int:
        r = self.session.delete(f"{self.base_url}{path}")
        return r.status_code

    async def get_account(self) -> dict:
        try:
            return await asyncio.to_thread(self._get, "/v2/account")
        except Exception as e:
            logger.error(f"get_account error: {e}")
            return {}

    async def get_positions(self) -> list:
        try:
            return await asyncio.to_thread(self._get, "/v2/positions")
        except Exception as e:
            logger.error(f"get_positions error: {e}")
            return []

    async def get_orders(self, status: str = "open") -> list:
        try:
            return await asyncio.to_thread(self._get, f"/v2/orders?status={status}")
        except Exception as e:
            logger.error(f"get_orders error: {e}")
            return []

    async def get_clock(self) -> dict:
        try:
            return await asyncio.to_thread(self._get, "/v2/clock")
        except Exception as e:
            logger.error(f"get_clock error: {e}")
            return {"is_open": False}

    async def submit_market_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        take_profit_price: Optional[float] = None,
        stop_loss_price: Optional[float] = None,
    ) -> dict:
        data: Dict[str, Any] = {
            "symbol": symbol,
            "qty": str(qty),
            "side": side,
            "type": "market",
            "time_in_force": "day",
        }
        if take_profit_price and stop_loss_price:
            data["order_class"] = "bracket"
            data["take_profit"] = {"limit_price": str(round(take_profit_price, 2))}
            data["stop_loss"] = {"stop_price": str(round(stop_loss_price, 2))}
        try:
            return await asyncio.to_thread(self._post, "/v2/orders", data)
        except Exception as e:
            logger.error(f"submit_order error: {e}")
            return {}

    async def submit_limit_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        limit_price: float,
        take_profit_price: Optional[float] = None,
        stop_loss_price: Optional[float] = None,
    ) -> dict:
        data: Dict[str, Any] = {
            "symbol": symbol,
            "qty": str(qty),
            "side": side,
            "type": "limit",
            "limit_price": str(round(limit_price, 2)),
            "time_in_force": "day",
        }
        if take_profit_price and stop_loss_price:
            data["order_class"] = "bracket"
            data["take_profit"] = {"limit_price": str(round(take_profit_price, 2))}
            data["stop_loss"] = {"stop_price": str(round(stop_loss_price, 2))}
        try:
            return await asyncio.to_thread(self._post, "/v2/orders", data)
        except Exception as e:
            logger.error(f"submit_limit_order error: {e}")
            return {}

    async def cancel_all_orders(self) -> int:
        try:
            return await asyncio.to_thread(self._delete, "/v2/orders")
        except Exception as e:
            logger.error(f"cancel_all_orders error: {e}")
            return 0

    async def close_all_positions(self) -> int:
        try:
            return await asyncio.to_thread(self._delete, "/v2/positions")
        except Exception as e:
            logger.error(f"close_all_positions error: {e}")
            return 0

    async def close_position(self, symbol: str) -> dict:
        try:
            return await asyncio.to_thread(self._delete, f"/v2/positions/{symbol}")
        except Exception as e:
            logger.error(f"close_position {symbol} error: {e}")
            return {}

    async def cancel_order(self, order_id: str) -> bool:
        try:
            status = await asyncio.to_thread(self._delete, f"/v2/orders/{order_id}")
            return status in (200, 204)
        except Exception as e:
            logger.warning(f"cancel_order {order_id} error: {e}")
            return False

    async def get_orders_for_symbol(self, symbol: str, status: str = "open") -> list:
        try:
            orders = await asyncio.to_thread(self._get, f"/v2/orders?status={status}&symbols={symbol}")
            return orders if isinstance(orders, list) else []
        except Exception as e:
            logger.warning(f"get_orders_for_symbol {symbol} error: {e}")
            return []

    async def submit_stop_order(self, symbol: str, qty: int, stop_price: float, side: str = "sell") -> dict:
        data = {
            "symbol": symbol,
            "qty": str(qty),
            "side": side,
            "type": "stop",
            "stop_price": str(round(stop_price, 2)),
            "time_in_force": "gtc",
        }
        try:
            return await asyncio.to_thread(self._post, "/v2/orders", data)
        except Exception as e:
            logger.error(f"submit_stop_order {symbol} error: {e}")
            return {}

    async def partial_close(self, symbol: str, qty: int) -> dict:
        data = {
            "symbol": symbol,
            "qty": str(qty),
            "side": "sell",
            "type": "market",
            "time_in_force": "day",
        }
        try:
            return await asyncio.to_thread(self._post, "/v2/orders", data)
        except Exception as e:
            logger.error(f"partial_close {symbol} x{qty} error: {e}")
            return {}

    # ── Data API screener (data.alpaca.markets) ──────────────────────────

    def _data_get(self, path: str) -> Any:
        r = self.session.get(f"https://data.alpaca.markets{path}")
        r.raise_for_status()
        return r.json()

    async def get_most_active(self, top: int = 50) -> list[str]:
        """Top stocks by trading volume via Alpaca screener."""
        try:
            data = await asyncio.to_thread(self._data_get, f"/v1beta1/screener/stocks/most-actives?by=volume&top={top}")
            return [item["symbol"] for item in data.get("most_actives", []) if item.get("symbol")]
        except Exception as e:
            logger.warning(f"get_most_active error: {e}")
            return []

    async def get_portfolio_history(self, period: str = "1M", timeframe: str = "1D", extended_hours: bool = True, start_date: str = "") -> dict:
        """Fetch portfolio value history from Alpaca.
        period: 1D, 1W, 1M, 3M, 6M, 1A
        timeframe: 1Min, 5Min, 15Min, 1H, 1D
        start_date: optional ISO date string (YYYY-MM-DD) to cap history start
        Returns list of {ts, value} dicts.
        """
        try:
            params = f"?period={period}&timeframe={timeframe}&extended_hours={str(extended_hours).lower()}"
            if start_date:
                params += f"&start={start_date[:10]}"
            raw = await asyncio.to_thread(self._get, f"/v2/account/portfolio/history{params}")
            timestamps = raw.get("timestamp", [])
            equity = raw.get("equity", [])
            result = []
            for ts, val in zip(timestamps, equity):
                if val is not None and val > 0:
                    from datetime import datetime, timezone
                    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                    result.append({"ts": dt.isoformat(), "value": round(val, 2)})
            return result
        except Exception as e:
            logger.warning(f"get_portfolio_history error: {e}")
            return []

    async def get_top_movers(self, top: int = 50, market_type: str = "stocks") -> list[str]:
        """Top gainers via Alpaca screener."""
        try:
            data = await asyncio.to_thread(self._data_get, f"/v1beta1/screener/{market_type}/movers?top={top}")
            gainers = [item["symbol"] for item in data.get("gainers", []) if item.get("symbol")]
            return gainers
        except Exception as e:
            logger.warning(f"get_top_movers error: {e}")
            return []

    async def get_snapshot(self, symbol: str) -> dict:
        """Get real-time snapshot: latest trade, quote, minute bar, daily bar."""
        try:
            return await asyncio.to_thread(self._data_get, f"/v2/stocks/{symbol}/snapshot")
        except Exception as e:
            logger.warning(f"get_snapshot {symbol} error: {e}")
            return {}

    async def get_bars(self, symbol: str, timeframe: str = "5Min", limit: int = 6) -> list[dict]:
        """Get recent intraday bars (default: last 6 x 5-min = 30 min)."""
        try:
            data = await asyncio.to_thread(
                self._data_get,
                f"/v2/stocks/{symbol}/bars?timeframe={timeframe}&limit={limit}",
            )
            return data.get("bars", [])
        except Exception as e:
            logger.warning(f"get_bars {symbol} error: {e}")
            return []
