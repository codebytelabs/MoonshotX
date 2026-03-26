"""
MoonshotX Model Benchmark — tests all candidate OpenRouter models against
realistic trading agent tasks and produces a ranked comparison report.

Evaluation dimensions:
  - Latency (seconds)
  - Structured output compliance (JSON parseable / required fields present)
  - Quality score (heuristic: specificity, completeness, correctness)
  - Token usage → estimated cost
  - Cost-efficiency: quality/cost, quality/latency

Run:
  cd backend
  OPENROUTER_API_KEY=<key> venv/bin/python -m pytest tests/test_model_benchmark.py -v -s
"""

import json
import os
import time
import re
from dataclasses import dataclass, field
from typing import Optional

import pytest
import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OPENROUTER_API_KEY = os.getenv(
    "OPENROUTER_API_KEY",
    "REDACTED_OPENROUTER_KEY",
)
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

# Models under test
REASONING_MODELS = [
    "z-ai/glm-5",
    "minimax/minimax-m2.7",
    "anthropic/claude-haiku-4-5",
]
QUICK_MODELS = [
    "nvidia/nemotron-3-super-120b-a12b:free",
    "google/gemini-2.5-flash-lite-preview-09-2025",
    "google/gemini-3.1-flash-lite-preview",
]
ALL_MODELS = REASONING_MODELS + QUICK_MODELS

# Approximate OpenRouter pricing per 1M tokens (input / output) in USD
# Source: openrouter.ai/models — updated 2026-03
PRICING = {
    "z-ai/glm-5":                                          (0.50, 0.50),
    "minimax/minimax-m2.7":                                (0.20, 0.20),
    "anthropic/claude-haiku-4-5":                          (0.80, 4.00),
    "nvidia/nemotron-3-super-120b-a12b:free":              (0.00, 0.00),
    "google/gemini-2.5-flash-lite-preview-09-2025":        (0.075, 0.30),
    "google/gemini-3.1-flash-lite-preview":                (0.075, 0.30),
}

# ---------------------------------------------------------------------------
# Task definitions — realistic agent prompts
# ---------------------------------------------------------------------------

