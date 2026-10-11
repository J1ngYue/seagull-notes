#!/usr/bin/env python3
"""把 Codex 整理的笔记 JSON 渲染为自包含 HTML 和 Markdown。"""

from __future__ import annotations

import argparse
import base64
import html
import json
import mimetypes
import os
import re
import sys
from pathlib import Path
from string import Template
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import markdown

PROJECT_HOME = Path(os.environ.get("SEAGULL_NOTES_HOME", str(Path(__file__).resolve().parents[2])))
sys.path.insert(0, str(PROJECT_HOME / "src"))

from seagull_notes import config, export


def timestamp(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes:02}:{seconds:02}"


def source_link(source: str, start: float | None = None) -> str:
    parts = urlsplit(source)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("source_url 必须是 http/https 视频链接")
    if start is None:
        return source
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["t"] = str(max(0, int(start)))
    return urlunsplit(parts._replace(query=urlencode(query)))


def image_data(image: dict, base: Path) -> tuple[str, Path]:
    path = (base / image["path"]).resolve()
    mime = mimetypes.guess_type(path.name)[0]
    if mime not in {"image/png", "image/jpeg", "image/webp", "image/svg+xml"}:
        raise ValueError(f"不支持的图片格式：{path}")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}", path


def rich_text(text: str) -> str:
    # 输入正文是 Markdown；原文中的 HTML 作为文本保留。
    escaped = html.escape(text, quote=False).replace("&gt;", ">")
    rendered = markdown.markdown(
        escaped, extensions=["tables", "fenced_code", "sane_lists", "pymdownx.arithmatex"],
        extension_configs={"pymdownx.arithmatex": {"generic": True}},
    )
    from lxml import html as lxml_html

    root = lxml_html.fragment_fromstring(rendered, create_parent="div")
    # Markdown 对代码再次转义；还原输入字符，序列化时仍作为文本输出。
    for code in root.iter("code"):
        code.text = html.unescape(code.text or "")
    for link in root.iter("a"):
        href = link.get("href", "")
        if urlsplit(href).scheme.lower() not in {"", "http", "https"}:
            link.attrib.pop("href", None)
    # 配图来自 sections.image；正文不加载未核实的外部图片。
    for image in list(root.iter("img")):
        image.drop_tag()
    return "".join(lxml_html.tostring(child, encoding="unicode") for child in root)


def math_assets() -> tuple[str, str]:
    """Bundle KaTeX and its WOFF2 fonts so the notebook works offline."""
    assets = Path(__file__).resolve().parents[1] / "assets" / "katex"
    css = (assets / "katex.min.css").read_text(encoding="utf-8")

    def embed_font(match):
        font = re.search(r"url\((fonts/[^)]+\.woff2)\)", match[0])
        if not font:
            raise ValueError("KaTeX font declaration is missing a WOFF2 source")
        encoded = base64.b64encode((assets / font[1]).read_bytes()).decode("ascii")
        return f'src:url(data:font/woff2;base64,{encoded}) format("woff2");'

    css = re.sub(r"src:[^;]+;", embed_font, css)
    script = (assets / "katex.min.js").read_text(encoding="utf-8")
    return f"<style>{css}</style>", f"<script>{script}</script>"


