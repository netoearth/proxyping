"""
Cross-platform proxy connectivity testing & system proxy detection core.
Zero external dependencies — uses Python 3.8+ standard library only.
Supports Windows, macOS, and Linux.
"""

from __future__ import annotations

import base64
import json
import os
import platform
import socket
import ssl
import struct
import subprocess
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


PROTOCOLS = ("MTPROTO", "SOCKS5", "HTTP", "WEB")
DEFAULT_TEST_HOST = "cp.cloudflare.com"
DEFAULT_TEST_PORT = 80
DEFAULT_TEST_PATH = "/generate_204"
CONFIG_PATH = Path.home() / ".proxy_tester_config.json"


@dataclass
class ProxyEntry:
    id: str
    protocol: str  # MTPROTO | SOCKS5 | HTTP | WEB
    host: str
    port: int
    secret: str = ""
    username: str = ""
    password: str = ""
    status: str = "untested"  # untested | testing | available | unavailable
    latency_ms: Optional[int] = None
    detail: str = ""

    def address_label(self) -> str:
        return f"{self.host}:{self.port}"

    def to_share_uri(self) -> str:
        proto = self.protocol.upper()
        if proto == "MTPROTO":
            q = urllib.parse.urlencode(
                {"server": self.host, "port": self.port, "secret": self.secret}
            )
            return f"tg://proxy?{q}"
        scheme = "socks5" if proto == "SOCKS5" else "http"
        auth = ""
        if self.username:
            user = urllib.parse.quote(self.username, safe="")
            pwd = urllib.parse.quote(self.password, safe="")
            auth = f"{user}:{pwd}@" if self.password else f"{user}@"
        return f"{scheme}://{auth}{self.host}:{self.port}"


@dataclass
class ProbeResult:
    available: bool
    latency_ms: Optional[int]
    detail: str


def detect_system_proxies() -> List[Tuple[str, str, int]]:
    """
    Detect OS-level configured proxies across Windows, macOS, and Linux.
    Returns list of tuples: (protocol, host, port).
    """
    results: List[Tuple[str, str, int]] = []
    seen = set()

    def add_proxy(proto: str, host: str, port: int) -> None:
        key = (proto.upper(), host, port)
        if host and port > 0 and key not in seen:
            seen.add(key)
            results.append(key)

    # 1. Cross-platform stdlib detection (Windows Registry, macOS SystemConfig, Linux env)
    try:
        proxies = urllib.request.getproxies()
        for scheme, raw_url in proxies.items():
            if not raw_url:
                continue
            url = raw_url if "://" in raw_url else f"http://{raw_url}"
            parsed = urllib.parse.urlparse(url)
            if parsed.hostname and parsed.port:
                proto = "SOCKS5" if "socks" in scheme.lower() or "socks" in (parsed.scheme or "").lower() else "HTTP"
                add_proxy(proto, parsed.hostname, parsed.port)
    except Exception:
        pass

    sys_name = platform.system().lower()

    # 2. macOS scutil fallback
    if sys_name == "darwin":
        try:
            out = subprocess.check_output(["scutil", "--proxy"], text=True, timeout=2)
            info: Dict[str, str] = {}
            for line in out.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    info[k.strip()] = v.strip()
            if info.get("SOCKSEnable") == "1" and info.get("SOCKSProxy"):
                add_proxy("SOCKS5", info["SOCKSProxy"], int(info.get("SOCKSPort", 1080)))
            if info.get("HTTPEnable") == "1" and info.get("HTTPProxy"):
                add_proxy("HTTP", info["HTTPProxy"], int(info.get("HTTPPort", 8080)))
            if info.get("HTTPSEnable") == "1" and info.get("HTTPSProxy"):
                add_proxy("HTTP", info["HTTPSProxy"], int(info.get("HTTPSPort", 8080)))
        except Exception:
            pass

    # 3. Linux GNOME gsettings fallback
    elif sys_name == "linux":
        try:
            mode = subprocess.check_output(
                ["gsettings", "get", "org.gnome.system.proxy", "mode"],
                text=True,
                timeout=1.5,
                stderr=subprocess.DEVNULL,
            ).strip().strip("'")
            if mode == "manual":
                for section, proto in (("socks", "SOCKS5"), ("http", "HTTP"), ("https", "HTTP")):
                    host = subprocess.check_output(
                        ["gsettings", "get", f"org.gnome.system.proxy.{section}", "host"],
                        text=True,
                        timeout=1.5,
                        stderr=subprocess.DEVNULL,
                    ).strip().strip("'")
                    port_str = subprocess.check_output(
                        ["gsettings", "get", f"org.gnome.system.proxy.{section}", "port"],
                        text=True,
                        timeout=1.5,
                        stderr=subprocess.DEVNULL,
                    ).strip()
                    if host and port_str.isdigit() and int(port_str) > 0:
                        add_proxy(proto, host, int(port_str))
        except Exception:
            pass

    return results


