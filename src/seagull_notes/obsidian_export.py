"""Portable Markdown, real attachments and native editable Canvas for Obsidian."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zipfile import ZIP_DEFLATED, ZipFile

from . import export, notebook_library, sources

ASSETS = Path(__file__).resolve().parents[2] / "skill" / "assets"
INSTRUCTIONS = """---
cssclasses:
  - seagull-notes
---
# Seagull Notes：导入与编辑

将包里的 `Seagull Notes` 文件夹复制到 vault 根目录，保留其目录结构。
将 `.obsidian/snippets/seagull-notes.css` 放到 vault 同名目录，在设置 → 外观 → CSS 代码片段中启用 `seagull-notes`，即可使用米色阅读样式。

## 修改笔记和图片

- 正文是原生 Markdown，切到编辑模式即可修改。
- 删除图片：删除对应的 `![[...]]` 嵌入行；图片附件仍保留，便于恢复。
- 替换图片：把新图放进该篇的 `附件` 文件夹，改嵌入行中的文件名，或在编辑器中拖入新图。
- 移动位置：剪切整条图片嵌入行，粘贴到需要的段落。
- 调整尺寸：`![[图片路径|760]]` 中的 760 是宽度；改成 480 等数值即可。也可用 `|640x480` 指定宽高。
- 图注是图片下方的普通 Markdown，能独立修改。
- SVG 保留原始矢量文件，可使用 SVG 编辑器修改文字、图形与颜色，保存后笔记会显示更新后的附件。
- PNG/JPG 保留原图片，可替换、裁剪或用图像编辑器修改；截图不会自动变成可逐字编辑的矢量图。
- 脑图另存为 Obsidian 原生 `.canvas`，可直接拖动节点、修改文字和连接，不依赖额外插件。

## 排版与内容

保留原笔记全部章节、时间链接、代码围栏、LaTeX、图注和脑图内容。米色样式用于这些笔记的阅读视图与 Live Preview；导航与代码复制使用 Obsidian 自带界面。CSS 不把正文变成 HTML，内容仍可编辑。

`字幕原文.md` 保存原笔记实际提供的完整字幕。重导入时，本工具保留 vault 已有文件，不覆盖你改过的笔记或图片；新版导出包仍会更新。