def render_note(note: dict, base: Path) -> tuple[str, str]:
    title = note["title"]
    local_source = None
    if note.get("source_url"):
        source = source_link(note["source_url"])
        source_action = f'<a href="{html.escape(source, quote=True)}" target="_blank" rel="noopener">查看原视频 ↗</a>'
        source_md = f"[{note.get('platform', '原视频')}]({source})"
    else:
        local_source = Path(note["source_ref"])
        if not local_source.is_absolute() or not local_source.is_file():
            raise ValueError("source_ref 必须是实际存在的本地文件绝对路径")
        source = str(local_source)
        source_action = f'<span class="source-local" title="{html.escape(source, quote=True)}">本地素材：{html.escape(local_source.name)}</span>'
        source_md = f"本地文件 `{source}`"
    origin = note.get("subtitle_origin", "字幕来源待核实")
    summary = note.get("summary", "")
    cover = ""
    cover_md = ""
    if note.get("cover"):
        data_url, cover_path = image_data(note["cover"], base)
        caption = note["cover"].get("caption", "")
        diagram_class = ' class="diagram"' if note["cover"].get("kind") == "diagram" or cover_path.suffix.lower() == ".svg" else ""
        cover = f'<figure class="cover"><button type="button" class="figure-image" aria-label="放大查看配图"><img{diagram_class} src="{data_url}" alt="{html.escape(caption, quote=True)}"></button><figcaption>{html.escape(caption)}</figcaption></figure>'
        cover_md = f"![{caption}](<{cover_path.as_posix()}>)"
    takeaways = ""
    if note.get("takeaways"):
        cards = [f'<div class="takeaway"><span>{i:02}</span><p>{html.escape(point)}</p></div>' for i, point in enumerate(note["takeaways"], 1)]
        takeaways = '<div class="takeaways">' + "".join(cards) + '</div>'
    meta = " · ".join(str(value) for value in [
        note.get("platform", "本地文件" if local_source else "视频"), note.get("uploader"),
        timestamp(note["duration"]) if note.get("duration") else None, origin,
    ] if value)
    toc, sections = [], []
    body = [f"# {title}", summary, f"来源：{source_md} · {meta}"]
    if note.get("takeaways"):
        body.append("## 核心收获\n\n" + "\n".join(f"- {point}" for point in note["takeaways"]))
    if cover_md:
        body.append(cover_md)
    for i, section in enumerate(note["sections"], 1):
        name = html.escape(section["title"])
        start = section.get("start")
        time_link = ""
        heading = section["title"]
        if start is not None:
            if local_source:
                time_link = f'<span class="time">{timestamp(start)}</span>'
                heading += f" · {timestamp(start)}"
            else:
                target = source_link(source, start)
                time_link = f'<a class="time" href="{html.escape(target, quote=True)}" target="_blank" rel="noopener">↗ {timestamp(start)}</a>'
                heading += f" [{timestamp(start)}]({target})"
        toc.append(f'<a href="#chapter-{i}"><span>{i:02}</span>{name}</a>')
        figure = ""
        image_md = ""
        if section.get("image"):
            image = section["image"]
            data_url, path = image_data(image, base)
            caption = image.get("caption", "")
            figure = f'<figure><button type="button" class="figure-image" aria-label="放大查看配图"><img src="{data_url}" alt="{html.escape(caption, quote=True)}"></button><figcaption>{html.escape(caption)}</figcaption></figure>'
            image_md = f"![{caption}](<{path.as_posix()}>)"
        sections.append(f'<section class="chapter" id="chapter-{i}"><header><span class="number">{i:02}</span><h2>{name}</h2>{time_link}</header><div class="prose">{rich_text(section["markdown"])}</div>{figure}</section>')
        body.extend([f"## {heading}", section["markdown"], image_md])
    markdown_body = "\n\n".join(value for value in body if value)
    tree = note.get("mind_map")
    mindmap = '<p class="muted">这篇笔记没有提供脑图。</p>'
    if tree:
        svg = export.render_svg(tree, title)
        encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
        mindmap = f'<img class="mindmap" alt="{html.escape(title, quote=True)}思维导图" src="data:image/svg+xml;base64,{encoded}">'
    math_css, math_js = math_assets() if any('class="arithmatex"' in section for section in sections) else ("", "")
    template = Template((Path(__file__).resolve().parents[1] / "assets" / "notebook.html").read_text(encoding="utf-8"))
    page = template.substitute(
        title=html.escape(title), summary=html.escape(summary), meta=html.escape(meta),
        source_action=source_action, toc="".join(toc), sections="".join(sections),
        source_kicker="LOCAL NOTES · 本地精读" if local_source else "VIDEO NOTES · 视频精读",
        source_hint="章节时间对应本地素材的位置。" if local_source else "点击章节时间，回到原视频。",
        cover=cover, takeaways=takeaways, subtitle=html.escape(note.get("subtitle", "")),
        mindmap=mindmap, markdown=html.escape(markdown_body),
        transcript=html.escape(note.get("transcript") or "未提供完整字幕原文。"),
        math_css=math_css, math_js=math_js,
    )
    return page, markdown_body


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="笔记 JSON → 图文 HTML + Markdown")
    parser.add_argument("note", type=Path)
    parser.add_argument("--out", type=Path, help="输出文件基名，不含扩展名")
    args = parser.parse_args()
    try:
        note = json.loads(args.note.read_text(encoding="utf-8-sig"))
        page, body = render_note(note, args.note.resolve().parent)
        out = args.out or config.ARTIFACT_DIR / export._safe_name(note["title"], "note")
        out.parent.mkdir(parents=True, exist_ok=True)
        html_path, md_path = Path(f"{out}.html"), Path(f"{out}.md")
        html_path.write_text(page, encoding="utf-8")
        md_path.write_text(body, encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, "html": str(html_path.resolve()), "markdown": str(md_path.resolve())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
