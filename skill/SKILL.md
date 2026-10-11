---
name: seagull-notes
description: Turn Bilibili, YouTube and other video links into illustrated Chinese notes with timestamps, mind maps, Markdown and a local HTML page. Prefer platform captions including AI captions; let the user sign in through the in-app browser when needed, then continue reading accessible captions. Use for video note requests and follow-ups to existing video notes.
---

# Seagull Notes

用户发视频链接，你取得完整平台字幕、理解内容、选择有信息量的配图，交付可直接阅读的图文笔记。笔记由当前 Codex 模型整理，无需另配生成 API key。

脚本路径相对于此 skill 目录；请从当前 `SKILL.md` 的真实路径确定目录，不猜用户路径。项目源码位于仓库的 `src/`，产物默认位于项目的 `data/artifacts/`。项目根可由 `SEAGULL_NOTES_HOME` 指定；仅复制 skill 时需先在当前 Python 安装项目包。

## 1. 取得完整字幕

解析分享文本里的真实视频链接，保留分 P 和用户指定的范围。不要把封面、简介、评论或平台 AI 总结当作完整字幕。

Windows 直接使用 `D:\software\Anaconda\python.exe`，不调用 `.cmd/.bat` 包装器，也不自动换成其他解释器：

```powershell
& 'D:\software\Anaconda\python.exe' '<skill目录>\scripts\fetch.py' '<视频链接>' --anonymous
```

用户没有现成登录状态时可先用 `--anonymous` 尝试免登录获取，不读取已存 Cookie 或浏览器登录态。用户说此前已登录、或同一会话已有有效登录态时，先复用现有页面和已授权的本地凭证，能取得字幕就直接继续；不要因匿名请求失败重新弹出选择，也不要强制用户再次登录。当前状态实际失效时才说明具体限制。默认只取平台字幕，不下载视频、不运行 ASR。成功 JSON 中 `content` 是全文，`segments` 中的 `start/end/text` 是秒数时间轴；`origin` 标明来源，`source_ref` 是原链接。平台字幕也可能是机器生成的，仍要检查专有名词和数字，不宣称其必然准确。

