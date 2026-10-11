# 图文笔记渲染输入

`scripts/notebook.py` 使用当前模型整理后的 UTF-8 JSON，不调用外部生成服务。

```json
{
  "title": "笔记标题",
  "source_url": "https://www.bilibili.com/video/BV.../",
  "platform": "Bilibili",
  "uploader": "实际作者",
  "duration": 600,
  "subtitle_origin": "平台 AI 字幕",
  "summary": "核心观点、适用范围和主要收获。",
  "sections": [
    {
      "title": "章节主题",
      "start": 42,
      "markdown": "解释核心概念，再给出步骤、证据或例子。支持 **加粗**、列表、表格和代码块。",
      "image": {
        "path": "images/chapter-01.png",
        "caption": "00:42 视频画面：实际显示的内容。"
      }
    }
  ],
  "mind_map": [{"title": "核心主题", "children": [{"title": "主要分支"}]}],
  "transcript": "完整字幕原文，含实际取得的时间戳（若有）。"
}
```

必需：`title/sections` 和来源。网络来源使用 `source_url`；本地来源使用 `source_ref`，填实际存在的文件绝对路径，不需要编造视频链接。章节必需：`title/markdown`。其他字段只有实际知道时才填。可加 `subtitle` 一句话说明主题，`takeaways` 用字符串数组列出核心收获，`cover` 与章节 `image` 使用相同结构提供一张主题画面。`start` 单位为秒，缺失则省略，不用 0 代替未知。本地来源的时间显示为位置标记，网络来源的时间可跳转原视频。`image` 可省略；提供时文件必须真实存在，路径相对 JSON 所在目录或绝对路径，支持 PNG/JPEG/WebP/SVG。图注需说明视频时间或“根据字幕绘制的示意图”。

Markdown 正文中的外部图片不会加载；用 `image` 提供已经核实的配图。原文 HTML 作为普通文字展示。HTML 中的配图与脑图嵌入文件，Markdown 中的配图链接指向原本地文件，移动 Markdown 时需一并保留图片。

示意图在 `image/cover` 加 `"kind": "diagram"`，尤其是 PNG 示意图，避免按视频封面比例裁切。SVG 默认完整显示。点击配图可打开大图，按 Esc 或“关闭”返回笔记。数值图的生成方法见 [note-figures.md](note-figures.md)。

代码使用 Markdown 围栏并注明实际语言，如 `bash`、`python`、`java`、`cpp` 或 `html`。渲染后是带语言标签、语法颜色和复制按钮的独立圆角代码框；高亮与样式嵌入 HTML，离线可用。复制只包含原始代码，保留缩进、换行和特殊字符，不包含标签或按钮。未知语言仍按纯文本展示并支持复制。

代码示例要补齐必要步骤，不用省略号代替关键命令。需要先修改文件、处于特定分支或替换示例值时，在代码前明确说明；互斥方案放进不同代码框，避免复制后连续执行。只按实际取得的源码标注原视频代码，自己的具体示例明确标为补充。

正文支持 LaTeX：`$L(\theta)=\frac{\theta^2}{2}$` 为行内公式，`$$\theta_{t+1}=\theta_t-\eta\nabla L(\theta_t)$$` 为独立公式，也支持 `\(...\)` 与 `\[...\]`。JSON 中反斜杠需要转义为 `\\`，例如 `"markdown": "$$\\frac{a}{b}$$"`。代码块和反引号中的内容不作为公式渲染。

点击公式会复制不带定界符的 LaTeX 源码，并提示“已复制 LaTeX 公式”；聚焦后可用 Enter 或空格复制。输出 HTML 嵌入 KaTeX 0.19.0 和 WOFF2 字体，离线也能排版。格式错误会保留源码，不能把未渲染的内容冒充正确公式。

每章保留有用细节；不要把口语转写直接切段。脑图用于关系概览，章节图用于解释具体内容，两者不能互相冒充。没有字幕原文则在页面明确显示缺失，不编造 transcript。

长课程的 `sections[].markdown` 默认是详细学习正文，不是摘要列表。按教学内容分章，用三级标题拆分较长章节。主要演示应包含前提、起始状态、操作、结果与验证；对比实验保留状态差异和参数作用。正文要覆盖所有主要教学主题，不能用一张脑图或命令速查表取代解释。整理后的练习可单独成章，标明为补充；没有对应视频片段时省略 `start`。

`transcript` 填实际取得的字幕全文（可附来源说明与时间戳），不只放“已读取全文”或文件路径。长原文保留在原文标签，正文仍写成经过理解的学习笔记。

渲染命令：

```powershell
& 'D:\software\Anaconda\python.exe' '<skill目录>\scripts\notebook.py' '<note.json的绝对路径>'
```

用 `--out '<产物目录>\标题'` 指定输出基名。默认按标题输出 HTML 和 Markdown，stdout 返回两者的绝对路径。