def _probe_socks5(
    host: str,
    port: int,
    target_host: str,
    target_port: int,
    username: str = "",
    password: str = "",
    timeout: float = 5.0,
) -> ProbeResult:
    start = time.perf_counter()
    sock: Optional[socket.socket] = None
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.settimeout(timeout)

        # Greeting: support No-Auth (0x00) and optionally User/Pass (0x02)
        if username:
            sock.sendall(b"\x05\x02\x00\x02")
        else:
            sock.sendall(b"\x05\x01\x00")

        method_resp = sock.recv(2)
        if len(method_resp) < 2 or method_resp[0] != 0x05:
            return ProbeResult(False, None, "无效的 SOCKS5 握手响应")

        chosen = method_resp[1]
        if chosen == 0xFF:
            return ProbeResult(False, None, "SOCKS5 认证方式被拒绝")

        if chosen == 0x02:
            if not username:
                return ProbeResult(False, None, "代理需要用户名/密码认证")
            u_bytes = username.encode("utf-8")[:255]
            p_bytes = password.encode("utf-8")[:255]
            auth_pkt = struct.pack("!BB", 1, len(u_bytes)) + u_bytes + struct.pack("!B", len(p_bytes)) + p_bytes
            sock.sendall(auth_pkt)
            auth_resp = sock.recv(2)
            if len(auth_resp) < 2 or auth_resp[1] != 0x00:
                return ProbeResult(False, None, "SOCKS5 用户名或密码错误")

        # CONNECT command (ATYP = 0x03 domain name)
        target_bytes = target_host.encode("ascii")
        req = (
            struct.pack("!BBBB", 0x05, 0x01, 0x00, 0x03)
            + struct.pack("!B", len(target_bytes))
            + target_bytes
            + struct.pack("!H", target_port)
        )
        sock.sendall(req)

        head = sock.recv(4)
        if len(head) < 4 or head[0] != 0x05:
            return ProbeResult(False, None, "SOCKS5 CONNECT 无响应")
        if head[1] != 0x00:
            return ProbeResult(False, None, f"SOCKS5 连接失败 (错误码: {head[1]})")

        # Drain bound address bytes
        atyp = head[3]
        if atyp == 0x01:
            sock.recv(6)
        elif atyp == 0x03:
            alen = sock.recv(1)
            if alen:
                sock.recv(alen[0] + 2)
        elif atyp == 0x04:
            sock.recv(18)

        # Lightweight HTTP HEAD check over tunnel to confirm end-to-end traffic
        http_req = (
            f"HEAD {DEFAULT_TEST_PATH} HTTP/1.1\r\n"
            f"Host: {target_host}\r\n"
            f"Connection: close\r\n\r\n"
        ).encode("ascii")
        sock.sendall(http_req)
        banner = sock.recv(64)
        elapsed_ms = max(1, int((time.perf_counter() - start) * 1000))
        if banner.startswith(b"HTTP/"):
            return ProbeResult(True, elapsed_ms, "SOCKS5 端到端连通正常")
        return ProbeResult(True, elapsed_ms, "SOCKS5 隧道握手成功")
    except socket.timeout:
        return ProbeResult(False, None, "连接超时")
    except OSError as exc:
        return ProbeResult(False, None, f"连接失败: {exc.strerror or exc}")
    finally:
        if sock:
            try:
                sock.close()
            except OSError:
                pass