B站用户已启用本地采集器时，优先运行 `fetch.py '<BV视频链接>' --local-browser`，不再让用户打开开发者工具、复制响应或手动导入字幕。它使用专用的本地 Chrome 配置；与 Codex 内置浏览器的会话分开。先验证现有登录，已登录的窗口不弹提示；确需登录时仅交接一次，脚本会自动检测成功并继续。`caption_file` 与 `subtitle_file` 是自动保存的全文 JSON/SRT，返回的 `content/segments` 可直接写笔记。按 `coverage` 核对首末时间和明显缺段，不能只凭文件存在宣称完整。安装和限制见 [本地采集器](references/browser-subtitles.md#本地-b站采集器)。

用户提供本地字幕文件时直接解析；本地音视频在用户允许 ASR 后使用同一脚本并加 `--allow-asr`，读取实际返回的时间轴。生成笔记 JSON 时使用 `source_ref` 保存本地文件绝对路径，不为本地素材编造网页地址。模型已完整缓存时直接离线加载。

超过 30000 字可加 `--offset 0 --max-chars 30000` 分段读取。`has_more: true` 时继续按 `next_offset` 读到结尾，再写笔记。分页针对正文；时间轴保持完整。

匿名字幕取不到而用户明确要求免登录完成、并允许语音识别时，可用 `--anonymous --allow-asr` 尝试下载公开音频再转写。这不使用平台 AI 字幕，必须标为本地 ASR；音频也可能受访问限制。依赖与模型未准备好时先说明下载体积和耗时，不自动下载模型。

遇到 `browser_required`、412、机器人检查、登录提示或空字幕列表，读 [浏览器字幕流程](references/browser-subtitles.md)，先在目标视频的内置浏览器页面检查公开字幕。需要在登录和 ASR 之间选择时，用下表说明两条路径，再让用户选择；用户已明确选定路径则继续，不重复问。

| 选择 | 好处 | 代价与限制 |
|---|---|---|
| 浏览器登录后读平台字幕 | 有字幕时通常更快；保留原平台的措辞和可取得的时间轴，无需下载 ASR 模型 | 用户需要完成登录或验证；平台字幕也可能有误，登录后仍可能受风控或无法导出 |
| 免登录尝试音频转写 | 公开音频可下载时，不用登录视频平台；没有字幕也可尝试 | 需下载音频；本机没有 ASR 模型时必须先下载（默认 large-v3 约 3 GB），首次会多出下载、磁盘占用与加载耗时；识别长视频通常更慢，术语、数字可能识别错误，音频也可能被限制 |

不要把“登录”或“无字幕”写成已确定事实：广告、未加载完的播放器也可能让字幕接口暂时返回空。选择登录时展示该平台的原视频页面，由用户完成登录或验证；保留标签等其回复。之后从同一浏览器继续取可访问字幕，不要求用户导出 Cookie，也不假定登录态已传给 Python。用户明确拒绝登录时不强行引导登录。

提出选择 2 前，用当前解释器检查 ASR 依赖，并用 `asr.model_is_cached()` 检查完整模型快照。在选项文字中明确区分“已有模型，可直接识别”和“没有模型，需先下载约 X GB”；不要等用户选完后才透露模型下载。未获准下载时不启动模型准备。

YouTube 优先尝试浏览器提供的 `tab.content.exportYouTubeTranscript()`，实际成功后再读返回的 UTF-8 文件。B站及其他平台读取网页真实提供的字幕列表或下载入口。工具未暴露的能力不可编造。登录后仍无完整字幕时，说明具体障碍；有 CC 单句字幕不代表已取得全文。

用户明确允许语音识别后才加 `--allow-asr`。无字幕时不得默默转 ASR，也不得只看简介就生成整篇笔记。已有本地 Cookie 文件可沿用；旧 Cookie 参数兼容本地脚本方案，但不要求用户重新导出。

## 2. 写笔记并配图

读完素材再整理中文笔记：开头概括核心观点，按内容分章，保留关键数字、术语、步骤、论据及局限；删除口语重复和广告，区别视频观点与自己的解释。

章节 `start` 从实际时间轴选择，不猜时间。图文并茂的图要解释内容：优先原视频的课件、图表、流程、产品界面和关键演示画面。通过当前可用的浏览器/媒体工具定位、核实，再保存；保留画面时间和图注。字幕文本不包含画面证据，不能仅凭字幕声称看过视频画面。

若无法取得有用的真实画面，可以绘制基于已核实字幕的流程图、对比图或脑图，并标注“根据字幕绘制的示意图”。不要把自绘图标成视频截图；封面仅作封面，不当作整篇笔记唯一配图。短内容按信息量配图，不为凑数量添装饰。

需要生成解释图时读 [笔记配图规范](references/note-figures.md)。数值曲线先根据真实数据或明确标注的公式示例计算坐标，再使用 `scripts/plot.py` 输出 SVG/PNG；不要凭视觉手写曲线、点和箭头的位置。示意图的 `image/cover.kind` 设为 `diagram`，保证完整显示；手机上可点击配图查看大图。

阅读 [图文笔记格式](references/notebook-format.md)，将整理结果保存为 `note.json`。这是渲染输入，不是字幕转写的替代品。

数学公式用 LaTeX：行内 `$...$`、独立公式 `$$...$$`，不要放在代码反引号中。渲染后单击公式复制原始 LaTeX，Markdown 保留源码。Git 命令等程序代码仍使用代码格式，不为了展示数学功能给没有公式的视频添加无关公式。

## 3. 渲染并检查

```powershell
& 'D:\software\Anaconda\python.exe' '<skill目录>\scripts\notebook.py' '<note.json的绝对路径>'
```

输出自包含 `.html` 与 `.md`。HTML 参考 [CuteNote](https://cutenote.cc/) 的暖白页面、摘要卡片、章节层次和图文／脑图／Markdown／原文切换；图片嵌入文件，离线可读。可从打印按钮保存 PDF。只需独立脑图时仍可直接调用 `scripts/render.py`。

打开结果检查：中文、图片、章节时间跳转、各个标签、手机窄屏和打印布局。检查全文是否覆盖到视频结尾，缺失时间轴或画面时如实标明。

## 4. 交付

在 Codex 面板展示 HTML（`open_in_codex` 或内置浏览器），给用户可点击的 HTML 和 Markdown 绝对路径；简要说明字幕来源、配图来源与实际缺失。无需把完整笔记重复贴满聊天。

没有具体视频时只能交付明确标注的 UI 示例，不宣称真实平台登录和字幕提取已验证。

依赖见 [setup.md](references/setup.md)；错误排查见 [troubleshooting.md](references/troubleshooting.md)。
