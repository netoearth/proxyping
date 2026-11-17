import express from 'express';
import net from 'net';
import path from 'path';
import tls from 'tls';
import {fileURLToPath} from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

interface ProbeRequest {
  protocol: string;
  host: string;
  port: number;
  secret?: string;
  username?: string;
  password?: string;
  targetHost?: string;
  targetPort?: number;
}

interface ProbeResponse {
  available: boolean;
  latencyMs: number | null;
  detail: string;
}

interface IpSourceSpec {
  id: string;
  name: string;
  region: string;
  host: string;
  port: number;
  path: string;
  kind: 'ip_sb' | 'ipinfo' | 'ipify' | 'ipwho' | 'cf_trace' | 'ip_api' | 'pconline';
}

const SERVER_IP_SOURCES: IpSourceSpec[] = [
  {id: 'pconline', name: '太平洋电脑网', region: '国内来源', host: 'whois.pconline.com.cn', port: 443, path: '/ipJson.jsp?json=true', kind: 'pconline'},
  {id: 'ip_sb', name: 'IP.SB', region: '国际来源', host: 'api.ip.sb', port: 443, path: '/geoip', kind: 'ip_sb'},
  {id: 'ipinfo', name: 'IPinfo.io', region: '国际来源', host: 'ipinfo.io', port: 443, path: '/json', kind: 'ipinfo'},
  {id: 'ipify', name: 'ipify IPv4', region: '国际来源', host: 'api.ipify.org', port: 443, path: '/?format=json', kind: 'ipify'},
  {id: 'ipwho', name: 'ipwho.is', region: '全球节点', host: 'ipwho.is', port: 443, path: '/', kind: 'ipwho'},
  {id: 'cf_trace', name: 'Cloudflare', region: 'CDN 节点', host: 'www.cloudflare.com', port: 443, path: '/cdn-cgi/trace', kind: 'cf_trace'},
  {id: 'ip_api', name: 'IP-API', region: '国际来源', host: 'ip-api.com', port: 80, path: '/json/?lang=zh-CN', kind: 'ip_api'},
];

