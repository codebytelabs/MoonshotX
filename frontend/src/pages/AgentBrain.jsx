import React, { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import { useWebSocket } from '../hooks/useWebSocket';
import { Check, X, Clock, Brain, ChevronRight } from 'lucide-react';
import { formatLocalDateTime, formatLocalTime, LOCAL_TZ_ABBR } from '../utils/time';

const API = process.env.REACT_APP_BACKEND_URL + '/api';

const AGENT_NODES = [
  { id: 'technical', name: 'Technical Analyst', tier: 'Q', role: 'analyst', col: 0, row: 0 },
  { id: 'news', name: 'News Analyst', tier: 'Q', role: 'analyst', col: 0, row: 1 },
  { id: 'sentiment', name: 'Sentiment Analyst', tier: 'Q', role: 'analyst', col: 0, row: 2 },
  { id: 'fundamentals', name: 'Fundamentals Analyst', tier: 'Q', role: 'analyst', col: 0, row: 3 },
  { id: 'bull', name: 'Bull Researcher', tier: 'Q', role: 'researcher', col: 1, row: 0 },
  { id: 'bear', name: 'Bear Researcher', tier: 'Q', role: 'researcher', col: 1, row: 1 },
  { id: 'research_manager', name: 'Research Manager', tier: 'D', role: 'manager', col: 1, row: 2 },
  { id: 'trader', name: 'Trader', tier: 'Q', role: 'trader', col: 2, row: 0 },
  { id: 'aggressive', name: 'Aggressive Analyst', tier: 'Q', role: 'risk', col: 2, row: 1 },
  { id: 'neutral', name: 'Neutral Analyst', tier: 'Q', role: 'risk', col: 2, row: 2 },
  { id: 'conservative', name: 'Conservative Analyst', tier: 'Q', role: 'risk', col: 2, row: 3 },
  { id: 'portfolio_manager', name: 'Portfolio Manager', tier: 'D', role: 'manager', col: 3, row: 1 },
];

const ROLE_COLORS = {
  analyst: 'rgba(0,229,255,0.15)',
  researcher: 'rgba(255,204,0,0.12)',
  manager: 'rgba(0,255,135,0.12)',
  trader: 'rgba(255,165,0,0.12)',
  risk: 'rgba(255,59,48,0.1)',
};

const ROLE_BORDER = {
  analyst: 'rgba(0,229,255,0.3)',
  researcher: 'rgba(255,204,0,0.3)',
  manager: 'rgba(0,255,135,0.3)',
  trader: 'rgba(255,165,0,0.3)',
  risk: 'rgba(255,59,48,0.3)',
};

function AgentCard({ agent, status, result }) {
  const isRunning = status === 'running';
  const isComplete = status === 'complete';
  const signal = result?.signal || result?.verdict || result?.decision;
  const signalColor = signal === 'BULLISH' || signal === 'APPROVE' ? 'var(--success)' : signal === 'BEARISH' || signal === 'REJECT' ? 'var(--danger)' : 'var(--warning)';

  return (
    <div style={{
      background: isRunning ? 'rgba(0,229,255,0.08)' : ROLE_COLORS[agent.role],
      border: `1px solid ${isRunning ? 'var(--border-active)' : isComplete ? ROLE_BORDER[agent.role] : 'var(--border)'}`,
      padding: '8px 10px',
      transition: 'all 150ms ease',
      boxShadow: isRunning ? '0 0 8px rgba(0,229,255,0.2)' : 'none',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 2 }}>
        <div style={{ fontSize: 11, fontFamily: 'JetBrains Mono', fontWeight: 600, color: isRunning ? 'var(--primary)' : 'var(--text-secondary)' }}>
          {agent.name.split(' ')[0]}
          {agent.tier === 'D' && <span style={{ marginLeft: 4, fontSize: 8, color: '#00FF87', background: 'rgba(0,255,135,0.15)', padding: '1px 3px' }}>DEEP</span>}
        </div>
        {isRunning && <div className="agent-running" style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--primary)' }} />}
        {isComplete && signal && <span style={{ fontSize: 9, color: signalColor, fontFamily: 'JetBrains Mono' }}>{signal?.slice(0, 4)}</span>}
      </div>
      <div style={{ fontSize: 9, color: 'var(--text-muted)', letterSpacing: '0.08em' }}>
        {agent.name.split(' ').slice(1).join(' ')}
      </div>
      {isComplete && result?.confidence !== undefined && (
        <div style={{ marginTop: 4 }}>
          <div style={{ height: 2, background: 'var(--border)' }}>
            <div style={{ height: '100%', width: `${(result.confidence || 0) * 100}%`, background: signalColor, transition: 'width 0.5s ease' }} />
          </div>
        </div>
      )}
    </div>
  );
}

export default function AgentBrain() {
  const { lastEvent } = useWebSocket();
  const [agentLogs, setAgentLogs] = useState([]);
  const [selectedLog, setSelectedLog] = useState(null);
  const [liveAgents, setLiveAgents] = useState({});
  const [liveActivity, setLiveActivity] = useState([]);
  const logRef = useRef(null);
  const [analyzeTicker, setAnalyzeTicker] = useState('');
  const [analyzing, setAnalyzing] = useState(false);

  const fetchLogs = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/agent-logs?limit=15`);
      setAgentLogs(r.data);
    } catch (e) {}
  }, []);

  useEffect(() => {
    fetchLogs();
    const interval = setInterval(fetchLogs, 15000);
    return () => clearInterval(interval);
  }, [fetchLogs]);

  useEffect(() => {
    if (!lastEvent) return;
    if (lastEvent.type === 'agent_activity') {
      const agentKey = lastEvent.agent.toLowerCase().replace(/\s+/g, '_');
      setLiveAgents(prev => ({
        ...prev,
        [agentKey]: { status: lastEvent.status, result: lastEvent.data, ticker: lastEvent.ticker },
      }));
      setLiveActivity(prev => [lastEvent, ...prev.slice(0, 49)]);
      if (logRef.current) logRef.current.scrollTop = 0;
    }
    if (lastEvent.type === 'pipeline_start') {
      setLiveAgents({});
      setLiveActivity([]);
    }
    if (lastEvent.type === 'pipeline_complete') {
      setTimeout(fetchLogs, 2000);
    }
  }, [lastEvent, fetchLogs]);

  const handleManualAnalyze = async () => {
    if (!analyzeTicker.trim()) return;
    setAnalyzing(true);
    setLiveAgents({});
    setLiveActivity([]);
    try {
      const r = await axios.post(`${API}/trading/analyze/${analyzeTicker.toUpperCase()}`);
      await fetchLogs();
      if (r.data.decision_id) {
        setSelectedLog(await axios.get(`${API}/agent-logs/${r.data.decision_id}`).then(rr => rr.data));
      }
    } catch (e) {}
    setAnalyzing(false);
  };

  const selectLog = async (log) => {
    try {
      const r = await axios.get(`${API}/agent-logs/${log.decision_id}`);
      setSelectedLog(r.data);
    } catch (e) {}
  };

  const agentStatuses = {};
  AGENT_NODES.forEach(a => {
    const key = a.id.replace(/\s+/g, '_').toLowerCase();
    const liveKey = Object.keys(liveAgents).find(k => k.includes(a.id) || a.name.toLowerCase().includes(k.split('_')[0]));
    agentStatuses[a.id] = liveAgents[liveKey] || {};
  });

  return (
    <div style={{ padding: 24, height: 'calc(100vh - 52px)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20, flexShrink: 0 }}>
        <div>
          <h1 style={{ fontFamily: 'JetBrains Mono', fontSize: 20, fontWeight: 700, letterSpacing: '0.08em' }}>AGENT BRAIN</h1>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>12-agent autonomous decision pipeline</div>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            value={analyzeTicker}
            onChange={e => setAnalyzeTicker(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === 'Enter' && handleManualAnalyze()}
            placeholder="TICKER"
            data-testid="analyze-ticker-input"
            style={{
              background: 'var(--surface)', border: '1px solid var(--border)',
              color: 'var(--text-primary)', padding: '7px 12px',
              fontFamily: 'JetBrains Mono', fontSize: 12, width: 100,
              outline: 'none',
            }}
          />
          <button
            onClick={handleManualAnalyze}
            disabled={analyzing || !analyzeTicker}
            data-testid="analyze-trigger-btn"
            style={{
              background: 'rgba(0,229,255,0.1)', border: '1px solid var(--border-active)',
              color: 'var(--primary)', padding: '7px 16px',
              fontFamily: 'JetBrains Mono', fontSize: 11, fontWeight: 700, letterSpacing: '0.1em',
              cursor: analyzing || !analyzeTicker ? 'not-allowed' : 'pointer',
              opacity: analyzing ? 0.6 : 1,
            }}
          >
            {analyzing ? 'ANALYZING...' : 'ANALYZE'}
          </button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, flex: 1, overflow: 'hidden', minHeight: 0 }}>
        {/* Left: Pipeline + Log list */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, overflow: 'hidden' }}>
          {/* Agent Pipeline Grid */}
          <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', padding: 16, flexShrink: 0 }}>
            <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'JetBrains Mono', letterSpacing: '0.15em', marginBottom: 12 }}>
              AGENT PIPELINE
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6 }}>
              {[0, 1, 2, 3].map(col => (
                <div key={col} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {AGENT_NODES.filter(a => a.col === col).map(agent => {
                    const live = liveAgents[Object.keys(liveAgents).find(k => agent.name.toLowerCase().includes(k.replace(/_/g, ' '))) || agent.id];
                    return (
                      <AgentCard
                        key={agent.id}
                        agent={agent}
                        status={live?.status}
                        result={live?.result}
                      />
                    );
                  })}
                </div>
              ))}
            </div>
          </div>

          {/* Decision Log List */}
          <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', fontSize: 10, color: 'var(--text-muted)', fontFamily: 'JetBrains Mono', letterSpacing: '0.15em', flexShrink: 0 }}>
              DECISION HISTORY ({agentLogs.length})
            </div>
            <div style={{ overflow: 'auto', flex: 1 }}>
              {agentLogs.length === 0 ? (
                <div style={{ padding: 20, color: 'var(--text-muted)', fontSize: 12, fontFamily: 'JetBrains Mono' }}>NO DECISIONS YET</div>
              ) : agentLogs.map(log => (
                <div
                  key={log.decision_id}
                  onClick={() => selectLog(log)}
                  data-testid={`log-row-${log.ticker}`}
                  style={{
                    padding: '10px 16px', borderBottom: '1px solid rgba(255,255,255,0.04)',
                    cursor: 'pointer',
                    background: selectedLog?.decision_id === log.decision_id ? 'rgba(0,229,255,0.05)' : 'transparent',
                  }}
                  className="table-row-hover"
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontFamily: 'JetBrains Mono', fontWeight: 600, fontSize: 13 }}>{log.ticker}</span>
                      <span style={{
                        fontSize: 9, padding: '1px 5px', border: '1px solid', letterSpacing: '0.1em', fontFamily: 'JetBrains Mono',
                        color: log.decision === 'APPROVE' ? 'var(--success)' : 'var(--danger)',
                        borderColor: log.decision === 'APPROVE' ? 'rgba(0,255,135,0.3)' : 'rgba(255,59,48,0.3)',
                        background: log.decision === 'APPROVE' ? 'rgba(0,255,135,0.08)' : 'rgba(255,59,48,0.08)',
                      }}>{log.decision}</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <span style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'JetBrains Mono' }}>{log.duration_s}s</span>
                      <ChevronRight size={12} color="var(--text-muted)" />
                    </div>
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
                    {log.regime?.toUpperCase() || 'N/A'} &nbsp;•&nbsp; Bayesian: {log.bayesian_score != null ? (log.bayesian_score * 100).toFixed(0) + '%' : '—'}
                    &nbsp;•&nbsp; {log.created_at ? formatLocalDateTime(log.created_at) : ''}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right: Debate Log / Live Activity */}
        <div className="terminal-bg" style={{
          border: '1px solid rgba(0,229,255,0.15)', overflow: 'auto', display: 'flex', flexDirection: 'column',
        }}>
          <div ref={logRef} style={{ padding: 16, flex: 1, overflow: 'auto' }}>
            <div style={{ fontSize: 10, color: 'var(--primary)', fontFamily: 'JetBrains Mono', letterSpacing: '0.15em', marginBottom: 12 }}>
              {selectedLog ? `> DECISION LOG — ${selectedLog.ticker} — ${selectedLog.decision}` : '> LIVE AGENT STREAM'}
            </div>

            {/* Live activity feed */}
            {liveActivity.length > 0 && !selectedLog && (
              <div>
                {liveActivity.map((evt, i) => (
                  <div key={i} style={{ marginBottom: 12 }}>
                    <div style={{ fontFamily: 'JetBrains Mono', fontSize: 11 }}>
                      <span style={{ color: 'var(--text-muted)' }}>[{formatLocalTime(evt.ts)}] </span>
                      <span style={{ color: 'var(--primary)' }}>{evt.agent}</span>
                      <span style={{ color: 'var(--text-muted)' }}> on </span>
                      <span style={{ color: 'var(--warning)' }}>{evt.ticker}</span>
                      <span style={{ color: evt.status === 'running' ? 'var(--primary)' : 'var(--success)' }}> → {evt.status.toUpperCase()}</span>
                    </div>
                    {evt.data?.analysis && (
                      <div style={{ fontFamily: 'JetBrains Mono', fontSize: 10, color: 'var(--text-secondary)', marginTop: 4, paddingLeft: 16, lineHeight: 1.6 }}>
                        {evt.data.analysis}
                      </div>
                    )}
                    {evt.data?.signal && (
                      <div style={{ fontFamily: 'JetBrains Mono', fontSize: 10, marginTop: 2, paddingLeft: 16 }}>
                        <span style={{ color: 'var(--text-muted)' }}>SIGNAL: </span>
                        <span style={{ color: evt.data.signal === 'BULLISH' ? 'var(--success)' : evt.data.signal === 'BEARISH' ? 'var(--danger)' : 'var(--warning)' }}>
                          {evt.data.signal}
                        </span>
                        {evt.data.confidence !== undefined && (
                          <span style={{ color: 'var(--text-muted)' }}> ({(evt.data.confidence * 100).toFixed(0)}% confidence)</span>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Selected log detail */}
            {selectedLog && (
              <div>
                <div style={{ fontFamily: 'JetBrains Mono', fontSize: 11, color: 'var(--text-muted)', marginBottom: 12 }}>
                  Regime: {selectedLog.regime?.toUpperCase()} &nbsp;|&nbsp; Duration: {selectedLog.duration_s}s &nbsp;|&nbsp;
                  Bayesian: {selectedLog.bayesian_score != null ? (selectedLog.bayesian_score * 100).toFixed(0) + '%' : '—'}
                </div>
                {selectedLog.agents?.map((entry, i) => (
                  <div key={i} style={{ marginBottom: 14, borderLeft: '2px solid rgba(0,229,255,0.2)', paddingLeft: 12 }}>
                    <div style={{ fontFamily: 'JetBrains Mono', fontSize: 11, color: 'var(--primary)', marginBottom: 4 }}>
                      [{String(i + 1).padStart(2, '0')}] {entry.agent?.toUpperCase()}
                    </div>
                    {entry.result && Object.entries(entry.result).map(([k, v]) => {
                      if (typeof v === 'object') return null;
                      const color = k === 'signal' || k === 'verdict' ? (v === 'BULLISH' || v === 'APPROVE' ? 'var(--success)' : v === 'BEARISH' || v === 'REJECT' ? 'var(--danger)' : 'var(--warning)') : 'var(--text-secondary)';
                      return (
                        <div key={k} style={{ fontFamily: 'JetBrains Mono', fontSize: 10, lineHeight: 1.7, paddingLeft: 8 }}>
                          <span style={{ color: 'var(--text-muted)' }}>{k}: </span>
                          <span style={{ color }}>{String(v)}</span>
                        </div>
                      );
                    })}
                  </div>
                ))}
                {selectedLog.reasoning && (
                  <div style={{ marginTop: 12, padding: 12, border: '1px solid rgba(0,229,255,0.2)', background: 'rgba(0,229,255,0.04)' }}>
                    <div style={{ fontFamily: 'JetBrains Mono', fontSize: 10, color: 'var(--primary)', marginBottom: 6 }}>FINAL REASONING</div>
                    <div style={{ fontFamily: 'JetBrains Mono', fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.7 }}>{selectedLog.reasoning}</div>
                  </div>
                )}
              </div>
            )}

            {liveActivity.length === 0 && !selectedLog && (
              <div style={{ color: 'var(--text-muted)', fontFamily: 'JetBrains Mono', fontSize: 11 }}>
                Waiting for agent activity...
                <br /><br />
                Start the trading system or manually trigger an analysis above.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