TASKS = {
    # ── REASONING TASKS ────────────────────────────────────────────────────
    "technical_analysis": {
        "role": "reasoning",
        "agent": "TechnicalAnalyst",
        "system": (
            "You are an expert technical analyst for US equities. "
            "Respond ONLY with valid JSON."
        ),
        "user": (
            "Analyze NVDA given this data:\n"
            "Price: $125.40 | 5d mom: +3.2% | 20d mom: -1.8% | RSI(14): 58.3 | "
            "EMA9 > EMA21: True | ATR%: 2.4% | Volume ratio: 1.8x\n\n"
            "Respond with JSON: {\"signal\": \"BUY|SELL|HOLD\", "
            "\"confidence\": 0-1, \"key_levels\": {\"support\": ..., \"resistance\": ...}, "
            "\"reasoning\": \"...\", \"risks\": [...]}"
        ),
        "required_fields": ["signal", "confidence", "reasoning"],
        "valid_signals": ["BUY", "SELL", "HOLD"],
    },
    "fundamentals_analysis": {
        "role": "reasoning",
        "agent": "FundamentalsAnalyst",
        "system": (
            "You are a fundamentals analyst specializing in US tech stocks. "
            "Respond ONLY with valid JSON."
        ),
        "user": (
            "Analyze NVDA fundamentals:\n"
            "P/E: 42x | Forward P/E: 28x | Revenue growth YoY: +78% | "
            "Gross margin: 73% | Free cash flow: $35B | Debt/Equity: 0.4 | "
            "Next earnings: 14 days away\n\n"
            "Respond with JSON: {\"fundamental_rating\": \"STRONG|NEUTRAL|WEAK\", "
            "\"earnings_risk\": \"HIGH|MEDIUM|LOW\", \"fair_value_estimate\": ..., "
            "\"reasoning\": \"...\", \"catalysts\": [...]}"
        ),
        "required_fields": ["fundamental_rating", "earnings_risk", "reasoning"],
        "valid_signals": ["STRONG", "NEUTRAL", "WEAK"],
    },
    "bull_bear_debate": {
        "role": "reasoning",
        "agent": "BullDebater",
        "system": (
            "You are an aggressive bull-case analyst. Make the strongest possible "
            "bullish argument for the trade. Respond ONLY with valid JSON."
        ),
        "user": (
            "Make the bull case for buying NVDA at $125 with a 2-week hold:\n"
            "Regime: neutral | Bayesian score: 0.72 | Technical: bullish | "
            "Fundamentals: strong | Recent news: AI chip demand surge, data center buildout\n\n"
            "Respond with JSON: {\"verdict\": \"STRONG_BUY|BUY|WEAK_BUY\", "
            "\"price_target\": ..., \"catalyst\": \"...\", "
            "\"argument\": \"...\", \"conviction\": 0-1}"
        ),
        "required_fields": ["verdict", "price_target", "argument"],
        "valid_signals": ["STRONG_BUY", "BUY", "WEAK_BUY"],
    },
    "research_verdict": {
        "role": "reasoning",
        "agent": "ResearchManager",
        "system": (
            "You are a research manager synthesizing multiple analyst views. "
            "Make the final research verdict. Respond ONLY with valid JSON."
        ),
        "user": (
            "Synthesize these views on NVDA:\n"
            "Bull case: STRONG_BUY, target $145, conviction 0.82\n"
            "Bear case: HOLD, concerned about valuation at 42x P/E, conviction 0.61\n"
            "Technical: BUY, RSI 58, EMA bullish, volume 1.8x\n"
            "Fundamentals: STRONG, 78% revenue growth, 73% gross margin\n"
            "Regime: neutral (VIX 18.5, Fear/Greed 52)\n\n"
            "Respond with JSON: {\"final_verdict\": \"APPROVE|REJECT\", "
            "\"confidence\": 0-1, \"suggested_action\": \"BUY|SELL|HOLD\", "
            "\"reasoning\": \"...\", \"key_risk\": \"...\"}"
        ),
        "required_fields": ["final_verdict", "confidence", "reasoning"],
        "valid_signals": ["APPROVE", "REJECT"],
    },
    "risk_assessment": {
        "role": "reasoning",
        "agent": "RiskAnalyst",
        "system": (
            "You are a conservative risk analyst. Assess trade risk rigorously. "
            "Respond ONLY with valid JSON."
        ),
        "user": (
            "Assess risk for this proposed trade:\n"
            "Symbol: NVDA | Entry: $125 | Stop-loss: $120 | Take-profit: $135 | "
            "Position size: $5,000 (4% of portfolio) | Regime: neutral | "
            "Earnings in 14 days | Correlation with AAPL: 0.72\n\n"
            "Respond with JSON: {\"risk_verdict\": \"APPROVE|REDUCE|REJECT\", "
            "\"max_loss_pct\": ..., \"r_ratio\": ..., "
            "\"primary_risk\": \"...\", \"recommendation\": \"...\"}"
        ),
        "required_fields": ["risk_verdict", "r_ratio", "primary_risk"],
        "valid_signals": ["APPROVE", "REDUCE", "REJECT"],
    },

    # ── QUICK TASKS ────────────────────────────────────────────────────────
    "sentiment_analysis": {
        "role": "quick",
        "agent": "SentimentAnalyst",
        "system": (
            "You are a market sentiment analyst. Extract signals from news quickly. "
            "Respond ONLY with valid JSON."
        ),
        "user": (
            "Score sentiment for NVDA from these headlines:\n"
            "1. 'NVDA beats Q4 earnings by 18%, raises guidance'\n"
            "2. 'Blackwell GPU shipments accelerate into Q2'\n"
            "3. 'China export restrictions may impact 15% of NVDA revenue'\n"
            "4. 'Jensen Huang: AI infrastructure spending not slowing'\n"
            "5. 'NVDA stock up 4% pre-market on earnings beat'\n\n"
            "Respond with JSON: {\"sentiment_score\": -1 to 1, "
            "\"signal\": \"BULLISH|BEARISH|NEUTRAL\", "
            "\"key_driver\": \"...\", \"risk_flag\": true/false}"
        ),
        "required_fields": ["sentiment_score", "signal", "key_driver"],
        "valid_signals": ["BULLISH", "BEARISH", "NEUTRAL"],
    },
    "news_summary": {
        "role": "quick",
        "agent": "NewsAnalyst",
        "system": (
            "You are a financial news analyst. Extract trading-relevant signals fast. "
            "Respond ONLY with valid JSON."
        ),
        "user": (
            "Analyze these market events for AMD today:\n"
            "1. AMD launches MI350 AI chip, claims 2x performance over NVDA H200\n"
            "2. AMD misses revenue estimate by 3%, but beats EPS\n"
            "3. Lisa Su increases 2026 AI chip revenue guidance to $7B\n"
            "4. Microsoft announces major AMD chip deployment for Azure\n"
            "5. Short interest in AMD increases 12% month-over-month\n\n"
            "Respond with JSON: {\"news_signal\": \"POSITIVE|NEGATIVE|MIXED\", "
            "\"catalyst_strength\": \"HIGH|MEDIUM|LOW\", "
            "\"tradeable\": true/false, \"summary\": \"...\", "
            "\"watch_factors\": [...]}"
        ),
        "required_fields": ["news_signal", "catalyst_strength", "tradeable"],
        "valid_signals": ["POSITIVE", "NEGATIVE", "MIXED"],
    },
    "trade_planning": {
        "role": "quick",
        "agent": "TraderPlanner",
        "system": (
            "You are a precision trade planner. Produce exact entry/exit levels fast. "
            "Respond ONLY with valid JSON."
        ),
        "user": (
            "Plan the trade for NVDA given approval to BUY:\n"
            "Current price: $125.40 | ATR: $3.01 (2.4%) | "
            "Support: $121.50 | Resistance: $132.00 | "
            "Portfolio: $125,000 | Risk per trade: 1.5% | Regime: neutral\n\n"
            "Respond with JSON: {\"order_type\": \"LIMIT|MARKET\", "
            "\"entry_price\": ..., \"stop_loss\": ..., \"take_profit\": ..., "
            "\"position_value\": ..., \"shares\": ..., \"r_ratio\": ...}"
        ),
        "required_fields": ["entry_price", "stop_loss", "take_profit", "shares"],
        "valid_signals": ["LIMIT", "MARKET"],
    },
}


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