function probeSocks5(
  host: string,
  port: number,
  targetHost: string,
  targetPort: number,
  username: string,
  password: string,
  timeoutMs = 3500,
): Promise<ProbeResponse> {
  return new Promise((resolve) => {
    const start = performance.now();
    const socket = new net.Socket();
    let stage: 'greeting' | 'auth' | 'connect' | 'http' = 'greeting';
    let settled = false;

    const finish = (res: ProbeResponse) => {
      if (settled) return;
      settled = true;
      socket.destroy();
      resolve(res);
    };

    socket.setTimeout(timeoutMs);

    socket.on('timeout', () => {
      finish({available: false, latencyMs: null, detail: '连接超时'});
    });

    socket.on('error', (err) => {
      finish({
        available: false,
        latencyMs: null,
        detail: err.message || 'TCP 连接失败',
      });
    });

    socket.connect(port, host, () => {
      const greeting = username
        ? Buffer.from([0x05, 0x02, 0x00, 0x02])
        : Buffer.from([0x05, 0x01, 0x00]);
      socket.write(greeting);
    });

    socket.on('data', (chunk) => {
      if (stage === 'greeting') {
        if (chunk.length < 2 || chunk[0] !== 0x05) {
          return finish({available: false, latencyMs: null, detail: '无效的 SOCKS5 握手响应'});
        }
        if (chunk[1] === 0xff) {
          return finish({available: false, latencyMs: null, detail: 'SOCKS5 认证方式被拒绝'});
        }
        if (chunk[1] === 0x02) {
          if (!username) {
            return finish({available: false, latencyMs: null, detail: '需要用户名/密码认证'});
          }
          stage = 'auth';
          const u = Buffer.from(username, 'utf8').subarray(0, 255);
          const p = Buffer.from(password, 'utf8').subarray(0, 255);
          const authBuf = Buffer.concat([
            Buffer.from([0x01, u.length]),
            u,
            Buffer.from([p.length]),
            p,
          ]);
          socket.write(authBuf);
          return;
        }
        stage = 'connect';
        sendConnect();
        return;
      }

      if (stage === 'auth') {
        if (chunk.length < 2 || chunk[1] !== 0x00) {
          return finish({available: false, latencyMs: null, detail: 'SOCKS5 用户名或密码错误'});
        }
        stage = 'connect';
        sendConnect();
        return;
      }

      if (stage === 'connect') {
        if (chunk.length < 4 || chunk[0] !== 0x05) {
          return finish({available: false, latencyMs: null, detail: 'SOCKS5 CONNECT 无响应'});
        }
        if (chunk[1] !== 0x00) {
          return finish({
            available: false,
            latencyMs: null,
            detail: `SOCKS5 连接失败 (错误码: ${chunk[1]})`,
          });
        }
        stage = 'http';
        socket.write(
          `HEAD /generate_204 HTTP/1.1\r\nHost: ${targetHost}\r\nConnection: close\r\n\r\n`,
        );
        return;
      }

      if (stage === 'http') {
        const latencyMs = Math.max(1, Math.round(performance.now() - start));
        const banner = chunk.toString('latin1');
        if (banner.startsWith('HTTP/')) {
          return finish({available: true, latencyMs, detail: 'SOCKS5 端到端连通正常'});
        }
        return finish({available: true, latencyMs, detail: 'SOCKS5 隧道握手成功'});
      }
    });

    function sendConnect() {
      const hostBuf = Buffer.from(targetHost, 'ascii');
      const portBuf = Buffer.alloc(2);
      portBuf.writeUInt16BE(targetPort, 0);
      const req = Buffer.concat([
        Buffer.from([0x05, 0x01, 0x00, 0x03, hostBuf.length]),
        hostBuf,
        portBuf,
      ]);
      socket.write(req);
    }
  });
}

function probeHttp(
  host: string,
  port: number,
  targetHost: string,
  targetPort: number,
  username: string,
  password: string,
  useConnect: boolean,
  timeoutMs = 3500,
): Promise<ProbeResponse> {
  return new Promise((resolve) => {
    const start = performance.now();
    const socket = new net.Socket();
    let settled = false;

    const finish = (res: ProbeResponse) => {
      if (settled) return;
      settled = true;
      socket.destroy();
      resolve(res);
    };

    socket.setTimeout(timeoutMs);

    socket.on('timeout', () => {
      finish({available: false, latencyMs: null, detail: '连接超时'});
    });

    socket.on('error', (err) => {
      finish({
        available: false,
        latencyMs: null,
        detail: err.message || 'TCP 连接失败',
      });
    });

    socket.connect(port, host, () => {
      const authHeader = username
        ? `Proxy-Authorization: Basic ${Buffer.from(`${username}:${password}`).toString('base64')}\r\n`
        : '';
      const payload =
        useConnect || targetPort === 443
          ? `CONNECT ${targetHost}:${targetPort} HTTP/1.1\r\nHost: ${targetHost}:${targetPort}\r\n${authHeader}Proxy-Connection: keep-alive\r\n\r\n`
          : `HEAD http://${targetHost}:${targetPort}/generate_204 HTTP/1.1\r\nHost: ${targetHost}\r\n${authHeader}Connection: close\r\n\r\n`;
      socket.write(payload);
    });

    socket.on('data', (chunk) => {
      const latencyMs = Math.max(1, Math.round(performance.now() - start));
      const firstLine = chunk.toString('latin1').split(/\r?\n/)[0] || '';
      if (firstLine.includes('407')) {
        return finish({available: false, latencyMs: null, detail: 'HTTP 代理需要认证 (407)'});
      }
      if (/200|204|301|302/.test(firstLine)) {
        return finish({available: true, latencyMs, detail: firstLine.trim()});
      }
      if (firstLine.startsWith('HTTP/')) {
        return finish({
          available: false,
          latencyMs: null,
          detail: `代理返回异常状态: ${firstLine.trim()}`,
        });
      }
      return finish({available: false, latencyMs: null, detail: '无效的 HTTP 代理响应'});
    });
  });
}

