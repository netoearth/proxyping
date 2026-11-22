import React, {useEffect, useRef, useState} from 'react';
import {MoreVertical} from 'lucide-react';
import type {ProxyEntry, ProxyProtocol} from '../types/proxy';

interface TelegramProxyWindowProps {
  proxies: ProxyEntry[];
  selectedId: string | null;
  targetHost: string;
  targetPort: number;
  systemProxies: Array<{protocol: string; host: string; port: number}>;
  onSelectProxy: (id: string) => void;
  onTestProxy: (id: string) => void;
  onTestAll: () => void;
  onSaveProxy: (entry: ProxyEntry, isNew: boolean) => void;
  onDeleteProxy: (id: string) => void;
  onClearUnavailable: () => void;
  onUpdateTarget: (host: string, port: number) => void;
  onImportUri: (uri: string) => boolean;
}

const PROTOCOLS: ProxyProtocol[] = ['MTPROTO', 'SOCKS5', 'HTTP', 'WEB'];

function RadioCircle({selected}: {selected: boolean}) {
  return (
    <span
      className={`inline-flex items-center justify-center w-[20px] h-[20px] rounded-full border-2 shrink-0 transition-colors duration-150 ${
        selected ? 'border-[#64b5f6]' : 'border-[#6b7c8e]'
      }`}
    >
      {selected && <span className="w-[10px] h-[10px] rounded-full bg-[#64b5f6]" />}
    </span>
  );
}