@dataclass
class ModelResult:
    model: str
    task: str
    latency_s: float
    prompt_tokens: int
    completion_tokens: int
    response_text: str
    parsed_json: Optional[dict]
    fields_present: bool
    signal_valid: bool
    quality_score: float       # 0–10
    cost_usd: float
    error: Optional[str] = None


def _call_model(model: str, system: str, user: str, timeout: int = 60) -> dict:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://moonshotx.ai",
        "X-Title": "MoonshotX Benchmark",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": 1024,
        "temperature": 0.1,
    }
    t0 = time.perf_counter()
    r = requests.post(OPENROUTER_BASE_URL, headers=headers, json=payload, timeout=timeout)
    latency = time.perf_counter() - t0
    r.raise_for_status()
    data = r.json()
    content = data["choices"][0]["message"].get("content") or ""
    return {
        "latency": latency,
        "content": content,
        "prompt_tokens": data.get("usage", {}).get("prompt_tokens", 0),
        "completion_tokens": data.get("usage", {}).get("completion_tokens", 0),
    }


def _extract_json(text: str) -> Optional[dict]:
    if not text:
        return None
    text = text.strip()
    # Try direct parse
    try:
        return json.loads(text)
    except Exception:
        pass
    # Strip markdown fences
    m = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except Exception:
            pass
    # Find first { ... } block
    m = re.search(r"(\{[\s\S]+\})", text)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    # Truncated JSON — try to recover partial object
    start = text.find("{")
    if start != -1:
        fragment = text[start:]
        # Count open braces and close them
        opens = fragment.count("{")
        closes = fragment.count("}")
        if opens > closes:
            fragment += "}" * (opens - closes)
        try:
            return json.loads(fragment)
        except Exception:
            pass
        # Last resort: extract key-value pairs we can find
        pairs = re.findall(r'"(\w+)"\s*:\s*("[^"]*"|\d+\.?\d*|true|false|null)', fragment)
        if pairs:
            result = {}
            for k, v in pairs:
                try:
                    result[k] = json.loads(v)
                except Exception:
                    result[k] = v
            return result if result else None
    return None