function probeMtproto(
  host: string,
  port: number,
  secret: string,
  timeoutMs = 3500,
): Promise<ProbeResponse> {
  const cleaned = secret.trim().toLowerCase();
  if (cleaned) {
    const isHex = /^[0-9a-f]+$/.test(cleaned);
    const validLen =
      cleaned.length === 32 ||
      (cleaned.startsWith('dd') && cleaned.length === 34) ||
      (cleaned.startsWith('ee') && cleaned.length >= 34);
    if (!isHex || !validLen) {
      return Promise.resolve({
        available: false,
        latencyMs: null,
        detail: 'MTProto 密钥格式无效',
      });
    }
  }

  return new Promise((resolve) => {
    const start = performance.now();
    const socket = new net.Socket();
    let settled = false;

    const finish = (res: ProbeResponse) => {
      if (settled) return;
      settled = true;
      socket.destroy();
      resolve(res);
    };

    socket.setTimeout(timeoutMs);
    socket.on('timeout', () => {
      finish({available: false, latencyMs: null, detail: '连接超时'});
    });
    socket.on('error', (err) => {
      finish({
        available: false,
        latencyMs: null,
        detail: err.message || 'TCP 连接失败',
      });
    });
    socket.connect(port, host, () => {
      const latencyMs = Math.max(1, Math.round(performance.now() - start));
      finish({available: true, latencyMs, detail: 'MTProto TCP 端口可达'});
    });
  });
}

function decodeChunkedBody(buf: Buffer): string {
  const out: Buffer[] = [];
  let offset = 0;
  while (offset < buf.length) {
    const nl = buf.indexOf('\r\n', offset);
    if (nl === -1) break;
    const sizeStr = buf.subarray(offset, nl).toString('ascii').split(';')[0].trim();
    const size = Number.parseInt(sizeStr, 16);
    if (!Number.isFinite(size) || size <= 0) break;
    const start = nl + 2;
    out.push(buf.subarray(start, start + size));
    offset = start + size + 2;
  }
  return Buffer.concat(out).toString('utf8');
}

