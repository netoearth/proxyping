import React, {useCallback, useEffect, useState} from 'react';
import {IpSourcesPanel} from './components/IpSourcesPanel';
import {TelegramProxyWindow} from './components/TelegramProxyWindow';
import type {ProxyEntry} from './types/proxy';

const INITIAL_PROXIES: ProxyEntry[] = [
  {
    id: 'p1',
    protocol: 'SOCKS5',
    host: '127.0.0.1',
    port: 4526,
    secret: '',
    username: '',
    password: '',
    status: 'untested',
    latencyMs: null,
    detail: '',
  },
  {
    id: 'p2',
    protocol: 'SOCKS5',
    host: '127.0.0.1',
    port: 40000,
    secret: '',
    username: '',
    password: '',
    status: 'untested',
    latencyMs: null,
    detail: '',
  },
  {
    id: 'p3',
    protocol: 'SOCKS5',
    host: '127.0.0.1',
    port: 9050,
    secret: '',
    username: '',
    password: '',
    status: 'untested',
    latencyMs: null,
    detail: '',
  },
  {
    id: 'p4',
    protocol: 'SOCKS5',
    host: '127.0.0.1',
    port: 10240,
    secret: '',
    username: '',
    password: '',
    status: 'untested',
    latencyMs: null,
    detail: '',
  },
  {
    id: 'p5',
    protocol: 'SOCKS5',
    host: '127.0.0.1',
    port: 9909,
    secret: '',
    username: '',
    password: '',
    status: 'untested',
    latencyMs: null,
    detail: '',
  },
];