def _quality_score(task_def: dict, parsed: Optional[dict], text: str) -> float:
    if parsed is None:
        return 0.0

    score = 0.0
    required = task_def.get("required_fields", [])
    valid_signals = task_def.get("valid_signals", [])

    # Field presence (4 pts)
    present = sum(1 for f in required if f in parsed and parsed[f] is not None)
    score += (present / max(len(required), 1)) * 4.0

    # Signal validity (2 pts)
    sig_field = required[0] if required else None
    if sig_field and sig_field in parsed:
        val = str(parsed[sig_field]).upper().strip('"')
        if any(val == vs or val.startswith(vs) for vs in valid_signals):
            score += 2.0

    # Numeric confidence / score in range (1 pt)
    for num_field in ["confidence", "sentiment_score", "conviction", "r_ratio"]:
        if num_field in parsed:
            try:
                v = float(parsed[num_field])
                if -1.0 <= v <= 10.0:
                    score += 1.0
                break
            except Exception:
                pass

    # Reasoning depth — word count of reasoning/argument fields (3 pts)
    reasoning_text = " ".join(
        str(parsed.get(f, ""))
        for f in ["reasoning", "argument", "recommendation", "summary", "key_driver"]
        if f in parsed
    )
    words = len(reasoning_text.split())
    if words >= 40:
        score += 3.0
    elif words >= 20:
        score += 2.0
    elif words >= 8:
        score += 1.0

    return round(min(score, 10.0), 2)


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    inp_price, out_price = PRICING.get(model, (1.0, 1.0))
    return (prompt_tokens / 1_000_000) * inp_price + (completion_tokens / 1_000_000) * out_price


def run_one(model: str, task_name: str, task_def: dict) -> ModelResult:
    try:
        raw = _call_model(model, task_def["system"], task_def["user"])
        parsed = _extract_json(raw["content"])
        required = task_def.get("required_fields", [])
        fields_ok = parsed is not None and all(f in parsed for f in required)
        sig_field = required[0] if required else None
        valid_signals = task_def.get("valid_signals", [])
        sig_valid = False
        if sig_field and parsed and sig_field in parsed:
            val = str(parsed[sig_field]).upper().strip('"')
            sig_valid = any(val == vs or val.startswith(vs) for vs in valid_signals)
        quality = _quality_score(task_def, parsed, raw["content"])
        cost = _estimate_cost(model, raw["prompt_tokens"], raw["completion_tokens"])
        return ModelResult(
            model=model,
            task=task_name,
            latency_s=round(raw["latency"], 2),
            prompt_tokens=raw["prompt_tokens"],
            completion_tokens=raw["completion_tokens"],
            response_text=raw["content"][:500],
            parsed_json=parsed,
            fields_present=fields_ok,
            signal_valid=sig_valid,
            quality_score=quality,
            cost_usd=round(cost, 6),
        )
    except Exception as e:
        return ModelResult(
            model=model, task=task_name, latency_s=0, prompt_tokens=0,
            completion_tokens=0, response_text="", parsed_json=None,
            fields_present=False, signal_valid=False, quality_score=0,
            cost_usd=0, error=str(e)[:200],
        )


# ---------------------------------------------------------------------------
# Pytest test classes
# ---------------------------------------------------------------------------

RESULTS: list[ModelResult] = []


