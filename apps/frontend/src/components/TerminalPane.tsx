import { useCallback, useEffect, useRef, useState } from "react";
import { Terminal } from "xterm";
import { FitAddon } from "xterm-addon-fit";
import "xterm/css/xterm.css";

import { getProjectId } from "../lib/project";

type Props = {
  hostId: number | null;
  token: string | null;
  disabled?: boolean;
  height?: number;
};

function TerminalPane({ hostId, token, disabled, height = 360 }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const termRef = useRef<Terminal | null>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const onDataDisposeRef = useRef<(() => void) | null>(null);
  const [connStatus, setConnStatus] = useState<string>("disconnected");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fitAddon = new FitAddon();
    const term = new Terminal({
      convertEol: true,
      cursorBlink: true,
      theme: { background: "#0f172a" },
      fontSize: 14,
      scrollback: 5000,
    });
    term.loadAddon(fitAddon);
    termRef.current = term;
    fitRef.current = fitAddon;
    if (containerRef.current) {
      term.open(containerRef.current);
      fitAddon.fit();
      term.focus();
    }
    return () => {
      fitRef.current = null;
      term.dispose();
    };
  }, []);

  const disconnect = () => {
    socketRef.current?.close();
    socketRef.current = null;
    setConnStatus("disconnected");
  };

  const sendResize = useCallback(() => {
    const term = termRef.current;
    const ws = socketRef.current;
    const fit = fitRef.current;
    if (!term || !ws || ws.readyState !== WebSocket.OPEN || !fit) return;
    fit.fit();
    ws.send(JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }));
  }, []);

  useEffect(() => {
    if (!hostId || !token || disabled) {
      disconnect();
      return;
    }
    setError(null);
    const base = window.location.origin.replace(/^http/, "ws");
    const projectId = getProjectId();
    const qs = new URLSearchParams({ token });
    if (projectId) qs.set("project_id", String(projectId));
    const ws = new WebSocket(`${base}/api/v1/hosts/${hostId}/terminal?${qs.toString()}`);
    socketRef.current = ws;
    setConnStatus("connecting");

    ws.onopen = () => {
      setConnStatus("connected");
      termRef.current?.reset();
      termRef.current?.focus();
      termRef.current?.write(`\r\nПодключено к host ${hostId}\r\n`);
      sendResize();
      // Чистим предыдущий обработчик, чтобы не дублировать отправку
      onDataDisposeRef.current?.();
      const disposable = termRef.current?.onData((data) => {
        ws.send(data);
      });
      onDataDisposeRef.current = () => disposable?.dispose();
    };
    ws.onmessage = (event) => {
      termRef.current?.write(event.data);
    };
    ws.onerror = () => {
      setError("Ошибка WebSocket/SSH");
      setConnStatus("error");
    };
    ws.onclose = (evt) => {
      setConnStatus("disconnected");
      if (evt.reason) {
        setError(`Соединение закрыто: ${evt.reason}`);
      }
    };

    return () => {
      ws.close();
    };
  }, [hostId, token, disabled, sendResize]);

  useEffect(() => {
    if (connStatus !== "connected") return;
    sendResize();
    const onResize = () => sendResize();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [connStatus, height, sendResize]);

  return (
    <div className="terminal-wrapper">
      <div className="panel-title">
        <h2>Терминал</h2>
        <p className="form-helper">Статус: {connStatus}</p>
      </div>
      {error && <p className="text-error">{error}</p>}
      {!token && <p className="text-error">Нужно войти в Settings для подключения.</p>}
      {!hostId && <p>Выберите хост и нажмите «Terminal».</p>}
      <div className="terminal-container" ref={containerRef} style={{ height }} />
      {error && <p className="text-error">{error}</p>}
    </div>
  );
}

export default TerminalPane;