参考：[Obsidian 导入 Markdown](https://obsidian.md/help/import/markdown)、[图片嵌入与尺寸](https://obsidian.md/help/embeds)、[CSS 片段](https://obsidian.md/help/snippets)。
"""


def _timestamp(seconds: float) -> str:
    hours, rest = divmod(int(seconds), 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes:02}:{seconds:02}"


def canvas_tree(tree: list[dict], title: str = "") -> dict:
    nodes, edges = [], []
    placed, _, _ = export._layout(tree, title)
    for index, item in enumerate(placed):
        identity = f"node-{index}"
        color = "#f5ecdc" if item["depth"] == 0 else export.FILLS[item["branch"] % len(export.FILLS)]
        nodes.append({"id": identity, "type": "text", "text": item["title"],
                      "x": round(item["x"] * 1.4), "y": round(item["y"] * 1.4),
                      "width": round(item["w"] * 1.4), "height": round(item["h"] * 1.4), "color": color})
        if item["parent"] is not None:
            left = item["side"] == -1
            edges.append({"id": f"edge-{len(edges)}", "fromNode": f'node-{item["parent"]}', "toNode": identity,
                          "fromSide": "left" if left else "right", "toSide": "right" if left else "left",
                          "toEnd": "none", "color": export.PALETTE[item["branch"] % len(export.PALETTE)]})
    return {"nodes": nodes, "edges": edges}


def export_bundle(note: dict, source: Path, package: Path) -> dict[str, str]:
    identity = notebook_library.notebook_id(source)
    title = export._safe_name(note["title"], "笔记")
    folder = f"Seagull Notes/{identity}"
    note_name = f"{folder}/{title}.md"
    files = {}
    copied = {}

    def picture(image):
        original = (source.parent / image["path"]).resolve()
        if original not in copied:
            name = f"{folder}/附件/{len(copied)+1:02}-{export._safe_name(original.stem, 'image')}{original.suffix.lower()}"
            files[name] = original.read_bytes()
            copied[original] = name
        caption = image.get("caption", "")
        return f'![[{copied[original]}|760]]' + (f"\n\n*{caption}*" if caption else "")

    body = ["---\ncssclasses:\n  - seagull-notes\n---", f"# {note['title']}"]
    if note.get("subtitle"):
        body.append(note["subtitle"])
    if note.get("source_url"):
        source_line = f"来源：[{note.get('platform', sources.SOURCE_LABELS[sources.source_kind(note)])}]({note['source_url']})"
    elif sources.source_kind(note) in {"topic", "text"}:
        source_line = f"来源：{sources.SOURCE_LABELS[sources.source_kind(note)]}"
    else:
        source_line = f"来源：本地文件 `{Path(note['source_ref']).name}`"
    meta = [source_line, note.get("uploader"), _timestamp(note["duration"]) if note.get("duration") else None,
            note.get("subtitle_origin")]
    body.append(" · ".join(str(value) for value in meta if value))
    if note.get("summary"):
        body.append("> [!abstract] 核心概览\n" + "\n".join("> " + line for line in note["summary"].splitlines()))
    if note.get("takeaways"):
        body.append("> [!tip] 核心收获\n" + "\n".join("> - " + value for value in note["takeaways"]))
    if note.get("cover"):
        body.append(picture(note["cover"]))
    for chapter, section in enumerate(note["sections"], 1):
        heading = f"## {section['title']}"
        if section.get("start") is not None and sources.source_kind(note) in {"video", "local"}:
            label = _timestamp(section["start"])
            if note.get("source_url"):
                parts = urlsplit(note["source_url"])
                query = dict(parse_qsl(parts.query, keep_blank_values=True))
                query["t"] = str(int(section["start"]))
                target = urlunsplit(parts._replace(query=urlencode(query)))
                heading += f" · [{label}]({target})"
            else:
                heading += f" · {label}"
        body.extend([heading, section["markdown"]])
        if section.get("image"):
            body.append(picture(section["image"]))
        for item in note.get("review", []):
            if item.get("chapter") == chapter and item.get("options"):
                body.extend([f'### 自测：{item["question"]}', "\n".join(f'{index}. {option}' for index, option in enumerate(item["options"], 1)), f'正确答案：{item["correct"] + 1}. {item["options"][item["correct"]]}', item["answer"]])
    if note.get("mind_map"):
        canvas = f"{folder}/思维导图.canvas"
        files[canvas] = json.dumps(canvas_tree(note["mind_map"], note["title"]), ensure_ascii=False, indent=2).encode("utf-8")
        body.append(f"## 思维导图\n\n[[{canvas}|打开可编辑思维导图]]\n\n在 Obsidian 中打开此脑图，可修改节点文字、移动或增删节点，以及调整连线。")
    if note.get("transcript"):
        transcript = f"{folder}/字幕原文.md"
        files[transcript] = ("# 字幕与出处\n\n" + note["transcript"]).encode("utf-8")
        body.append(f"## 字幕与出处\n\n[[{transcript}|查看完整字幕与出处]]")
    body.append("[[Seagull Notes/导入与编辑|图片尺寸、移动、替换与样式说明]]")
    if sources.source_links(note):
        body.append("## 参考资料\n\n" + "\n".join(f'- [{item["title"]}]({item["url"]})' for item in sources.source_links(note)))
    for item in note.get("explorers", []):
        body.append(f'## {item["title"]}')
        for step in item.get("steps", []):
            body.extend([f'### {step["title"]}', step["markdown"]])
    for item in note.get("review", []):
        if item.get("chapter") and item.get("options"):
            continue
        body.append(f'### 自测：{item["question"]}')
        if item.get("options"):
            body.append("\n".join(f'{index}. {option}' for index, option in enumerate(item["options"], 1)))
        body.append(item["answer"])
    for item in note.get("extensions", []):
        body.extend([f'## 拓展：{item["title"]}', item["markdown"]])
    files[note_name] = "\n\n".join(body).encode("utf-8")
    files[".obsidian/snippets/seagull-notes.css"] = (ASSETS / "obsidian.css").read_bytes()
    files["Seagull Notes/导入与编辑.md"] = INSTRUCTIONS.encode("utf-8")
    package.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(package, "w", ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return {"obsidian_zip": str(package.resolve()), "obsidian_note": note_name}


def merge_bundles(packages: list[Path], target: Path) -> None:
    seen = set()
    with ZipFile(target, "w", ZIP_DEFLATED) as merged:
        for package in packages:
            with ZipFile(package) as archive:
                for name in archive.namelist():
                    if name not in seen:
                        merged.writestr(name, archive.read(name))
                        seen.add(name)


def import_bundle(package: Path, vault: Path) -> dict:
    vault = vault.resolve()
    if not vault.is_dir():
        raise ValueError("Obsidian vault 路径必须是实际存在的文件夹")
    imported = kept = 0
    notes = []
    with ZipFile(package) as archive:
        for name in archive.namelist():
            relative = PurePosixPath(name)
            destination = (vault / relative).resolve()
            if relative.is_absolute() or not destination.is_relative_to(vault):
                raise ValueError("导入包包含越出 vault 的路径")
            if destination.exists():
                kept += 1
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(archive.read(name))
                imported += 1
            if destination.suffix == ".md" and len(relative.parts) == 3 and relative.parts[0] == "Seagull Notes" and destination.name != "字幕原文.md":
                notes.append(str(destination))
    return {"vault": str(vault), "imported": imported, "kept_existing": kept, "notes": notes}
