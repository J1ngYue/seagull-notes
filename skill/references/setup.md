# 运行环境

Windows 使用真实 Python 解释器的绝对路径；本机使用 `D:\software\Anaconda\python.exe`，其他机器按安装位置调整。默认只读取平台字幕；不需要下载 Whisper 模型，不运行 `.cmd/.bat` 启动器，也不自动切换解释器。

字幕获取依赖 `yt-dlp/httpx/lxml`，图文渲染依赖 `Markdown/pymdown-extensions/lxml`。缺少时在指定解释器安装：

```powershell
& 'D:\software\Anaconda\python.exe' -m pip install yt-dlp httpx lxml Markdown pymdown-extensions
```

完整依赖可在仓库根安装 `pip install -e ".[notes]"`。网页/PDF 使用 `readability-lxml/pymupdf`。免登录字幕模式使用 `--anonymous`；需要本地 ASR 时安装 `pip install -e ".[notes,asr]"`，并显式使用 `--allow-asr`。

本地 B站采集器安装 `pip install -e ".[notes,browser]"`（Playwright 与 qrcode/Pillow），然后运行 `fetch.py '<BV视频链接>' --local-browser`。它优先使用已安装的 Chrome；没有 Chrome 时可显式运行 `python -m playwright install chromium` 安装浏览器，无需 ASR 模型。需要认证时展示日志中的本地 `LOGIN_URL`，用 B站 App 扫码确认；之后自动复用专用配置。专用配置被另一个采集进程占用时，先完成该进程再启动下一次；不要同时启动同一配置。

MCP 是独立的可选依赖：仅需要 MCP 服务端时安装 `pip install -e ".[mcp]"`。它会引入自己的 Web 服务依赖，建议使用独立 Python 环境；普通 skill、字幕抓取和本地 ASR 都不需要它。

ASR 模型准备：`python -m seagull_notes.cli prepare-model`（默认 large-v3 约 3 GB）。默认 GPU 配置为 CUDA/float16；CPU 可设 `SEAGULL_NOTES_ASR_DEVICE=cpu` 与 `SEAGULL_NOTES_ASR_COMPUTE=int8`。下载音频转码依赖可用的 FFmpeg/ffprobe。不在默认字幕流程中自动安装 GPU 依赖或下载模型。

浏览器登录按 [browser-subtitles.md](browser-subtitles.md) 操作。新采集器不依赖旧 `login.py/setup_cookies.py` 的 Cookie 导出方案。

路径：源代码 `<项目根>/src`；字幕缓存和媒体 `<项目根>/data`；笔记 `<项目根>/data/artifacts`。`SEAGULL_NOTES_HOME` 可覆盖项目根目录。