function fetchViaProxySocket(
  targetHost: string,
  targetPort: number,
  reqPath: string,
  proxy: {protocol: string; host: string; port: number; username?: string; password?: string},
  timeoutMs = 5000,
): Promise<{status: number; body: string}> {
  return new Promise((resolve, reject) => {
    const proto = proxy.protocol.toUpperCase();
    if (proto !== 'SOCKS5' && proto !== 'HTTP' && proto !== 'WEB') {
      return reject(new Error('MTProto 不支持 HTTP 出站探测'));
    }

    const rawSocket = new net.Socket();
    let activeSocket: net.Socket | tls.TLSSocket = rawSocket;
    let stage: 'greeting' | 'auth' | 'connect' | 'http_connect' | 'response' =
      proto === 'SOCKS5' ? 'greeting' : 'http_connect';
    const chunks: Buffer[] = [];
    let settled = false;

    const fail = (err: Error) => {
      if (settled) return;
      settled = true;
      activeSocket.destroy();
      rawSocket.destroy();
      reject(err);
    };

    const completeHttp = () => {
      if (settled) return;
      settled = true;
      const full = Buffer.concat(chunks);
      const sep = full.indexOf('\r\n\r\n');
      if (sep === -1) {
        return reject(new Error('响应格式无效'));
      }
      const headerStr = full.subarray(0, sep).toString('latin1');
      const bodyBuf = full.subarray(sep + 4);
      const firstLine = headerStr.split(/\r?\n/)[0] || '';
      const status = Number.parseInt(firstLine.split(' ')[1] || '0', 10);
      const isChunked = headerStr.toLowerCase().includes('transfer-encoding: chunked');
      const body = isChunked ? decodeChunkedBody(bodyBuf) : bodyBuf.toString('utf8');
      resolve({status, body});
    };

    rawSocket.setTimeout(timeoutMs);
    rawSocket.on('timeout', () => fail(new Error('代理连接超时')));
    rawSocket.on('error', (err) => fail(err));

    const sendTargetHttpGet = () => {
      const writeGet = (sock: net.Socket | tls.TLSSocket) => {
        sock.write(
          `GET ${reqPath} HTTP/1.1\r\nHost: ${targetHost}\r\nUser-Agent: ProxyProbe/1.0\r\nAccept: application/json,text/plain,*/*\r\nAccept-Encoding: identity\r\nConnection: close\r\n\r\n`,
        );
      };

      if (targetPort === 443) {
        const tlsSock = tls.connect({socket: rawSocket, servername: targetHost}, () => {
          writeGet(tlsSock);
        });
        activeSocket = tlsSock;
        tlsSock.setTimeout(timeoutMs);
        tlsSock.on('timeout', () => fail(new Error('TLS 握手超时')));
        tlsSock.on('error', (err) => fail(err));
        tlsSock.on('data', (d) => chunks.push(d));
        tlsSock.on('end', completeHttp);
      } else {
        writeGet(rawSocket);
      }
    };

    rawSocket.connect(proxy.port, proxy.host, () => {
      if (proto === 'SOCKS5') {
        rawSocket.write(
          proxy.username
            ? Buffer.from([0x05, 0x02, 0x00, 0x02])
            : Buffer.from([0x05, 0x01, 0x00]),
        );
      } else {
        const authH = proxy.username
          ? `Proxy-Authorization: Basic ${Buffer.from(`${proxy.username}:${proxy.password || ''}`).toString('base64')}\r\n`
          : '';
        rawSocket.write(
          `CONNECT ${targetHost}:${targetPort} HTTP/1.1\r\nHost: ${targetHost}:${targetPort}\r\n${authH}\r\n`,
        );
      }
    });

    rawSocket.on('data', (chunk) => {
      if (stage === 'response') {
        if (targetPort !== 443) {
          chunks.push(chunk);
        }
        return;
      }

      if (stage === 'greeting') {
        if (chunk.length < 2 || chunk[0] !== 0x05 || chunk[1] === 0xff) {
          return fail(new Error('SOCKS5 握手被拒绝'));
        }
        if (chunk[1] === 0x02) {
          if (!proxy.username) return fail(new Error('SOCKS5 需要认证'));
          stage = 'auth';
          const u = Buffer.from(proxy.username, 'utf8').subarray(0, 255);
          const p = Buffer.from(proxy.password || '', 'utf8').subarray(0, 255);
          rawSocket.write(
            Buffer.concat([Buffer.from([0x01, u.length]), u, Buffer.from([p.length]), p]),
          );
          return;
        }
        stage = 'connect';
        const hb = Buffer.from(targetHost, 'ascii');
        const pb = Buffer.alloc(2);
        pb.writeUInt16BE(targetPort, 0);
        rawSocket.write(
          Buffer.concat([Buffer.from([0x05, 0x01, 0x00, 0x03, hb.length]), hb, pb]),
        );
        return;
      }

      if (stage === 'auth') {
        if (chunk.length < 2 || chunk[1] !== 0x00) {
          return fail(new Error('SOCKS5 认证失败'));
        }
        stage = 'connect';
        const hb = Buffer.from(targetHost, 'ascii');
        const pb = Buffer.alloc(2);
        pb.writeUInt16BE(targetPort, 0);
        rawSocket.write(
          Buffer.concat([Buffer.from([0x05, 0x01, 0x00, 0x03, hb.length]), hb, pb]),
        );
        return;
      }

      if (stage === 'connect') {
        if (chunk.length < 4 || chunk[1] !== 0x00) {
          return fail(new Error('SOCKS5 隧道建立失败'));
        }
        stage = 'response';
        sendTargetHttpGet();
        return;
      }

      if (stage === 'http_connect') {
        const line = chunk.toString('latin1').split(/\r?\n/)[0] || '';
        if (!line.includes('200')) {
          return fail(new Error(`HTTP 隧道拒绝: ${line}`));
        }
        stage = 'response';
        sendTargetHttpGet();
      }
    });

    rawSocket.on('end', () => {
      if (targetPort !== 443 && stage === 'response') {
        completeHttp();
      }
    });
  });
}