export default function App() {
  const [proxies, setProxies] = useState<ProxyEntry[]>(INITIAL_PROXIES);
  const [selectedId, setSelectedId] = useState<string | null>('p5');
  const [targetHost, setTargetHost] = useState('cp.cloudflare.com');
  const [targetPort, setTargetPort] = useState(80);
  const [systemProxies, setSystemProxies] = useState<
    Array<{protocol: string; host: string; port: number}>
  >([]);

  const testProxyByEntry = useCallback(
    async (entry: ProxyEntry, tHost = targetHost, tPort = targetPort) => {
      setProxies((prev) =>
        prev.map((p) =>
          p.id === entry.id ? {...p, status: 'testing', latencyMs: null, detail: ''} : p,
        ),
      );

      try {
        const res = await fetch('/api/test-proxy', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            protocol: entry.protocol,
            host: entry.host,
            port: entry.port,
            secret: entry.secret,
            username: entry.username,
            password: entry.password,
            targetHost: tHost,
            targetPort: tPort,
          }),
        });
        const data = (await res.json()) as {
          available: boolean;
          latencyMs: number | null;
          detail: string;
        };

        setProxies((prev) =>
          prev.map((p) =>
            p.id === entry.id
              ? {
                  ...p,
                  status: data.available ? 'available' : 'unavailable',
                  latencyMs: data.latencyMs,
                  detail: data.detail,
                }
              : p,
          ),
        );
      } catch {
        setProxies((prev) =>
          prev.map((p) =>
            p.id === entry.id
              ? {...p, status: 'unavailable', latencyMs: null, detail: '探测服务请求失败'}
              : p,
          ),
        );
      }
    },
    [targetHost, targetPort],
  );

  useEffect(() => {
    fetch('/api/system-proxies')
      .then((r) => r.json())
      .then((data) => setSystemProxies(data.detected || []))
      .catch(() => {});
  }, []);

  const handleTestOne = (id: string) => {
    const found = proxies.find((p) => p.id === id);
    if (found) {
      void testProxyByEntry(found);
    }
  };

  const handleTestAll = () => {
    proxies.forEach((p) => {
      void testProxyByEntry(p);
    });
  };

  const handleSaveProxy = (updated: ProxyEntry, isNew: boolean) => {
    if (isNew) {
      setProxies((prev) => [...prev, updated]);
      setSelectedId(updated.id);
    } else {
      setProxies((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
    }
    void testProxyByEntry(updated);
  };

  const handleDeleteProxy = (id: string) => {
    setProxies((prev) => {
      const next = prev.filter((p) => p.id !== id);
      if (selectedId === id) {
        setSelectedId(next[0]?.id ?? null);
      }
      return next;
    });
  };

  const handleClearUnavailable = () => {
    setProxies((prev) => {
      const next = prev.filter((p) => p.status !== 'unavailable');
      if (selectedId && !next.some((p) => p.id === selectedId)) {
        setSelectedId(next[0]?.id ?? null);
      }
      return next;
    });
  };

  const handleUpdateTarget = (host: string, port: number) => {
    setTargetHost(host);
    setTargetPort(port);
    proxies.forEach((p) => {
      void testProxyByEntry(p, host, port);
    });
  };

  const handleImportUri = (raw: string): boolean => {
    const text = raw.trim();
    if (!text) return false;
    try {
      let entry: ProxyEntry | null = null;
      if (text.startsWith('tg://proxy') || text.startsWith('https://t.me/proxy')) {
        const u = new URL(text.replace(/^tg:\/\//, 'https://'));
        const host = u.searchParams.get('server') || '';
        const port = Number(u.searchParams.get('port') || '443');
        const secret = u.searchParams.get('secret') || '';
        if (host && port > 0) {
          entry = {
            id: `p_${Date.now()}`,
            protocol: 'MTPROTO',
            host,
            port,
            secret,
            username: '',
            password: '',
            status: 'untested',
            latencyMs: null,
            detail: '',
          };
        }
      } else {
        const normalized = text.includes('://') ? text : `socks5://${text}`;
        const u = new URL(normalized);
        const port = Number(u.port);
        if (u.hostname && port > 0 && port <= 65535) {
          const proto = u.protocol.includes('socks')
            ? 'SOCKS5'
            : u.protocol.startsWith('https')
              ? 'WEB'
              : 'HTTP';
          entry = {
            id: `p_${Date.now()}`,
            protocol: proto,
            host: u.hostname,
            port,
            secret: '',
            username: decodeURIComponent(u.username || ''),
            password: decodeURIComponent(u.password || ''),
            status: 'untested',
            latencyMs: null,
            detail: '',
          };
        }
      }
      if (!entry) return false;
      handleSaveProxy(entry, true);
      return true;
    } catch {
      return false;
    }
  };

  const selectedProxy = proxies.find((p) => p.id === selectedId) ?? null;

  return (
    <div className="min-h-screen bg-[#131a22] text-[#f3f6f9] flex flex-col justify-center py-6 px-4 sm:px-6">
      <div className="max-w-[1160px] w-full mx-auto">
        {/* Compact GUI Title Bar */}
        <div className="flex flex-wrap items-center justify-between gap-4 mb-5 px-1">
          <h1 className="text-[18px] font-semibold text-[#f5f5f5] tracking-tight">
            ProxyPing · 网络代理连通性与多源 IP 检测
          </h1>
          <div className="text-[12.5px] text-[#7f91a4]">
            MTPROTO · SOCKS5 · HTTP · WEB · 多源出口 IP 对比
          </div>
        </div>

        {/* Pure Dual-Pane Desktop GUI */}
        <div className="grid grid-cols-1 lg:grid-cols-[400px_1fr] gap-6 items-start">
          <TelegramProxyWindow
            proxies={proxies}
            selectedId={selectedId}
            targetHost={targetHost}
            targetPort={targetPort}
            systemProxies={systemProxies}
            onSelectProxy={(id) => {
              setSelectedId(id);
            }}
            onTestProxy={handleTestOne}
            onTestAll={handleTestAll}
            onSaveProxy={handleSaveProxy}
            onDeleteProxy={handleDeleteProxy}
            onClearUnavailable={handleClearUnavailable}
            onUpdateTarget={handleUpdateTarget}
            onImportUri={handleImportUri}
          />

          <IpSourcesPanel selectedProxy={selectedProxy} />
        </div>
      </div>
    </div>
  );
}
