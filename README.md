# ProxyPing — 跨平台网络代理连通性与多源出口 IP 检测工具

轻量级跨平台 GUI 工具，支持 **Windows / Linux / macOS**。采用 Python Tkinter 原生标准库构建桌面端（零第三方运行依赖），并附带同构双栏 Web 交互版界面。

## 核心功能

- **代理设置与连通性探测**
  - 支持 **MTPROTO / SOCKS5 / HTTP / WEB** 四种代理协议。
  - **SOCKS5**：RFC 1928 握手与 RFC 1929 用户名/密码认证，建立隧道后执行端到端 HTTP 探测与毫秒级 RTT 测速。
  - **HTTP / WEB**：支持直连代理及 `CONNECT` 隧道握手与 Basic 认证。
  - **MTPROTO**：校验 32 位十六进制及 `dd`/`ee` 前缀密钥格式并测算 TCP 端口延迟。
  - **跨平台系统代理识别**：自动读取 Windows 注册表、macOS `scutil --proxy`、Linux 环境变量与 GNOME `gsettings`。
  - **便捷管理**：支持 `socks5://`、`http://`、`tg://proxy?...` 链接导入、列表一键复制分享及本地配置自动持久化。
- **多源出口 IP 检测（类 IP233.cn）**
  - 并发探测国内与国际多组 IP 来源（`太平洋电脑网`、`IP.SB`、`Cloudflare Trace`、`ipify IPv4`、`ipwho.is`、`IPinfo.io`、`IP-API`）。
  - 实时显示出口 IP、归属地、ISP/ASN 与响应延迟（ms），自动对比多源出口一致性以辅助排查分流规则。
  - 支持切换 **本机直连** 与 **通过当前选中代理出站探测**。

---

## 目录结构

```text
.
├── python_app/                # Python Tkinter 桌面端（零第三方依赖）
│   ├── proxy_tester.py        # 桌面端 GUI 入口（代理设置 + 多源 IP 面板）
│   ├── proxy_core.py          # 探测内核、代理隧道与系统代理发现
│   ├── ui_widgets.py          # 跨平台 Canvas 自绘暗色控件与高 DPI 适配
│   ├── build_release.py       # 本地一键 PyInstaller 打包脚本
│   └── pyproject.toml         # Python 项目元数据
├── src/                       # Web 版双栏 GUI 前端
├── server.ts                  # Web 版探测后端（TCP/SOCKS5/HTTP/IP 检测）
└── .github/workflows/
    ├── ci.yml                 # Push / PR 自动校验
    └── release.yml            # Git Tag 自动构建 Win/macOS/Linux 并发布 Release
```

---

## 快速运行

### 1. 运行 Python Tkinter 桌面端

要求 Python 3.8+（仅使用标准库，无需 `pip install`）：

```bash
python3 python_app/proxy_tester.py
```

> **Linux 提示**：部分精简版 Ubuntu/Debian 需先安装系统 Tkinter 包：
> ```bash
> sudo apt-get update && sudo apt-get install -y python3-tk
> ```

### 2. 运行 Web 版 GUI

要求 Node.js 20+：

```bash
npm install
npm run dev
```

启动后访问 `http://localhost:3000`。

---

## 本地打包发布

如需将 Python Tkinter 桌面端打包为免安装可执行文件（`.exe` / `.app` / Linux 二进制）：

```bash
pip install pyinstaller
python3 python_app/build_release.py
```

打包产物将输出至 `dist_release/` 目录，并自动生成对应平台的压缩包（`.zip` 或 `.tar.gz`）。

---

## 发布到 GitHub 并自动构建多平台安装包

1. **初始化并推送代码到 GitHub 仓库**：

   ```bash
   git init
   git add .
   git commit -m "chore: initial release"
   git branch -M main
   git remote add origin https://github.com/<your-username>/<your-repo>.git
   git push -u origin main
   ```

2. **触发 GitHub Actions 自动打包与 Release 发布**（支持以下任意一种方式）：

   - **方式 A：推送版本标签自动发布**
     ```bash
     git tag v1.0.0
     git push origin v1.0.0
     ```
   - **方式 B：在 GitHub Actions 页面手动触发**
     进入仓库 **Actions → Release Desktop Packages → Run workflow**（可填写版本号如 `v1.0.0`，留空将自动生成 `v1.0.<run_number>`），构建完成后同样会自动发布到 Releases。

3. **获取发布产物**：
   - GitHub Actions 将在 `windows-latest`、`macos-latest`、`ubuntu-latest` 三端并发编译打包。
   - 构建完成后会自动在仓库 **Releases** 页面生成对应版本，并附带：
     - `ProxyPing-windows-x64.zip`（Windows 单文件 `.exe`）
     - `ProxyPing-macos.zip`（macOS `.app` 应用包）
     - `ProxyPing-linux-x64.tar.gz`（Linux 可执行文件）
     - `ProxyPing-python-src.zip`（纯 Python 源码便携包）

---

## 开源协议

本项目基于 [MIT License](LICENSE) 开源。
