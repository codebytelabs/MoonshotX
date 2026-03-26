import { useEffect, useRef, useState, useCallback } from 'react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const WS_URL = BACKEND_URL.replace(/^https/, 'wss').replace(/^http/, 'ws') + '/ws';

export function useWebSocket() {
  const wsRef = useRef(null);
  const timerRef = useRef(null);
  const [connected, setConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    try {
      wsRef.current = new WebSocket(WS_URL);

      wsRef.current.onopen = () => setConnected(true);

      wsRef.current.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          if (data.type !== 'ping') setLastEvent(data);
        } catch (_) {}
      };

      wsRef.current.onclose = () => {
        setConnected(false);
        timerRef.current = setTimeout(connect, 3000);
      };

      wsRef.current.onerror = () => {
        wsRef.current?.close();
      };
    } catch (e) {
      timerRef.current = setTimeout(connect, 5000);
    }
  }, []);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(timerRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { connected, lastEvent };
}
