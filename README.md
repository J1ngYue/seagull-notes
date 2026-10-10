# Seagull Notes

把 B站、YouTube 等视频链接整理成**图文笔记、思维导图、Markdown 和可离线阅读的 HTML**。

这是一个 Codex skill 与本地 Python 工具集：脚本负责取素材和渲染，当前 AI 客户端负责理解字幕、整理笔记。默认流程无需另配笔记生成 API key。

- **字幕优先**：读取平台字幕，包括平台 AI 字幕，保留可取得的时间轴。
- **免登录先试**：`--anonymous` 不读取 Cookie 文件或浏览器凭证。
- **音频转写可选**：显式允许后，尝试下载可访问音频并在本地转写。
- **浏览器登录交接**：确需登录时，由用户在 Codex 内置浏览器完成，再继续处理。
- **图文交付**：摘要、章节、实际时间定位、配图说明、脑图和完整字幕原文。

![视频到笔记的流程示意图](examples/workflow.svg)

## 快速开始

需要 Python 3.10+。克隆仓库后，在当前 Python 解释器安装：

```bash
git clone https://github.com/J1ngYue/seagull-notes.git
cd seagull-notes
python -m pip install -e ".[notes]"
```

Windows 请使用 Python 的实际绝对路径，避免 Microsoft Store 别名。例如：

```powershell
& 'D:\software\Anaconda\python.exe' -m pip install -e '.[notes]'
```

将仓库内 `skill/` 目录安装为你的 `seagull-notes` skill，例如复制到 `~/.agents/skills/seagull-notes/`。因为已安装项目包，skill 脚本可以导入本仓库源码。也可以直接在仓库的 `skill/` 使用，无需复制。

在 Codex 中发送：

> 用 seagull-notes 把这个视频整理成图文笔记：视频链接

默认按字幕优先处理；取不到完整字幕时如实说明，不用简介、评论或平台总结冒充全文。

## 可以不登录视频平台吗？

**可以尝试，但不能保证所有视频。**

| 视频情况 | 处理方式 |
| --- | --- |
| 公开字幕可取得 | 匿名读取字幕，再整理笔记 |
| 字幕需要登录，但音频公开可下载 | 用户允许后，用本地 ASR 转写音频 |
| 平台要求登录、验证或会员权限 | 需要相应访问权限，匿名模式无法保证处理 |
| 只有当前一句 CC，没有可导出的全文 | 不声称已读完整视频；报告限制或使用明确允许的 ASR |

有些笔记产品让用户无需登录 B站/YouTube，也不代表它的后台没有使用服务器会话、缓存或转写。这些具体实现不能仅从界面推断。CuteNote 的[公开说明](https://cutenote.co/youtube-summarizer)描述了字幕获取和音频转写两条路径，并说明生成自己的笔记需要登录 CuteNote。

### 只读取匿名字幕

```bash
python skill/scripts/fetch.py "视频链接" --anonymous
```

默认不下载视频、不运行 ASR、不下载模型。stdout 返回 JSON，日志写 stderr。`content` 是正文，`segments` 是可取得的 `start/end/text` 时间轴，`origin` 标明真实来源。长文本支持 `--offset/--max-chars` 分页。

### 允许匿名音频转写

```bash
python -m pip install -e ".[notes,asr]"
python -m seagull_notes.cli prepare-model
python skill/scripts/fetch.py "视频链接" --anonymous --allow-asr
```

默认 large-v3 模型约 3 GB，准备模型是显式的一次性操作。音频转换需要 FFmpeg/ffprobe。默认 ASR 使用 CUDA/float16；CPU 可配置 `SEAGULL_NOTES_ASR_DEVICE=cpu` 和 `SEAGULL_NOTES_ASR_COMPUTE=int8`，按需选择 `SEAGULL_NOTES_ASR_MODEL`。

ASR 是本地语音识别，**不是平台 AI 字幕**；运行时间与音频时长、硬件有关。匿名音频下载也可能被平台限制。单独的 `--allow-asr` 不代表禁止使用已有 Cookie，要完全匿名需同时加 `--anonymous`。

### 图文页面示例

```bash
python skill/scripts/notebook.py examples/notebook.json --out data/artifacts/demo
```

打开 `data/artifacts/demo.html`。示例为界面与流程演示，不是已处理的真实视频。页面参考 [CuteNote](https://cutenote.cc/) 的暖白卡片布局，支持图文笔记／脑图／Markdown／字幕原文切换，以及打印 PDF。

输入 JSON 格式见 [notebook-format.md](skill/references/notebook-format.md)。真实配图应来自经过核实的视频画面，带有实际时间和图注；自绘解释图须注明示意图。HTML 将图片嵌入文件，Markdown 保留原本地图片路径。

## 浏览器和本地文件

内置浏览器登录与 Python 下载器是不同会话，不能假定登录后 Cookie 自动传给脚本。YouTube 可尝试当前浏览器提供的 transcript 导出；其他平台依赖当前网页和工具开放的字幕能力。详见 [browser-subtitles.md](skill/references/browser-subtitles.md)。

原项目的网页、PDF、字幕文件、CLI 和 MCP 工具也保留在 `src/`。本次发布的主要入口是 `skill/SKILL.md`。没有配置服务端模型时，旧 CLI 的直接生成模式使用规则降级输出，不等同于 AI 整理质量。

模型、下载媒体、Cookie、数据库和笔记产物默认位于项目本地目录，均不提交到仓库。可以通过 `SEAGULL_NOTES_HOME` 改变目录。AI 客户端整理时，字幕会进入该客户端的上下文；是否发送到云端取决于客户端配置。

## 测试

```bash
python -m pip install -e ".[notes,test]"
python -m pytest tests -q
```

测试覆盖字幕缓存、匿名模式不读取 Cookie、只取字幕时不下载视频、时间轴、图文输出和原有管线；不依赖网络、GPU 或生成 API。平台登录、反爬和具体视频的可用性需要实际链接验证。

项目与 CuteNote 无隶属关系；CuteNote 仅为页面呈现参考。
