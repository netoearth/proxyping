import React, {useCallback, useEffect, useState} from 'react';
import {Check, Copy, RotateCw} from 'lucide-react';
import type {IpRouteMode, IpSourceResult, ProxyEntry} from '../types/proxy';

interface IpSourcesPanelProps {
  selectedProxy: ProxyEntry | null;
}

interface SourceDefinition {
  id: string;
  name: string;
  region: string;
  browserDirect: boolean;
}

const SOURCE_DEFS: SourceDefinition[] = [
  {id: 'pconline', name: '太平洋电脑网', region: '国内来源', browserDirect: false},
  {id: 'ip_sb', name: 'IP.SB', region: '国际来源', browserDirect: true},
  {id: 'cf_trace', name: 'Cloudflare Trace', region: 'CDN 节点', browserDirect: true},
  {id: 'ipify', name: 'ipify IPv4', region: '国际来源', browserDirect: true},
  {id: 'ipwho', name: 'ipwho.is', region: '全球节点', browserDirect: true},
  {id: 'ipinfo', name: 'IPinfo.io', region: '国际来源', browserDirect: true},
  {id: 'ip_api', name: 'IP-API', region: '国际来源', browserDirect: false},
];

async function queryBrowserDirect(id: string): Promise<Omit<IpSourceResult, 'id' | 'name' | 'region'>> {
  const start = performance.now();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 5000);

  try {
    if (id === 'cf_trace') {
      const resp = await fetch('https://www.cloudflare.com/cdn-cgi/trace', {signal: controller.signal});
      const text = await resp.text();
      const latencyMs = Math.max(1, Math.round(performance.now() - start));
      const map: Record<string, string> = {};
      for (const line of text.split(/\r?\n/)) {
        const idx = line.indexOf('=');
        if (idx > 0) map[line.slice(0, idx)] = line.slice(idx + 1);
      }
      if (!map.ip) throw new Error('未能解析 Cloudflare Trace');
      return {
        status: 'ok',
        ip: map.ip,
        location: map.colo ? `${map.loc || ''} (${map.colo})`.trim() : map.loc || '',
        isp: 'Cloudflare Edge',
        latencyMs,
        error: '',
      };
    }

    if (id === 'ip_sb') {
      const resp = await fetch('https://api.ip.sb/geoip', {signal: controller.signal});
      const data = (await resp.json()) as Record<string, unknown>;
      const latencyMs = Math.max(1, Math.round(performance.now() - start));
      return {
        status: 'ok',
        ip: String(data.ip || ''),
        location: [data.country, data.city].filter(Boolean).join(' · '),
        isp: String(data.organization || data.isp || ''),
        latencyMs,
        error: '',
      };
    }

    if (id === 'ipify') {
      const resp = await fetch('https://api.ipify.org?format=json', {signal: controller.signal});
      const data = (await resp.json()) as Record<string, unknown>;
      const latencyMs = Math.max(1, Math.round(performance.now() - start));
      return {
        status: 'ok',
        ip: String(data.ip || ''),
        location: 'IPv4 出口验证',
        isp: 'ipify',
        latencyMs,
        error: '',
      };
    }

    if (id === 'ipwho') {
      const resp = await fetch('https://ipwho.is/', {signal: controller.signal});
      const data = (await resp.json()) as Record<string, unknown>;
      const latencyMs = Math.max(1, Math.round(performance.now() - start));
      const conn = (data.connection as Record<string, unknown> | undefined) || {};
      return {
        status: 'ok',
        ip: String(data.ip || ''),
        location: [data.country, data.city].filter(Boolean).join(' · '),
        isp: String(conn.isp || conn.org || ''),
        latencyMs,
        error: '',
      };
    }

    if (id === 'ipinfo') {
      const resp = await fetch('https://ipinfo.io/json', {signal: controller.signal});
      const data = (await resp.json()) as Record<string, unknown>;
      const latencyMs = Math.max(1, Math.round(performance.now() - start));
      return {
        status: 'ok',
        ip: String(data.ip || ''),
        location: [data.country, data.region, data.city].filter(Boolean).join(' · '),
        isp: String(data.org || ''),
        latencyMs,
        error: '',
      };
    }

    throw new Error('该来源需由后端路由探测');
  } catch (err) {
    const latencyMs = Math.max(1, Math.round(performance.now() - start));
    const message = err instanceof Error && err.name === 'AbortError' ? '请求超时' : (err instanceof Error ? err.message : '请求失败');
    return {
      status: 'error',
      ip: '',
      location: '',
      isp: '',
      latencyMs,
      error: message,
    };
  } finally {
    clearTimeout(timer);
  }
}