class TestReasoningModels:
    """Test deep-think models on complex analysis tasks."""

    @pytest.mark.parametrize("model", REASONING_MODELS)
    def test_technical_analysis(self, model):
        r = run_one(model, "technical_analysis", TASKS["technical_analysis"])
        RESULTS.append(r)
        _report_one(r)
        assert r.error is None, f"API error: {r.error}"
        if not r.fields_present:
            print(f"  ⚠️  fields missing (scored lower): {r.response_text[:200]}")

    @pytest.mark.parametrize("model", REASONING_MODELS)
    def test_fundamentals_analysis(self, model):
        r = run_one(model, "fundamentals_analysis", TASKS["fundamentals_analysis"])
        RESULTS.append(r)
        _report_one(r)
        assert r.error is None, f"API error: {r.error}"
        if not r.fields_present:
            print(f"  ⚠️  fields missing (scored lower): {r.response_text[:200]}")

    @pytest.mark.parametrize("model", REASONING_MODELS)
    def test_bull_bear_debate(self, model):
        r = run_one(model, "bull_bear_debate", TASKS["bull_bear_debate"])
        RESULTS.append(r)
        _report_one(r)
        assert r.error is None, f"API error: {r.error}"

    @pytest.mark.parametrize("model", REASONING_MODELS)
    def test_research_verdict(self, model):
        r = run_one(model, "research_verdict", TASKS["research_verdict"])
        RESULTS.append(r)
        _report_one(r)
        assert r.error is None, f"API error: {r.error}"
        if not r.fields_present:
            print(f"  ⚠️  fields missing (scored lower): {r.response_text[:200]}")

    @pytest.mark.parametrize("model", REASONING_MODELS)
    def test_risk_assessment(self, model):
        r = run_one(model, "risk_assessment", TASKS["risk_assessment"])
        RESULTS.append(r)
        _report_one(r)
        assert r.error is None, f"API error: {r.error}"


class TestQuickModels:
    """Test fast models on latency-sensitive tasks."""

    @pytest.mark.parametrize("model", QUICK_MODELS)
    def test_sentiment_analysis(self, model):
        r = run_one(model, "sentiment_analysis", TASKS["sentiment_analysis"])
        RESULTS.append(r)
        _report_one(r)
        assert r.error is None, f"API error: {r.error}"
        if not r.fields_present:
            print(f"  ⚠️  fields missing (scored lower): {r.response_text[:200]}")

    @pytest.mark.parametrize("model", QUICK_MODELS)
    def test_news_summary(self, model):
        r = run_one(model, "news_summary", TASKS["news_summary"])
        RESULTS.append(r)
        _report_one(r)
        assert r.error is None, f"API error: {r.error}"

    @pytest.mark.parametrize("model", QUICK_MODELS)
    def test_trade_planning(self, model):
        r = run_one(model, "trade_planning", TASKS["trade_planning"])
        RESULTS.append(r)
        _report_one(r)
        assert r.error is None, f"API error: {r.error}"
        if not r.fields_present:
            print(f"  ⚠️  fields missing (scored lower): {r.response_text[:200]}")


class TestCrossComparison:
    """Run all models on the most critical task (research_verdict) for head-to-head."""

    @pytest.mark.parametrize("model", ALL_MODELS)
    def test_research_verdict_all_models(self, model):
        r = run_one(model, "research_verdict_all", TASKS["research_verdict"])
        RESULTS.append(r)
        _report_one(r)
        assert r.error is None, f"API error: {r.error}"


# ---------------------------------------------------------------------------
# Reporting helpers
# ---------------------------------------------------------------------------

def _report_one(r: ModelResult):
    short = r.model.split("/")[-1][:28]
    status = "✅" if r.fields_present and r.error is None else ("⚠️" if r.error is None else "❌")
    cost_str = f"${r.cost_usd:.5f}" if r.cost_usd > 0 else "FREE"
    qc = f"{r.quality_score/max(r.cost_usd*1000, 0.001):.0f}" if r.cost_usd > 0 else "∞"
    ql = f"{r.quality_score/max(r.latency_s, 0.1):.2f}"
    print(
        f"\n  {status} [{r.task[:22]:22}] {short:28} "
        f"q={r.quality_score:4.1f}/10  "
        f"lat={r.latency_s:5.1f}s  "
        f"cost={cost_str:10}  "
        f"q/cost={qc:>6}  q/lat={ql}"
    )
    if r.error:
        print(f"     ERROR: {r.error}")


