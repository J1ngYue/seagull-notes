# 图文笔记渲染输入

`scripts/notebook.py` 使用当前模型整理后的 UTF-8 JSON，不调用外部生成服务。

默认阅读配色为暖白、米色和暖棕：代码框、公式框、重点卡片与脑图节点统一使用米色底，不使用偏绿背景；Obsidian CSS 和 Canvas 同步采用该配色。代码语法颜色保留，视频截图与原始配图的内容不随界面换色。

主题、粘贴文本和网页也使用同一个渲染器：`source_kind` 设为 `topic/text/article`，主题或文字可用 `source_text/source_origin`，无需伪造视频或文件地址；网页填写真实 `source_url`。`sources` 保存 `title/url` 资料数组，`style` 为 `paper/atlas/folio`，`tags` 用于笔记夹搜索。互动步骤、自测与拓展字段见 [materials-and-styles.md](materials-and-styles.md)。非视频来源不添加虚构时间戳。

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

必需：`title/sections` 和来源类型。视频、网页使用 `source_url`；本地来源使用 `source_ref`，填实际存在的文件绝对路径；主题和粘贴文本明确填写 `source_kind/source_text/source_origin`，不需要编造链接。章节必需：`title/markdown`。其他字段只有实际知道时才填。可加 `subtitle` 一句话说明主题，`takeaways` 用字符串数组列出核心收获，`cover` 与章节 `image` 使用相同结构提供一张主题画面。`start` 单位为秒，仅用于视频或本地时间轴，缺失则省略，不用 0 代替未知。本地来源的时间显示为位置标记，视频来源的时间可跳转原视频。`image` 可省略；提供时文件必须真实存在，路径相对 JSON 所在目录或绝对路径，支持 PNG/JPEG/WebP/SVG。图注需说明真实出处、视频时间或自绘示意图的依据。

Markdown 正文中的外部图片不会加载；用 `image` 提供已经核实的配图。原文 HTML 作为普通文字展示。HTML 中的配图与脑图嵌入文件，Markdown 中的配图链接指向原本地文件，移动 Markdown 时需一并保留图片。

示意图在 `image/cover` 加 `"kind": "diagram"`，尤其是 PNG 示意图，避免按视频封面比例裁切。SVG 默认完整显示。点击配图可打开大图，按 Esc 或“关闭”返回笔记。数值图的生成方法见 [note-figures.md](note-figures.md)。

代码使用 Markdown 围栏并注明实际语言，如 `bash`、`python`、`java`、`cpp` 或 `html`。渲染后是带语言标签、语法颜色和复制按钮的独立淡色圆角代码框；高亮与样式嵌入 HTML，离线可用。复制只包含原始代码，保留缩进、换行和特殊字符，不包含标签或按钮。未知语言仍按纯文本展示并支持复制。

代码示例要补齐必要步骤，不用省略号代替关键命令。需要先修改文件、处于特定分支或替换示例值时，在代码前明确说明；互斥方案放进不同代码框，避免复制后连续执行。只按实际取得的源码标注原视频代码，自己的具体示例明确标为补充。

阅读目录支持搜索，随滚动定位当前章节；手机上通过“章节目录”展开。底部显示章节位置并提供上一章、下一章与返回顶部。代码框的“换行”只改变显示方式，不改变复制内容；复制成功会在按钮上反馈。

Markdown 标签显示完整源码，可复制全部或下载 `.md`，保留代码、公式和图片引用；首次切换从顶部显示，返回正文恢复阅读位置。脑图和源码视图不叠加原书页的装饰；纸本风格的脑图装订条随画布容器定位，展开时保持在画布左侧，收起或按 Esc 后恢复。

正文支持 LaTeX：`$L(\theta)=\frac{\theta^2}{2}$` 为行内公式，`$$\theta_{t+1}=\theta_t-\eta\nabla L(\theta_t)$$` 为独立公式，也支持 `\(...\)` 与 `\[...\]`。JSON 中反斜杠需要转义为 `\\`，例如 `"markdown": "$$\\frac{a}{b}$$"`。代码块和反引号中的内容不作为公式渲染。

