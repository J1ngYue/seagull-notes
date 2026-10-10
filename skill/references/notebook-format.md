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

必需：`title/source_url/sections`；章节必需：`title/markdown`。其他字段只有实际知道时才填。可加 `subtitle` 一句话说明主题，`takeaways` 用字符串数组列出核心收获，`cover` 与章节 `image` 使用相同结构提供一张主题画面。`start` 单位为秒，缺失则省略，不用 0 代替未知。`image` 可省略；提供时文件必须真实存在，路径相对 JSON 所在目录或绝对路径，支持 PNG/JPEG/WebP/SVG。图注需说明视频时间或“根据字幕绘制的示意图”。

Markdown 正文中的外部图片不会加载；用 `image` 提供已经核实的配图。原文 HTML 作为普通文字展示。HTML 中的配图与脑图嵌入文件，Markdown 中的配图链接指向原本地文件，移动 Markdown 时需一并保留图片。

每章保留有用细节；不要把口语转写直接切段。脑图用于关系概览，章节图用于解释具体内容，两者不能互相冒充。没有字幕原文则在页面明确显示缺失，不编造 transcript。

渲染命令：

```powershell
& 'D:\software\Anaconda\python.exe' '<skill目录>\scripts\notebook.py' '<note.json的绝对路径>'
```

用 `--out '<产物目录>\标题'` 指定输出基名。默认按标题输出 HTML 和 Markdown，stdout 返回两者的绝对路径。