def _probe_http(
    host: str,
    port: int,
    target_host: str,
    target_port: int,
    username: str = "",
    password: str = "",
    use_connect: bool = False,
    timeout: float = 5.0,
) -> ProbeResult:
    start = time.perf_counter()
    sock: Optional[socket.socket] = None
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.settimeout(timeout)

        auth_header = ""
        if username:
            token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
            auth_header = f"Proxy-Authorization: Basic {token}\r\n"

        if use_connect or target_port == 443:
            req = (
                f"CONNECT {target_host}:{target_port} HTTP/1.1\r\n"
                f"Host: {target_host}:{target_port}\r\n"
                f"{auth_header}"
                f"Proxy-Connection: keep-alive\r\n\r\n"
            )
        else:
            req = (
                f"HEAD http://{target_host}:{target_port}{DEFAULT_TEST_PATH} HTTP/1.1\r\n"
                f"Host: {target_host}\r\n"
                f"{auth_header}"
                f"Connection: close\r\n\r\n"
            )

        sock.sendall(req.encode("ascii"))
        resp = sock.recv(1024).decode("latin-1", errors="ignore")
        elapsed_ms = max(1, int((time.perf_counter() - start) * 1000))

        first_line = resp.splitlines()[0] if resp else ""
        if "407" in first_line:
            return ProbeResult(False, None, "HTTP 代理需要认证 (407)")
        if any(code in first_line for code in ("200", "204", "301", "302")):
            return ProbeResult(True, elapsed_ms, first_line.strip())
        if first_line.startswith("HTTP/"):
            return ProbeResult(False, None, f"代理返回异常状态: {first_line.strip()}")
        return ProbeResult(False, None, "无效的 HTTP 代理响应")
    except socket.timeout:
        return ProbeResult(False, None, "连接超时")
    except OSError as exc:
        return ProbeResult(False, None, f"连接失败: {exc.strerror or exc}")
    finally:
        if sock:
            try:
                sock.close()
            except OSError:
                pass


def _probe_mtproto(
    host: str,
    port: int,
    secret: str = "",
    timeout: float = 5.0,
) -> ProbeResult:
    cleaned = secret.strip().lower()
    if cleaned:
        # Validate standard 32-hex, dd+32-hex, or ee+32-hex+domain-hex
        is_hex = all(c in "0123456789abcdef" for c in cleaned)
        valid_len = len(cleaned) == 32 or (
            cleaned.startswith("dd") and len(cleaned) == 34
        ) or (
            cleaned.startswith("ee") and len(cleaned) >= 34
        )
        if not (is_hex and valid_len):
            return ProbeResult(False, None, "MTProto 密钥格式无效")

    start = time.perf_counter()
    sock: Optional[socket.socket] = None
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.settimeout(min(timeout, 2.0))
        elapsed_ms = max(1, int((time.perf_counter() - start) * 1000))
        return ProbeResult(True, elapsed_ms, "MTProto TCP 端口可达")
    except socket.timeout:
        return ProbeResult(False, None, "连接超时")
    except OSError as exc:
        return ProbeResult(False, None, f"连接失败: {exc.strerror or exc}")
    finally:
        if sock:
            try:
                sock.close()
            except OSError:
                pass


def test_proxy(
    entry: ProxyEntry,
    target_host: str = DEFAULT_TEST_HOST,
    target_port: int = DEFAULT_TEST_PORT,
    timeout: float = 5.0,
) -> ProbeResult:
    proto = entry.protocol.upper()
    if proto == "SOCKS5":
        return _probe_socks5(
            entry.host,
            entry.port,
            target_host,
            target_port,
            entry.username,
            entry.password,
            timeout=timeout,
        )
    if proto in ("HTTP", "WEB"):
        return _probe_http(
            entry.host,
            entry.port,
            target_host,
            target_port,
            entry.username,
            entry.password,
            use_connect=(proto == "WEB"),
            timeout=timeout,
        )
    if proto == "MTPROTO":
        return _probe_mtproto(entry.host, entry.port, entry.secret, timeout=timeout)
    return ProbeResult(False, None, f"不支持的协议: {proto}")