export function TelegramProxyWindow({
  proxies,
  selectedId,
  targetHost,
  targetPort,
  systemProxies,
  onSelectProxy,
  onTestProxy,
  onTestAll,
  onSaveProxy,
  onDeleteProxy,
  onClearUnavailable,
  onUpdateTarget,
  onImportUri,
}: TelegramProxyWindowProps) {
  const [editingEntry, setEditingEntry] = useState<ProxyEntry | null>(null);
  const [isNewEntry, setIsNewEntry] = useState(false);
  const [openRowMenuId, setOpenRowMenuId] = useState<string | null>(null);
  const [globalMenuOpen, setGlobalMenuOpen] = useState(false);
  const [copiedBanner, setCopiedBanner] = useState<string | null>(null);

  // Sub-modals for target configuration & URI import (replaces window.prompt)
  const [targetDialogOpen, setTargetDialogOpen] = useState(false);
  const [targetDraft, setTargetDraft] = useState(`${targetHost}:${targetPort}`);
  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const [importDraft, setImportDraft] = useState('');
  const [importError, setImportError] = useState('');

  // Form state for Edit Proxy dialog (matches Screenshot 1)
  const [formProto, setFormProto] = useState<ProxyProtocol>('MTPROTO');
  const [formHost, setFormHost] = useState('');
  const [formPort, setFormPort] = useState('');
  const [formSecret, setFormSecret] = useState('');
  const [formUser, setFormUser] = useState('');
  const [formPass, setFormPass] = useState('');
  const [formError, setFormError] = useState('');

  const menuContainerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const handleOutside = (e: MouseEvent) => {
      if (menuContainerRef.current && !menuContainerRef.current.contains(e.target as Node)) {
        setOpenRowMenuId(null);
        setGlobalMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleOutside);
    return () => document.removeEventListener('mousedown', handleOutside);
  }, []);

  const flashCopied = (msg: string) => {
    setCopiedBanner(msg);
    setTimeout(() => setCopiedBanner(null), 2200);
  };

  const openAddDialog = () => {
    setIsNewEntry(true);
    setEditingEntry({
      id: `p_${Date.now()}`,
      protocol: 'SOCKS5',
      host: '',
      port: 1080,
      secret: '',
      username: '',
      password: '',
      status: 'untested',
      latencyMs: null,
      detail: '',
    });
    setFormProto('SOCKS5');
    setFormHost('');
    setFormPort('');
    setFormSecret('');
    setFormUser('');
    setFormPass('');
    setFormError('');
  };

  const openEditDialog = (entry: ProxyEntry) => {
    setIsNewEntry(false);
    setEditingEntry(entry);
    setFormProto(entry.protocol);
    setFormHost(entry.host);
    setFormPort(String(entry.port));
    setFormSecret(entry.secret);
    setFormUser(entry.username);
    setFormPass(entry.password);
    setFormError('');
    setOpenRowMenuId(null);
  };

  const handleSaveForm = (e: React.FormEvent) => {
    e.preventDefault();
    const cleanHost = formHost.trim();
    const portNum = Number(formPort.trim());
    if (!cleanHost) {
      setFormError('请输入代理服务器地址');
      return;
    }
    if (!Number.isInteger(portNum) || portNum < 1 || portNum > 65535) {
      setFormError('请输入有效端口 (1 - 65535)');
      return;
    }
    if (!editingEntry) return;
    onSaveProxy(
      {
        ...editingEntry,
        protocol: formProto,
        host: cleanHost,
        port: portNum,
        secret: formProto === 'MTPROTO' ? formSecret.trim() : '',
        username: formProto === 'MTPROTO' ? '' : formUser.trim(),
        password: formProto === 'MTPROTO' ? '' : formPass.trim(),
      },
      isNewEntry,
    );
    setEditingEntry(null);
  };

  const formatShareUri = (p: ProxyEntry) => {
    if (p.protocol === 'MTPROTO') {
      const qs = new URLSearchParams({
        server: p.host,
        port: String(p.port),
        secret: p.secret,
      });
      return `tg://proxy?${qs.toString()}`;
    }
    const scheme = p.protocol === 'SOCKS5' ? 'socks5' : 'http';
    const auth = p.username
      ? `${encodeURIComponent(p.username)}${p.password ? `:${encodeURIComponent(p.password)}` : ''}@`
      : '';
    return `${scheme}://${auth}${p.host}:${p.port}`;
  };

  const handleCopyOne = async (p: ProxyEntry) => {
    setOpenRowMenuId(null);
    try {
      await navigator.clipboard.writeText(formatShareUri(p));
      flashCopied('已复制代理链接');
    } catch {
      flashCopied('复制失败，请手动复制');
    }
  };

  const sysProxySummary =
    systemProxies.length > 0
      ? systemProxies.map((s) => `${s.protocol} ${s.host}:${s.port}`).join(', ')
      : '未检测到系统环境变量代理';

  return (
    <div
      ref={menuContainerRef}
      className="relative w-full max-w-[400px] mx-auto bg-[#1e2732] border border-[#2b3745] rounded-lg shadow-2xl overflow-hidden select-none"
    >
      {/* Main Window: 代理设置 (Screenshot 2) */}
      <div className="flex flex-col h-[620px]">
        {/* Header */}
        <div className="flex items-center justify-between px-5 pt-4 pb-3">
          <h2 className="text-[16px] font-semibold text-[#f5f5f5] tracking-tight">
            代理设置
          </h2>
          <div className="relative">
            <button
              type="button"
              onClick={() => setGlobalMenuOpen((v) => !v)}
              aria-label="更多代理选项"
              className="p-1.5 rounded-md text-[#7f91a4] hover:text-[#f5f5f5] hover:bg-[#26323e] transition-colors cursor-pointer"
            >
              <MoreVertical className="w-4 h-4" />
            </button>

            {globalMenuOpen && (
              <div className="absolute right-0 mt-1 w-44 bg-[#242f3d] border border-[#303e4e] rounded-md shadow-xl py-1 z-30 text-[13px]">
                <button
                  type="button"
                  onClick={() => {
                    setGlobalMenuOpen(false);
                    onTestAll();
                  }}
                  className="w-full text-left px-3.5 py-2 text-[#f5f5f5] hover:bg-[#2f3d4d] cursor-pointer"
                >
                  全部重新测试
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setGlobalMenuOpen(false);
                    setImportDraft('');
                    setImportError('');
                    setImportDialogOpen(true);
                  }}
                  className="w-full text-left px-3.5 py-2 text-[#f5f5f5] hover:bg-[#2f3d4d] cursor-pointer"
                >
                  导入代理链接
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setGlobalMenuOpen(false);
                    setTargetDraft(`${targetHost}:${targetPort}`);
                    setTargetDialogOpen(true);
                  }}
                  className="w-full text-left px-3.5 py-2 text-[#f5f5f5] hover:bg-[#2f3d4d] cursor-pointer"
                >
                  设置探测目标
                </button>
                <div className="my-1 border-t border-[#303e4e]" />
                <button
                  type="button"
                  onClick={() => {
                    setGlobalMenuOpen(false);
                    onClearUnavailable();
                  }}
                  className="w-full text-left px-3.5 py-2 text-[#e05a5a] hover:bg-[#2f3d4d] cursor-pointer"
                >
                  清空不可用代理
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Recessed Notice Band */}
        <div className="bg-[#17212b] px-5 py-3 border-y border-[#1b2632] shrink-0">
          <p className="text-[12.5px] leading-[1.45] text-[#7f91a4]">
            代理服务器可能有助于解决个别地区无法连接目标网络的情况。
            <span className="block mt-1 text-[#8ba1b7] tabular-nums">
              探测目标: {targetHost}:{targetPort} · 系统代理: {sysProxySummary}
            </span>
          </p>
        </div>

        {/* Scrollable Proxy Items */}
        <div className="flex-1 min-h-0 overflow-y-auto py-1">
          {proxies.length === 0 ? (
            <div className="py-12 px-6 text-center text-[13px] text-[#7f91a4]">
              暂无代理配置，点击右下角「添加」创建代理。
            </div>
          ) : (
            proxies.map((entry) => {
              const isSelected = entry.id === selectedId;
              return (
                <div
                  key={entry.id}
                  onClick={() => onSelectProxy(entry.id)}
                  className="relative flex items-center justify-between px-5 py-2.5 hover:bg-[#242f3c] transition-colors cursor-pointer"
                >
                  <div className="flex items-center gap-3.5 min-w-0">
                    <RadioCircle selected={isSelected} />
                    <div className="min-w-0">
                      <div className="flex items-baseline gap-1.5 truncate">
                        <span className="text-[14px] font-semibold text-[#f5f5f5]">
                          {entry.protocol}
                        </span>
                        <span className="text-[14px] text-[#7f91a4] font-mono tabular-nums truncate">
                          {entry.host}:{entry.port}
                        </span>
                      </div>
                      <div className="text-[12.5px] mt-0.5 tabular-nums">
                        {entry.status === 'available' && entry.latencyMs !== null && (
                          <span className="text-[#45b97c]">
                            可用 (ping: {entry.latencyMs} 毫秒)
                          </span>
                        )}
                        {entry.status === 'unavailable' && (
                          <span className="text-[#e05a5a]">不可用</span>
                        )}
                        {entry.status === 'testing' && (
                          <span className="text-[#64b5f6]">正在测试...</span>
                        )}
                        {entry.status === 'untested' && (
                          <span className="text-[#7f91a4]">未测试</span>
                        )}
                      </div>
                    </div>
                  </div>

                  <div
                    className="relative shrink-0"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <button
                      type="button"
                      onClick={() =>
                        setOpenRowMenuId((cur) => (cur === entry.id ? null : entry.id))
                      }
                      aria-label={`操作 ${entry.host}:${entry.port}`}
                      className="p-1.5 rounded-md text-[#7f91a4] hover:text-[#f5f5f5] hover:bg-[#2c3a49] transition-colors cursor-pointer"
                    >
                      <MoreVertical className="w-4 h-4" />
                    </button>

                    {openRowMenuId === entry.id && (
                      <div className="absolute right-0 mt-1 w-36 bg-[#242f3d] border border-[#303e4e] rounded-md shadow-xl py-1 z-30 text-[13px]">
                        <button
                          type="button"
                          onClick={() => {
                            setOpenRowMenuId(null);
                            onTestProxy(entry.id);
                          }}
                          className="w-full text-left px-3.5 py-2 text-[#f5f5f5] hover:bg-[#2f3d4d] cursor-pointer"
                        >
                          立即测试
                        </button>
                        <button
                          type="button"
                          onClick={() => openEditDialog(entry)}
                          className="w-full text-left px-3.5 py-2 text-[#f5f5f5] hover:bg-[#2f3d4d] cursor-pointer"
                        >
                          编辑代理
                        </button>
                        <button
                          type="button"
                          onClick={() => handleCopyOne(entry)}
                          className="w-full text-left px-3.5 py-2 text-[#f5f5f5] hover:bg-[#2f3d4d] cursor-pointer"
                        >
                          复制链接
                        </button>
                        <div className="my-1 border-t border-[#303e4e]" />
                        <button
                          type="button"
                          onClick={() => {
                            setOpenRowMenuId(null);
                            onDeleteProxy(entry.id);
                          }}
                          className="w-full text-left px-3.5 py-2 text-[#e05a5a] hover:bg-[#2f3d4d] cursor-pointer"
                        >
                          删除
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Footer Buttons */}
        <div className="flex items-center justify-between gap-2 px-4 py-3 bg-[#1e2732] border-t border-[#232e3a] shrink-0">
          <span className="text-[12px] text-[#7f91a4] pl-1 truncate">
            {copiedBanner || ''}
          </span>
          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={onTestAll}
              className="px-4 py-1.5 rounded text-[13.5px] font-medium text-[#64b5f6] hover:bg-[#26323e] transition-colors whitespace-nowrap shrink-0 cursor-pointer"
            >
              全部测试
            </button>
            <button
              type="button"
              onClick={openAddDialog}
              className="px-4 py-1.5 rounded text-[13.5px] font-medium text-[#64b5f6] hover:bg-[#26323e] transition-colors whitespace-nowrap shrink-0 cursor-pointer"
            >
              添加
            </button>
          </div>
        </div>
      </div>

      {/* Overlay Modal: 编辑代理 (Screenshot 1) */}
      {editingEntry && (
        <div className="absolute inset-0 bg-black/55 flex items-center justify-center p-3 z-40">
          <form
            onSubmit={handleSaveForm}
            className="w-full max-w-[352px] bg-[#1e2732] border border-[#2c3847] rounded-lg shadow-2xl px-6 py-5 flex flex-col"
          >
            <h3 className="text-[16px] font-semibold text-[#f5f5f5] mb-3.5">
              {isNewEntry ? '添加代理' : '编辑代理'}
            </h3>

            {/* Protocol Radios */}
            <div className="space-y-1.5 mb-3.5">
              {PROTOCOLS.map((proto) => (
                <button
                  key={proto}
                  type="button"
                  onClick={() => setFormProto(proto)}
                  className="w-full flex items-center gap-3.5 py-1.5 px-1 -mx-1 rounded hover:bg-[#26323e] transition-colors text-left cursor-pointer"
                >
                  <RadioCircle selected={formProto === proto} />
                  <span className="text-[14px] text-[#f5f5f5]">{proto}</span>
                </button>
              ))}
            </div>

            <p className="text-[12.5px] leading-[1.45] text-[#7f91a4] mb-4">
              {formProto === 'MTPROTO'
                ? '将验证 MTProto 密钥格式并测试服务器 TCP 端口连通性与往返延迟。'
                : '将执行完整协议握手并访问探测目标测量端到端延迟（毫秒）。'}
            </p>

            {/* 代理地址 */}
            <div className="mb-4">
              <div className="text-[13.5px] font-semibold text-[#f5f5f5] mb-2">
                代理地址
              </div>
              <div className="flex items-end gap-4">
                <label className="flex-1 block">
                  <span className="block text-[11.5px] text-[#64b5f6] mb-0.5">
                    服务器
                  </span>
                  <input
                    type="text"
                    value={formHost}
                    onChange={(e) => setFormHost(e.target.value)}
                    placeholder="127.0.0.1"
                    className="w-full bg-transparent text-[14px] text-[#f5f5f5] placeholder-[#526375] pb-1.5 border-b-2 border-[#3b4a59] focus:border-[#64b5f6] focus:outline-none transition-colors font-mono"
                    autoFocus
                  />
                </label>
                <label className="w-[74px] block">
                  <span className="block text-[11.5px] text-[#7f91a4] mb-0.5">
                    端口
                  </span>
                  <input
                    type="text"
                    inputMode="numeric"
                    value={formPort}
                    onChange={(e) => setFormPort(e.target.value)}
                    placeholder="1080"
                    className="w-full bg-transparent text-[14px] text-[#f5f5f5] placeholder-[#526375] pb-1.5 border-b-2 border-[#3b4a59] focus:border-[#64b5f6] focus:outline-none transition-colors font-mono tabular-nums"
                  />
                </label>
              </div>
            </div>

            {/* 认证信息 */}
            <div className="mb-4">
              <div className="text-[13.5px] font-semibold text-[#f5f5f5] mb-2">
                认证信息
              </div>
              {formProto === 'MTPROTO' ? (
                <label className="block">
                  <span className="block text-[11.5px] text-[#7f91a4] mb-0.5">
                    密钥
                  </span>
                  <input
                    type="text"
                    value={formSecret}
                    onChange={(e) => setFormSecret(e.target.value)}
                    placeholder="32 位十六进制密钥或 dd/ee 前缀密钥"
                    className="w-full bg-transparent text-[14px] text-[#f5f5f5] placeholder-[#526375] pb-1.5 border-b-2 border-[#3b4a59] focus:border-[#64b5f6] focus:outline-none transition-colors font-mono"
                  />
                </label>
              ) : (
                <div className="space-y-3">
                  <label className="block">
                    <span className="block text-[11.5px] text-[#7f91a4] mb-0.5">
                      用户名 (可选)
                    </span>
                    <input
                      type="text"
                      value={formUser}
                      onChange={(e) => setFormUser(e.target.value)}
                      className="w-full bg-transparent text-[14px] text-[#f5f5f5] pb-1.5 border-b-2 border-[#3b4a59] focus:border-[#64b5f6] focus:outline-none transition-colors"
                    />
                  </label>
                  <label className="block">
                    <span className="block text-[11.5px] text-[#7f91a4] mb-0.5">
                      密码 (可选)
                    </span>
                    <input
                      type="password"
                      value={formPass}
                      onChange={(e) => setFormPass(e.target.value)}
                      className="w-full bg-transparent text-[14px] text-[#f5f5f5] pb-1.5 border-b-2 border-[#3b4a59] focus:border-[#64b5f6] focus:outline-none transition-colors"
                    />
                  </label>
                </div>
              )}
            </div>

            {formError && (
              <div className="text-[12px] text-[#e05a5a] mb-3">{formError}</div>
            )}

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setEditingEntry(null)}
                className="px-4 py-1.5 rounded text-[13.5px] font-medium text-[#64b5f6] hover:bg-[#26323e] transition-colors cursor-pointer"
              >
                取消
              </button>
              <button
                type="submit"
                className="px-4 py-1.5 rounded text-[13.5px] font-medium text-[#64b5f6] hover:bg-[#26323e] transition-colors cursor-pointer"
              >
                保存
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Target Configuration Dialog */}
      {targetDialogOpen && (
        <div className="absolute inset-0 bg-black/55 flex items-center justify-center p-4 z-40">
          <div className="w-full max-w-[330px] bg-[#1e2732] border border-[#2c3847] rounded-lg shadow-2xl p-5">
            <h3 className="text-[15px] font-semibold text-[#f5f5f5] mb-2">
              设置探测目标
            </h3>
            <p className="text-[12.5px] text-[#7f91a4] mb-3">
              SOCKS5 / HTTP 代理将尝试通过隧道访问该地址 (host:port)。
            </p>
            <input
              type="text"
              value={targetDraft}
              onChange={(e) => setTargetDraft(e.target.value)}
              className="w-full bg-transparent text-[14px] text-[#f5f5f5] pb-1.5 border-b-2 border-[#3b4a59] focus:border-[#64b5f6] focus:outline-none font-mono mb-4"
            />
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setTargetDialogOpen(false)}
                className="px-3.5 py-1.5 rounded text-[13px] font-medium text-[#64b5f6] hover:bg-[#26323e] cursor-pointer"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => {
                  const idx = targetDraft.lastIndexOf(':');
                  if (idx > 0) {
                    const h = targetDraft.slice(0, idx).trim();
                    const p = Number(targetDraft.slice(idx + 1).trim());
                    if (h && Number.isInteger(p) && p > 0 && p <= 65535) {
                      onUpdateTarget(h, p);
                      setTargetDialogOpen(false);
                    }
                  }
                }}
                className="px-3.5 py-1.5 rounded text-[13px] font-medium text-[#64b5f6] hover:bg-[#26323e] cursor-pointer"
              >
                确定
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Import URI Dialog */}
      {importDialogOpen && (
        <div className="absolute inset-0 bg-black/55 flex items-center justify-center p-4 z-40">
          <div className="w-full max-w-[330px] bg-[#1e2732] border border-[#2c3847] rounded-lg shadow-2xl p-5">
            <h3 className="text-[15px] font-semibold text-[#f5f5f5] mb-2">
              导入代理链接
            </h3>
            <p className="text-[12.5px] text-[#7f91a4] mb-3">
              支持 socks5://、http:// 或 tg://proxy?... 链接格式。
            </p>
            <input
              type="text"
              value={importDraft}
              onChange={(e) => {
                setImportDraft(e.target.value);
                setImportError('');
              }}
              placeholder="socks5://127.0.0.1:1080"
              className="w-full bg-transparent text-[14px] text-[#f5f5f5] placeholder-[#526375] pb-1.5 border-b-2 border-[#3b4a59] focus:border-[#64b5f6] focus:outline-none font-mono mb-2"
            />
            {importError && (
              <div className="text-[12px] text-[#e05a5a] mb-2">{importError}</div>
            )}
            <div className="flex justify-end gap-2 mt-3">
              <button
                type="button"
                onClick={() => setImportDialogOpen(false)}
                className="px-3.5 py-1.5 rounded text-[13px] font-medium text-[#64b5f6] hover:bg-[#26323e] cursor-pointer"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => {
                  const ok = onImportUri(importDraft);
                  if (ok) {
                    setImportDialogOpen(false);
                  } else {
                    setImportError('无法识别该代理链接格式');
                  }
                }}
                className="px-3.5 py-1.5 rounded text-[13px] font-medium text-[#64b5f6] hover:bg-[#26323e] cursor-pointer"
              >
                导入
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
