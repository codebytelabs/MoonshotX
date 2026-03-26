"""MoonshotX Backend API Tests"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestCoreEndpoints:
    """Test core API endpoints"""

    def test_root(self):
        r = requests.get(f"{BASE_URL}/api/")
        assert r.status_code == 200
        data = r.json()
        assert data.get("service") == "MoonshotX"

    def test_account(self):
        r = requests.get(f"{BASE_URL}/api/account")
        assert r.status_code == 200
        data = r.json()
        assert "portfolio_value" in data
        assert "equity" in data
        assert "cash" in data
        assert "buying_power" in data
        assert "is_market_open" in data
        assert isinstance(data["portfolio_value"], float)
        print(f"Portfolio Value: ${data['portfolio_value']:,.2f}")
        print(f"Market Open: {data['is_market_open']}")

    def test_positions(self):
        r = requests.get(f"{BASE_URL}/api/positions")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        print(f"Open positions: {len(data)}")
        for p in data:
            assert "ticker" in p
            assert "qty" in p
            assert "unrealized_pnl" in p
            print(f"  {p['ticker']}: {p['qty']} shares, PnL=${p['unrealized_pnl']:.2f}")

    def test_regime(self):
        r = requests.get(f"{BASE_URL}/api/regime")
        assert r.status_code == 200
        data = r.json()
        assert "regime" in data
        print(f"Regime: {data['regime']}, VIX: {data.get('vix')}, Fear/Greed: {data.get('fear_greed')}")

    def test_universe(self):
        r = requests.get(f"{BASE_URL}/api/universe")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        print(f"Universe stocks: {len(data)}")

    def test_system_status(self):
        r = requests.get(f"{BASE_URL}/api/system/status")
        assert r.status_code == 200
        data = r.json()
        assert "is_running" in data
        assert "is_halted" in data
        assert "regime" in data
        print(f"System running: {data['is_running']}, halted: {data['is_halted']}")

    def test_performance(self):
        r = requests.get(f"{BASE_URL}/api/performance")
        assert r.status_code == 200
        data = r.json()
        assert "total_trades" in data
        assert "win_rate" in data

    def test_agent_logs(self):
        r = requests.get(f"{BASE_URL}/api/agent-logs")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)

    def test_system_events(self):
        r = requests.get(f"{BASE_URL}/api/system-events")
        assert r.status_code == 200

    def test_trades(self):
        r = requests.get(f"{BASE_URL}/api/trades")
        assert r.status_code == 200


class TestSystemControl:
    """Test system start/stop"""

    def test_stop_then_start_then_stop(self):
        # stop first
        r = requests.post(f"{BASE_URL}/api/system/stop")
        assert r.status_code == 200

        r = requests.post(f"{BASE_URL}/api/system/start")
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") in ["started", "already_running"]

        # stop again
        r = requests.post(f"{BASE_URL}/api/system/stop")
        assert r.status_code == 200
        assert r.json().get("status") == "stopped"

    def test_reset(self):
        r = requests.post(f"{BASE_URL}/api/system/reset")
        assert r.status_code == 200