def pytest_sessionfinish(session, exitstatus):
    if not RESULTS:
        return

    print("\n\n" + "═" * 80)
    print("  MOONSHOTX MODEL BENCHMARK — FINAL REPORT")
    print("═" * 80)

    # Aggregate per model
    from collections import defaultdict
    agg = defaultdict(lambda: {"quality": [], "latency": [], "cost": [], "pass": 0, "total": 0})
    for r in RESULTS:
        m = r.model
        agg[m]["quality"].append(r.quality_score)
        agg[m]["latency"].append(r.latency_s)
        agg[m]["cost"].append(r.cost_usd)
        agg[m]["total"] += 1
        if r.fields_present and r.error is None:
            agg[m]["pass"] += 1

    def avg(lst):
        return sum(lst) / len(lst) if lst else 0

    print(f"\n{'Model':<42} {'AvgQ':>6} {'AvgLat':>7} {'AvgCost':>10} {'Pass':>6} {'Q/Cost':>8} {'Q/Lat':>7}")
    print("-" * 88)

    rows = []
    for model, d in agg.items():
        aq = avg(d["quality"])
        al = avg(d["latency"])
        ac = avg(d["cost"])
        pass_rate = d["pass"] / max(d["total"], 1)
        qc = aq / max(ac * 1000, 0.001) if ac > 0 else float("inf")
        ql = aq / max(al, 0.1)
        rows.append((model, aq, al, ac, pass_rate, qc, ql))

    rows.sort(key=lambda x: x[1], reverse=True)  # sort by avg quality
    for model, aq, al, ac, pr, qc, ql in rows:
        cost_str = f"${ac:.5f}" if ac > 0 else "FREE"
        qc_str = f"{qc:.0f}" if qc != float("inf") else "∞"
        cat = "REASON" if model in REASONING_MODELS else "QUICK"
        print(
            f"  [{cat}] {model:<38} {aq:>6.2f} {al:>6.1f}s {cost_str:>10} "
            f"{pr:>5.0%} {qc_str:>8} {ql:>6.2f}"
        )

    # Recommendations
    print("\n" + "─" * 80)
    print("  RECOMMENDED ASSIGNMENTS")
    print("─" * 80)

    reason_rows = [(m, aq, al, ac, qc, ql) for (m, aq, al, ac, _, qc, ql) in rows if m in REASONING_MODELS]
    quick_rows  = [(m, aq, al, ac, qc, ql) for (m, aq, al, ac, _, qc, ql) in rows if m in QUICK_MODELS]

    if reason_rows:
        best_r = max(reason_rows, key=lambda x: x[1])
        fast_r = min(reason_rows, key=lambda x: x[2])
        eff_r  = max(reason_rows, key=lambda x: x[4])
        print(f"\n  REASONING TIER:")
        print(f"    Best quality  → {best_r[0]}  (q={best_r[1]:.2f})")
        print(f"    Best latency  → {fast_r[0]}  (lat={fast_r[2]:.1f}s)")
        print(f"    Best q/cost   → {eff_r[0]}   (q/cost={eff_r[4]:.0f})")
        print(f"\n  → DEEP_MODEL assignment: {best_r[0]}")

    if quick_rows:
        best_q  = max(quick_rows, key=lambda x: x[1])
        fast_q  = min(quick_rows, key=lambda x: x[2])
        eff_q   = max(quick_rows, key=lambda x: x[4])
        print(f"\n  QUICK TIER:")
        print(f"    Best quality  → {best_q[0]}  (q={best_q[1]:.2f})")
        print(f"    Best latency  → {fast_q[0]}  (lat={fast_q[2]:.1f}s)")
        print(f"    Best q/cost   → {eff_q[0]}   (q/cost={eff_q[4]:.0f})")
        print(f"\n  → QUICK_MODEL assignment: {fast_q[0]}")

    print("\n" + "═" * 80 + "\n")
