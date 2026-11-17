export type ProxyProtocol = 'MTPROTO' | 'SOCKS5' | 'HTTP' | 'WEB';

export type ProxyMode = 'disabled' | 'system' | 'custom';

export type ProxyStatus = 'untested' | 'testing' | 'available' | 'unavailable';

export interface ProxyEntry {
  id: string;
  protocol: ProxyProtocol;
  host: string;
  port: number;
  secret: string;
  username: string;
  password: string;
  status: ProxyStatus;
  latencyMs: number | null;
  detail: string;
}

export type IpRouteMode = 'browser' | 'proxy' | 'server';

export interface IpSourceResult {
  id: string;
  name: string;
  region: string;
  status: 'idle' | 'loading' | 'ok' | 'error';
  ip: string;
  location: string;
  isp: string;
  latencyMs: number | null;
  error: string;
}