function parseIpPayload(kind: IpSourceSpec['kind'], body: string) {
  let ip = '';
  let location = '';
  let isp = '';

  if (kind === 'cf_trace') {
    const map: Record<string, string> = {};
    for (const line of body.split(/\r?\n/)) {
      const idx = line.indexOf('=');
      if (idx > 0) map[line.slice(0, idx)] = line.slice(idx + 1);
    }
    ip = map.ip || '';
    location = map.colo ? `${map.loc || ''} (${map.colo})`.trim() : map.loc || '';
    isp = 'Cloudflare Edge';
  } else {
    const data = JSON.parse(body.trim()) as Record<string, unknown>;
    if (kind === 'ip_sb') {
      ip = String(data.ip || '');
      location = [data.country, data.city].filter(Boolean).join(' · ');
      isp = String(data.organization || data.isp || '');
    } else if (kind === 'ipinfo') {
      ip = String(data.ip || '');
      location = [data.country, data.region, data.city].filter(Boolean).join(' · ');
      isp = String(data.org || '');
    } else if (kind === 'ipify') {
      ip = String(data.ip || '');
      location = 'IPv4 出口验证';
      isp = 'ipify';
    } else if (kind === 'ipwho') {
      ip = String(data.ip || '');
      location = [data.country, data.city].filter(Boolean).join(' · ');
      const conn = (data.connection as Record<string, unknown> | undefined) || {};
      isp = String(conn.isp || conn.org || '');
    } else if (kind === 'ip_api') {
      ip = String(data.query || '');
      location = [data.country, data.city].filter(Boolean).join(' · ');
      isp = String(data.isp || data.org || '');
    } else if (kind === 'pconline') {
      ip = String(data.ip || '');
      location = String(data.addr || '').trim();
      isp = '国内 IP 归属地库';
    }
  }

  return {ip, location, isp};
}

