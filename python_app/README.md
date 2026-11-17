# ProxyPing Tkinter 桌面端

基于 Python 3.8+ 标准库实现，**零第三方运行依赖**，原生支持 **Windows / Linux / macOS**。

## 模块说明

- `proxy_tester.py`: 双栏主窗口（「代理设置」+「多源出口 IP 检测」）与「编辑代理」弹窗 GUI。
- `proxy_core.py`: SOCKS5 / HTTP / WEB / MTProto 连通性测试内核、通过代理隧道的多源出口 IP 探测，以及跨平台系统代理自动读取。
- `ui_widgets.py`: 基于 Tkinter Canvas 的暗色主题控件（自定义圆形单选框、下划线输入框、跨平台滚轮容器、Windows Per-Monitor DPI 适配）。
- `build_release.py`: 一键调用 PyInstaller 生成单文件可执行程序与发布压缩包。

## 直接运行

```bash
python3 proxy_tester.py
```

## 本地打包为可执行程序

```bash
pip install pyinstaller
python3 build_release.py
```