def load_config(path: Path = CONFIG_PATH) -> Dict:
    default_entries = [
        ProxyEntry(id="p1", protocol="SOCKS5", host="127.0.0.1", port=4526),
        ProxyEntry(id="p2", protocol="SOCKS5", host="127.0.0.1", port=40000),
        ProxyEntry(id="p3", protocol="SOCKS5", host="127.0.0.1", port=9050),
        ProxyEntry(id="p4", protocol="SOCKS5", host="127.0.0.1", port=10240),
        ProxyEntry(id="p5", protocol="SOCKS5", host="127.0.0.1", port=9909),
    ]
    if not path.exists():
        return {
            "mode": "system",  # disabled | system | custom
            "selected_id": "p5",
            "target_host": DEFAULT_TEST_HOST,
            "target_port": DEFAULT_TEST_PORT,
            "proxies": [asdict(e) for e in default_entries],
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if "proxies" not in data:
            data["proxies"] = [asdict(e) for e in default_entries]
        return data
    except Exception:
        return {
            "mode": "system",
            "selected_id": "p5",
            "target_host": DEFAULT_TEST_HOST,
            "target_port": DEFAULT_TEST_PORT,
            "proxies": [asdict(e) for e in default_entries],
        }


def save_config(
    mode: str,
    selected_id: Optional[str],
    proxies: List[ProxyEntry],
    target_host: str = DEFAULT_TEST_HOST,
    target_port: int = DEFAULT_TEST_PORT,
    path: Path = CONFIG_PATH,
) -> None:
    payload = {
        "mode": mode,
        "selected_id": selected_id,
        "target_host": target_host,
        "target_port": target_port,
        "proxies": [
            {
                "id": p.id,
                "protocol": p.protocol,
                "host": p.host,
                "port": p.port,
                "secret": p.secret,
                "username": p.username,
                "password": p.password,
            }
            for p in proxies
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_proxy_uri(uri: str) -> Optional[ProxyEntry]:
    raw = uri.strip()
    if not raw:
        return None
    try:
        if raw.startswith(("tg://proxy", "https://t.me/proxy")):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(raw).query)
            server = qs.get("server", [""])[0]
            port = int(qs.get("port", ["443"])[0])
            secret = qs.get("secret", [""])[0]
            if server:
                return ProxyEntry(
                    id=f"p_{int(time.time() * 1000)}",
                    protocol="MTPROTO",
                    host=server,
                    port=port,
                    secret=secret,
                )
        if "://" not in raw:
            raw = f"socks5://{raw}"
        parsed = urllib.parse.urlparse(raw)
        if not parsed.hostname or not parsed.port:
            return None
        scheme = parsed.scheme.lower()
        proto = "SOCKS5" if "socks" in scheme else ("WEB" if scheme == "https" else "HTTP")
        return ProxyEntry(
            id=f"p_{int(time.time() * 1000)}",
            protocol=proto,
            host=parsed.hostname,
            port=parsed.port,
            username=urllib.parse.unquote(parsed.username or ""),
            password=urllib.parse.unquote(parsed.password or ""),
        )
    except Exception:
        return None


@dataclass
class IpCheckResult:
    source_id: str
    name: str
    region: str
    ok: bool
    ip: str = ""
    location: str = ""
    isp: str = ""
    latency_ms: Optional[int] = None
    error: str = ""


IP_SOURCES = [
    {"id": "ip_sb", "name": "IP.SB 国际", "region": "海外出口", "host": "api.ip.sb", "port": 443, "path": "/geoip", "kind": "ip_sb"},
    {"id": "ipinfo", "name": "IPinfo.io", "region": "海外出口", "host": "ipinfo.io", "port": 443, "path": "/json", "kind": "ipinfo"},
    {"id": "ipify", "name": "ipify IPv4", "region": "海外出口", "host": "api.ipify.org", "port": 443, "path": "/?format=json", "kind": "ipify"},
    {"id": "ipwho", "name": "ipwho.is", "region": "全球节点", "host": "ipwho.is", "port": 443, "path": "/", "kind": "ipwho"},
    {"id": "cf_trace", "name": "Cloudflare", "region": "CDN 节点", "host": "www.cloudflare.com", "port": 443, "path": "/cdn-cgi/trace", "kind": "cf_trace"},
    {"id": "ip_api", "name": "IP-API", "region": "海外出口", "host": "ip-api.com", "port": 80, "path": "/json/?lang=zh-CN", "kind": "ip_api"},
    {"id": "pconline", "name": "太平洋电脑网", "region": "国内出口", "host": "whois.pconline.com.cn", "port": 443, "path": "/ipJson.jsp?json=true", "kind": "pconline"},
]


def _http_get_via_socket(
    target_host: str,
    target_port: int,
    path: str,
    proxy: Optional[ProxyEntry] = None,
    timeout: float = 5.0,
) -> Tuple[int, str]:
    sock: Optional[socket.socket] = None
    wrapped: Optional[socket.socket] = None
    try:
        if proxy is not None:
            proto = proxy.protocol.upper()
            sock = socket.create_connection((proxy.host, proxy.port), timeout=timeout)
            sock.settimeout(timeout)
            if proto == "SOCKS5":
                sock.sendall(b"\x05\x02\x00\x02" if proxy.username else b"\x05\x01\x00")
                m = sock.recv(2)
                if len(m) < 2 or m[0] != 0x05 or m[1] == 0xFF:
                    raise OSError("SOCKS5 握手失败")
                if m[1] == 0x02:
                    u = proxy.username.encode("utf-8")[:255]
                    p = proxy.password.encode("utf-8")[:255]
                    sock.sendall(struct.pack("!BB", 1, len(u)) + u + struct.pack("!B", len(p)) + p)
                    ar = sock.recv(2)
                    if len(ar) < 2 or ar[1] != 0x00:
                        raise OSError("SOCKS5 认证失败")
                tb = target_host.encode("ascii")
                sock.sendall(struct.pack("!BBBB", 5, 1, 0, 3) + struct.pack("!B", len(tb)) + tb + struct.pack("!H", target_port))
                hd = sock.recv(4)
                if len(hd) < 4 or hd[1] != 0x00:
                    raise OSError("SOCKS5 隧道建立失败")
                atyp = hd[3]
                if atyp == 1:
                    sock.recv(6)
                elif atyp == 3:
                    al = sock.recv(1)
                    if al:
                        sock.recv(al[0] + 2)
                elif atyp == 4:
                    sock.recv(18)
            elif proto in ("HTTP", "WEB"):
                auth_h = ""
                if proxy.username:
                    tok = base64.b64encode(f"{proxy.username}:{proxy.password}".encode("utf-8")).decode("ascii")
                    auth_h = f"Proxy-Authorization: Basic {tok}\r\n"
                sock.sendall(
                    f"CONNECT {target_host}:{target_port} HTTP/1.1\r\nHost: {target_host}:{target_port}\r\n{auth_h}\r\n".encode("ascii")
                )
                resp = sock.recv(1024).decode("latin-1", errors="ignore")
                if "200" not in (resp.splitlines()[0] if resp else ""):
                    raise OSError("HTTP 隧道建立失败")
            else:
                raise OSError("MTProto 不支持 HTTP 出站探测")
        else:
            sock = socket.create_connection((target_host, target_port), timeout=timeout)
            sock.settimeout(timeout)

        active_sock: socket.socket = sock
        if target_port == 443:
            ctx = ssl.create_default_context()
            wrapped = ctx.wrap_socket(sock, server_hostname=target_host)
            active_sock = wrapped

        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {target_host}\r\n"
            f"User-Agent: Mozilla/5.0 ProxyPing/1.0\r\n"
            f"Accept: application/json,text/plain,*/*\r\n"
            f"Accept-Encoding: identity\r\n"
            f"Connection: close\r\n\r\n"
        ).encode("ascii")
        active_sock.sendall(req)

        buf = bytearray()
        content_length: Optional[int] = None
        is_chunked = False
        header_end = -1
        while True:
            data = active_sock.recv(4096)
            if not data:
                break
            buf.extend(data)
            if header_end == -1:
                header_end = buf.find(b"\r\n\r\n")
                if header_end != -1:
                    hdr_str = bytes(buf[:header_end]).decode("latin-1", errors="ignore").lower()
                    is_chunked = "transfer-encoding: chunked" in hdr_str
                    for line in hdr_str.splitlines():
                        if line.startswith("content-length:"):
                            val = line.split(":", 1)[1].strip()
                            if val.isdigit():
                                content_length = int(val)
            if header_end != -1:
                body_len = len(buf) - (header_end + 4)
                if content_length is not None and body_len >= content_length:
                    break
                if is_chunked and bytes(buf[header_end + 4:]).endswith(b"0\r\n\r\n"):
                    break

        raw = bytes(buf)
        header_bytes, _, body_bytes = raw.partition(b"\r\n\r\n")
        header_text = header_bytes.decode("latin-1", errors="ignore")
        status_line = header_text.splitlines()[0] if header_text else ""
        code = int(status_line.split()[1]) if len(status_line.split()) > 1 else 0
        encoding = "gbk" if "gbk" in header_text.lower() or "gb2312" in header_text.lower() else "utf-8"

        if is_chunked:
            decoded = []
            idx = 0
            while idx < len(body_bytes):
                nl = body_bytes.find(b"\r\n", idx)
                if nl == -1:
                    break
                size_hex = body_bytes[idx:nl].split(b";")[0].strip()
                if not size_hex:
                    break
                sz = int(size_hex, 16)
                if sz == 0:
                    break
                start_i = nl + 2
                decoded.append(body_bytes[start_i:start_i + sz])
                idx = start_i + sz + 2
            body_text = b"".join(decoded).decode(encoding, errors="replace")
        else:
            body_text = body_bytes.decode(encoding, errors="replace")
        return code, body_text
    finally:
        for s in (wrapped, sock):
            if s:
                try:
                    s.close()
                except OSError:
                    pass


def check_ip_source(
    source: Dict,
    proxy: Optional[ProxyEntry] = None,
    timeout: float = 5.0,
) -> IpCheckResult:
    start = time.perf_counter()
    try:
        code, body = _http_get_via_socket(
            source["host"],
            int(source["port"]),
            source["path"],
            proxy=proxy,
            timeout=timeout,
        )
        latency = max(1, int((time.perf_counter() - start) * 1000))
        if code < 200 or code >= 400:
            return IpCheckResult(
                source_id=source["id"],
                name=source["name"],
                region=source["region"],
                ok=False,
                latency_ms=latency,
                error=f"HTTP {code}",
            )

        kind = source["kind"]
        ip = ""
        location = ""
        isp = ""
        if kind == "cf_trace":
            kv = dict(line.split("=", 1) for line in body.splitlines() if "=" in line)
            ip = kv.get("ip", "")
            loc = kv.get("loc", "")
            colo = kv.get("colo", "")
            location = f"{loc} ({colo})" if colo else loc
            isp = "Cloudflare Edge"
        else:
            data = json.loads(body.strip())
            if kind == "ip_sb":
                ip = data.get("ip", "")
                location = " · ".join(x for x in (data.get("country"), data.get("city")) if x)
                isp = data.get("organization") or data.get("isp") or ""
            elif kind == "ipinfo":
                ip = data.get("ip", "")
                location = " · ".join(x for x in (data.get("country"), data.get("region"), data.get("city")) if x)
                isp = data.get("org", "")
            elif kind == "ipify":
                ip = data.get("ip", "")
                location = "出口验证"
                isp = "ipify"
            elif kind == "ipwho":
                ip = data.get("ip", "")
                location = " · ".join(x for x in (data.get("country"), data.get("city")) if x)
                conn = data.get("connection") or {}
                isp = conn.get("isp") or conn.get("org") or ""
            elif kind == "ip_api":
                ip = data.get("query", "")
                location = " · ".join(x for x in (data.get("country"), data.get("city")) if x)
                isp = data.get("isp") or data.get("org") or ""
            elif kind == "pconline":
                ip = data.get("ip", "")
                location = data.get("addr", "").strip()
                isp = "国内归属地库"

        if not ip:
            return IpCheckResult(
                source_id=source["id"],
                name=source["name"],
                region=source["region"],
                ok=False,
                latency_ms=latency,
                error="未解析到 IP",
            )
        return IpCheckResult(
            source_id=source["id"],
            name=source["name"],
            region=source["region"],
            ok=True,
            ip=ip,
            location=location,
            isp=isp,
            latency_ms=latency,
        )
    except Exception as exc:
        return IpCheckResult(
            source_id=source["id"],
            name=source["name"],
            region=source["region"],
            ok=False,
            error=str(exc) or "请求失败",
        )