async function startServer() {
  const app = express();
  app.use(express.json());

  app.post('/api/test-proxy', async (req, res) => {
    const body = req.body as ProbeRequest;
    const protocol = (body.protocol || 'SOCKS5').toUpperCase();
    const host = String(body.host || '').trim();
    const port = Number(body.port);
    const targetHost = String(body.targetHost || 'cp.cloudflare.com').trim();
    const targetPort = Number(body.targetPort || 80);

    if (!host || !Number.isInteger(port) || port < 1 || port > 65535) {
      res.status(400).json({
        available: false,
        latencyMs: null,
        detail: '主机地址或端口格式无效',
      });
      return;
    }

    let result: ProbeResponse;
    if (protocol === 'SOCKS5') {
      result = await probeSocks5(
        host,
        port,
        targetHost,
        targetPort,
        body.username || '',
        body.password || '',
      );
    } else if (protocol === 'HTTP' || protocol === 'WEB') {
      result = await probeHttp(
        host,
        port,
        targetHost,
        targetPort,
        body.username || '',
        body.password || '',
        protocol === 'WEB',
      );
    } else if (protocol === 'MTPROTO') {
      result = await probeMtproto(host, port, body.secret || '');
    } else {
      result = {available: false, latencyMs: null, detail: `不支持的协议: ${protocol}`};
    }

    res.json(result);
  });

  app.post('/api/check-ip', async (req, res) => {
    const {sourceId, proxy} = req.body as {
      sourceId: string;
      proxy?: {
        protocol: string;
        host: string;
        port: number;
        username?: string;
        password?: string;
      } | null;
    };

    const spec = SERVER_IP_SOURCES.find((s) => s.id === sourceId);
    if (!spec) {
      res.status(400).json({ok: false, error: '未知的 IP 检测来源'});
      return;
    }

    const start = performance.now();
    try {
      let status = 0;
      let body = '';
      if (proxy) {
        const resp = await fetchViaProxySocket(spec.host, spec.port, spec.path, proxy);
        status = resp.status;
        body = resp.body;
      } else {
        const scheme = spec.port === 443 ? 'https' : 'http';
        const resp = await fetch(`${scheme}://${spec.host}${spec.path}`, {
          signal: AbortSignal.timeout(5000),
          headers: {'User-Agent': 'ProxyProbe/1.0', Accept: 'application/json,text/plain,*/*'},
        });
        status = resp.status;
        if (spec.kind === 'pconline') {
          const buf = await resp.arrayBuffer();
          body = new TextDecoder('gbk').decode(buf);
        } else {
          body = await resp.text();
        }
      }

      const latencyMs = Math.max(1, Math.round(performance.now() - start));
      if (status < 200 || status >= 400) {
        res.json({ok: false, latencyMs, error: `HTTP ${status}`});
        return;
      }

      const parsed = parseIpPayload(spec.kind, body);
      if (!parsed.ip) {
        res.json({ok: false, latencyMs, error: '未能解析出口 IP'});
        return;
      }

      res.json({
        ok: true,
        ip: parsed.ip,
        location: parsed.location,
        isp: parsed.isp,
        latencyMs,
      });
    } catch (err) {
      const latencyMs = Math.max(1, Math.round(performance.now() - start));
      const msg = err instanceof Error ? err.message : '请求失败';
      res.json({ok: false, latencyMs, error: msg});
    }
  });

  app.get('/api/system-proxies', (_req, res) => {
    const envKeys = [
      ['HTTP_PROXY', 'HTTP'],
      ['http_proxy', 'HTTP'],
      ['HTTPS_PROXY', 'HTTP'],
      ['https_proxy', 'HTTP'],
      ['ALL_PROXY', 'SOCKS5'],
      ['all_proxy', 'SOCKS5'],
    ] as const;

    const detected: Array<{protocol: string; host: string; port: number}> = [];
    const seen = new Set<string>();

    for (const [key, defaultProto] of envKeys) {
      const val = process.env[key];
      if (!val) continue;
      try {
        const parsed = new URL(val.includes('://') ? val : `http://${val}`);
        const port = Number(parsed.port);
        if (parsed.hostname && port > 0) {
          const proto = parsed.protocol.includes('socks') ? 'SOCKS5' : defaultProto;
          const id = `${proto}:${parsed.hostname}:${port}`;
          if (!seen.has(id)) {
            seen.add(id);
            detected.push({protocol: proto, host: parsed.hostname, port});
          }
        }
      } catch {
        // Ignore malformed env var
      }
    }

    res.json({detected});
  });

  if (process.env.NODE_ENV !== 'production') {
    const {createServer: createViteServer} = await import('vite');
    const vite = await createViteServer({
      server: {middlewareMode: true},
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    const distDir = path.resolve(__dirname, 'dist');
    app.use(express.static(distDir));
    app.get('*', (_req, res) => {
      res.sendFile(path.join(distDir, 'index.html'));
    });
  }

  const port = 3000;
  app.listen(port, '0.0.0.0', () => {
    console.log(`Server listening on http://0.0.0.0:${port}`);
  });
}

startServer();