点击公式会复制不带定界符的 LaTeX 源码，并提示“已复制 LaTeX 公式”；聚焦后可用 Enter 或空格复制。输出 HTML 嵌入 KaTeX 0.19.0 和 WOFF2 字体，离线也能排版。格式错误会保留源码，不能把未渲染的内容冒充正确公式。

每章保留有用细节；不要把口语转写直接切段。脑图用于关系概览，章节图用于解释具体内容，两者不能互相冒充。没有字幕原文则在页面明确显示缺失，不编造 transcript。

长课程的 `sections[].markdown` 默认是详细学习正文，不是摘要列表。按教学内容分章，用三级标题拆分较长章节。主要演示应包含前提、起始状态、操作、结果与验证；对比实验保留状态差异和参数作用。正文要覆盖所有主要教学主题，不能用一张脑图或命令速查表取代解释。整理后的练习可单独成章，标明为补充；没有对应视频片段时省略 `start`。

短视频也按全部重要内容写，不因时长短而只留提纲。整理时在笔记输入旁保存 `coverage.md`，按实际时间记录每个重要知识点、例子、推导或结尾补充与对应正文章节；交付前逐项查漏。原文标签、摘要和脑图的提及不能替代正文解释。仅画面可见而未取得的信息标明缺失；口语重复与广告可以删去，不用完整转写冒充理解后的笔记。

`transcript` 填实际取得的字幕全文（可附来源说明与时间戳），不只放“已读取全文”或文件路径。长原文保留在原文标签，正文仍写成经过理解的学习笔记。

`mind_map` 保留全部重要主题关系；多项顶级主题会自动加课程中心节点，单根树保留原根。渲染器按分支信息量平衡左右两侧，主题卡片使用淡色配色，长中文或英文标签换行。网页版支持普通滚轮围绕指针缩放，并提供按钮缩放、拖动、适应画布和展开操作；独立脑图与笔记标签使用同一模板，Obsidian Canvas 共享节点布局，节点文字、位置、增删和连线均可编辑。用户已修改的 Canvas 不应被重新生成的版本覆盖。

渲染命令：

```powershell
& 'D:\software\Anaconda\python.exe' '<skill目录>\scripts\notebook.py' '<note.json的绝对路径>'
```

用 `--out '<产物目录>\标题'` 指定输出基名。默认输出到 `data/artifacts/notebooks/` 笔记夹，用稳定文件标识避免同名覆盖；页面显示实际标题。stdout 返回 `html/markdown/library/library_note` 的绝对路径。笔记夹的 `index.html` 会自动更新，每篇顶部可返回列表。同一输入 JSON 重新渲染会更新原条目；指定 `--out` 时也会自动收录，不移走原输出。

同时返回 `obsidian_zip`（可导入 ZIP 的绝对路径）与 `obsidian_note`（包内主 Markdown 路径）。包内 `Seagull Notes/<稳定标识>/` 保存正文、`附件/`、字幕原文与 `.canvas` 脑图；图片引用为 `![[Seagull Notes/.../附件/图片.svg|760]]`，760 可修改为显示宽度。没有原机器路径或 data URI 作为图片依赖。SVG 不转成位图，脑图 Canvas 的文字、节点与连线可以在 Obsidian 编辑。

`.obsidian/snippets/seagull-notes.css` 使用 `cssclasses: [seagull-notes]` 限定样式，仅影响对应笔记。用户首次在外观设置启用片段。代码围栏与公式保持原生 Markdown，使用 Obsidian 的编辑与代码复制；网页格式切换不会被当作可编辑 Markdown 交互搬过去。

直接导入：`notebook.py '<note.json>' --obsidian-vault '<实际vault绝对路径>'`；会复制附件并返回 `obsidian_import` 结果，不覆盖已经存在的文件。仅生成 ZIP 时不修改任何 vault。全部导出包为笔记夹中的 `Seagull-Notes-Obsidian.zip`。
