# 轻量级跨平台网络代理连通性测试工具 (Python Tkinter)

基于 Python 3.8+ 标准库实现，**零第三方依赖**，原生支持 **Windows / Linux / macOS**。

## 文件架构

- `proxy_tester.py`: 主窗口（「代理设置」）与编辑弹窗（「编辑代理」）GUI，多线程调度与队列异步刷新。
- `proxy_core.py`: 跨平台网络探测内核（SOCKS5 RFC 1928/1929 握手、HTTP/WEB CONNECT 隧道探测、MTProto 密钥校验与 TCP 延迟测试），以及跨平台系统代理读取（Windows 注册表、`macOS scutil`、`Linux env / gsettings`）。
- `ui_widgets.py`: 基于 Tkinter Canvas 的轻量自定义暗色主题控件（自定义圆形单选框、底部下划线输入框、跨平台滚轮容器与高 DPI 适配）。

## 快速运行

```bash
cd python_app
python3 proxy_tester.py
```

## 跨平台说明

- **Windows**: 自动启用 Per-Monitor DPI 感知，字体优先匹配 `Microsoft YaHei UI`，通过 `urllib.request.getproxies()` 读取系统 Internet 代理设置。
- **macOS**: 字体优先匹配 `PingFang SC`，使用 `scutil --proxy` 解析系统 SOCKS5 / HTTP / HTTPS 代理。
- **Linux**: 字体优先匹配 `Noto Sans CJK SC`，支持 `<Button-4>/<Button-5>` 滚轮事件，并自动读取环境变量及 GNOME `gsettings` 代理配置。