export function IpSourcesPanel({selectedProxy}: IpSourcesPanelProps) {
  const [routeMode, setRouteMode] = useState<IpRouteMode>('browser');
  const [results, setResults] = useState<IpSourceResult[]>(() =>
    SOURCE_DEFS.map((s) => ({
      id: s.id,
      name: s.name,
      region: s.region,
      status: 'idle',
      ip: '',
      location: '',
      isp: '',
      latencyMs: null,
      error: '',
    })),
  );
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const probeOneSource = useCallback(
    async (def: SourceDefinition, mode: IpRouteMode) => {
      setResults((prev) =>
        prev.map((item) =>
          item.id === def.id
            ? {...item, status: 'loading', error: ''}
            : item,
        ),
      );

      if (mode === 'browser' && def.browserDirect) {
        const res = await queryBrowserDirect(def.id);
        setResults((prev) =>
          prev.map((item) => (item.id === def.id ? {...item, ...res} : item)),
        );
        return;
      }

      if (mode === 'proxy' && !selectedProxy) {
        setResults((prev) =>
          prev.map((item) =>
            item.id === def.id
              ? {
                  ...item,
                  status: 'error',
                  ip: '',
                  location: '',
                  isp: '',
                  latencyMs: null,
                  error: '请先在左侧选择一个自定义代理节点',
                }
              : item,
          ),
        );
        return;
      }

      try {
        const resp = await fetch('/api/check-ip', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            sourceId: def.id,
            proxy:
              mode === 'proxy' && selectedProxy
                ? {
                    protocol: selectedProxy.protocol,
                    host: selectedProxy.host,
                    port: selectedProxy.port,
                    username: selectedProxy.username,
                    password: selectedProxy.password,
                  }
                : null,
          }),
        });
        const data = (await resp.json()) as {
          ok: boolean;
          ip?: string;
          location?: string;
          isp?: string;
          latencyMs?: number | null;
          error?: string;
        };
        setResults((prev) =>
          prev.map((item) =>
            item.id === def.id
              ? {
                  ...item,
                  status: data.ok ? 'ok' : 'error',
                  ip: data.ip || '',
                  location: data.location || '',
                  isp: data.isp || '',
                  latencyMs: data.latencyMs ?? null,
                  error: data.error || '',
                }
              : item,
          ),
        );
      } catch {
        setResults((prev) =>
          prev.map((item) =>
            item.id === def.id
              ? {...item, status: 'error', error: '探测服务连接失败'}
              : item,
          ),
        );
      }
    },
    [selectedProxy],
  );

  const probeAll = useCallback(
    (mode: IpRouteMode = routeMode) => {
      SOURCE_DEFS.forEach((def) => {
        void probeOneSource(def, mode);
      });
    },
    [probeOneSource, routeMode],
  );

  useEffect(() => {
    probeAll('browser');
    // Run initial multi-source IP check on mount only
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleModeSwitch = (nextMode: IpRouteMode) => {
    setRouteMode(nextMode);
    probeAll(nextMode);
  };

  const handleCopyIp = async (id: string, ip: string) => {
    if (!ip) return;
    try {
      await navigator.clipboard.writeText(ip);
      setCopiedId(id);
      setTimeout(() => setCopiedId((cur) => (cur === id ? null : cur)), 1600);
    } catch {
      // Ignore clipboard permission denial
    }
  };

  const okList = results.filter((r) => r.status === 'ok' && r.ip);
  const distinctIps = Array.from(new Set(okList.map((r) => r.ip)));

  return (
    <div className="bg-[#1e2732] border border-[#2b3745] rounded-lg shadow-2xl overflow-hidden flex flex-col h-[620px]">
      {/* Window Header */}
      <div className="flex items-center justify-between gap-4 px-5 pt-4 pb-3 border-b border-[#26323f]">
        <div>
          <h2 className="text-[16px] font-semibold text-[#f5f5f5] tracking-tight">
            多源出口 IP 检测
          </h2>
          <p className="text-[12px] text-[#7f91a4] mt-0.5 tabular-nums">
            对比不同网络来源返回的出口 IP 与归属地（类 IP233.cn 分流检测）
          </p>
        </div>

        <button
          type="button"
          onClick={() => probeAll(routeMode)}
          className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded text-[13px] font-medium text-[#64b5f6] hover:bg-[#26323e] transition-colors whitespace-nowrap shrink-0 cursor-pointer"
        >
          <RotateCw className="w-3.5 h-3.5" />
          全部刷新
        </button>
      </div>

      {/* Route Mode Segmented Selector */}
      <div className="px-5 py-3 bg-[#17212b] border-b border-[#232f3c] flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-1 p-1 bg-[#121921] rounded-md">
          <button
            type="button"
            onClick={() => handleModeSwitch('browser')}
            className={`px-3 py-1.5 text-[12.5px] font-medium rounded transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
              routeMode === 'browser'
                ? 'bg-[#243242] text-[#f5f5f5]'
                : 'text-[#7f91a4] hover:text-[#d6e0ea]'
            }`}
          >
            本机浏览器直连
          </button>
          <button
            type="button"
            onClick={() => handleModeSwitch('proxy')}
            className={`px-3 py-1.5 text-[12.5px] font-medium rounded transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
              routeMode === 'proxy'
                ? 'bg-[#243242] text-[#f5f5f5]'
                : 'text-[#7f91a4] hover:text-[#d6e0ea]'
            }`}
          >
            通过选中代理探测
          </button>
          <button
            type="button"
            onClick={() => handleModeSwitch('server')}
            className={`px-3 py-1.5 text-[12.5px] font-medium rounded transition-colors whitespace-nowrap shrink-0 cursor-pointer ${
              routeMode === 'server'
                ? 'bg-[#243242] text-[#f5f5f5]'
                : 'text-[#7f91a4] hover:text-[#d6e0ea]'
            }`}
          >
            国内/海外节点直连
          </button>
        </div>

        <div className="text-[12px] text-[#7f91a4] tabular-nums">
          {routeMode === 'proxy' ? (
            selectedProxy ? (
              <span className="text-[#8ba5bf] font-mono">
                出口通道: {selectedProxy.protocol} {selectedProxy.host}:{selectedProxy.port}
              </span>
            ) : (
              <span className="text-[#e05a5a]">未选中代理节点</span>
            )
          ) : (
            <span>
              可用源 {okList.length}/{results.length} · 出口 IP 数 {distinctIps.length}
            </span>
          )}
        </div>
      </div>

      {/* Multi-source Result Rows */}
      <div className="flex-1 overflow-y-auto divide-y divide-[#24303d]">
        {results.map((item) => {
          const def = SOURCE_DEFS.find((d) => d.id === item.id)!;
          return (
            <div
              key={item.id}
              className="px-5 py-3.5 hover:bg-[#232e3b] transition-colors flex items-center justify-between gap-4"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 text-[12.5px]">
                  <span className="font-medium text-[#d6e0ea]">{item.name}</span>
                  <span className="text-[#56687a]" aria-hidden="true">·</span>
                  <span className="text-[#7f91a4]">{item.region}</span>
                  {routeMode === 'browser' && !def.browserDirect && (
                    <>
                      <span className="text-[#56687a]" aria-hidden="true">·</span>
                      <span className="text-[#7f91a4]">中转查询</span>
                    </>
                  )}
                </div>

                <div className="mt-1 flex items-center gap-2">
                  {item.status === 'loading' && (
                    <span className="text-[14px] text-[#64b5f6] font-mono">
                      正在查询...
                    </span>
                  )}
                  {item.status === 'idle' && (
                    <span className="text-[14px] text-[#7f91a4] font-mono">—</span>
                  )}
                  {item.status === 'error' && (
                    <span className="text-[13.5px] text-[#e05a5a]">
                      获取失败 · {item.error}
                    </span>
                  )}
                  {item.status === 'ok' && (
                    <>
                      <span className="text-[15.5px] font-semibold text-[#f5f5f5] font-mono tabular-nums tracking-tight">
                        {item.ip}
                      </span>
                      <button
                        type="button"
                        onClick={() => handleCopyIp(item.id, item.ip)}
                        aria-label={`复制 ${item.ip}`}
                        className="p-1 rounded text-[#7f91a4] hover:text-[#f5f5f5] hover:bg-[#2c3a49] transition-colors cursor-pointer"
                      >
                        {copiedId === item.id ? (
                          <Check className="w-3.5 h-3.5 text-[#45b97c]" />
                        ) : (
                          <Copy className="w-3.5 h-3.5" />
                        )}
                      </button>
                    </>
                  )}
                </div>

                {item.status === 'ok' && (item.location || item.isp) && (
                  <div className="mt-0.5 text-[12px] text-[#7f91a4] truncate">
                    {[item.location, item.isp].filter(Boolean).join(' · ')}
                  </div>
                )}
              </div>

              <div className="flex items-center gap-3 shrink-0">
                <div className="text-right tabular-nums text-[12.5px] font-mono min-w-[60px]">
                  {item.status === 'ok' && item.latencyMs !== null && (
                    <span className="text-[#45b97c]">{item.latencyMs} ms</span>
                  )}
                  {item.status === 'error' && (
                    <span className="text-[#e05a5a]">超时/失败</span>
                  )}
                  {item.status === 'loading' && (
                    <span className="text-[#64b5f6]">探测中</span>
                  )}
                </div>

                <button
                  type="button"
                  onClick={() => void probeOneSource(def, routeMode)}
                  aria-label={`重测 ${item.name}`}
                  className="p-1.5 rounded text-[#7f91a4] hover:text-[#f5f5f5] hover:bg-[#2c3a49] transition-colors cursor-pointer"
                >
                  <RotateCw
                    className={`w-3.5 h-3.5 ${
                      item.status === 'loading' ? 'animate-spin text-[#64b5f6]' : ''
                    }`}
                  />
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Summary Footer */}
      <div className="px-5 py-3 bg-[#17212b] border-t border-[#232f3c] flex items-center justify-between gap-4 text-[12px] text-[#7f91a4]">
        <span>
          {distinctIps.length > 1
            ? `检测到 ${distinctIps.length} 个不同出口 IP（国内/海外分流生效或来源策略差异）`
            : distinctIps.length === 1
              ? `当前所有可用来源出口 IP 一致: ${distinctIps[0]}`
              : '点击「全部刷新」或切换探测通道以对比不同来源的出口 IP'}
        </span>
        <span className="whitespace-nowrap shrink-0 tabular-nums">
          {okList.length} 源在线
        </span>
      </div>
    </div>
  );
}
