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
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import markdown
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexer import bygroups, inherit
from pygments.lexers import get_lexer_by_name
from pygments.lexers.shell import BashLexer
from pygments.lexers.special import TextLexer
from pygments.token import Name, Text
from pygments.util import ClassNotFound

PROJECT_HOME = Path(os.environ.get("SEAGULL_NOTES_HOME", str(Path(__file__).resolve().parents[2])))
sys.path.insert(0, str(PROJECT_HOME / "src"))

from seagull_notes import export, notebook_library, obsidian_export, sources


class NotebookBashLexer(BashLexer):
    tokens = {"root": [
        (r"^([ \t]*)(git|ssh-keygen|ssh)(?=[ \t]|$)", bygroups(Text, Name.Function)),
        (r"--?[\w-]+", Name.Attribute),
        inherit,
    ]}


CODE_FORMATTER = HtmlFormatter(nowrap=True, style="default")


def code_block(source: str, language: str) -> str:
    try:
        lexer = get_lexer_by_name(language or "text", stripnl=False, ensurenl=False)
    except ClassNotFound:
        lexer = TextLexer(stripnl=False, ensurenl=False)
    if isinstance(lexer, BashLexer):
        lexer = NotebookBashLexer(stripnl=False, ensurenl=False)
    label = html.escape(lexer.name, quote=True)
    colored = highlight(source, lexer, CODE_FORMATTER)
    language_icon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m8 6-6 6 6 6m8-12 6 6-6 6M14 4l-4 16"/></svg>'
    copy_icon = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="3" width="12" height="14" rx="3"/><path d="M16 17v3H4V7h4"/></svg>'
    return (f'<div class="code-block"><div class="code-toolbar"><span class="code-language">{language_icon}{label}</span>'
            '<div class="code-actions"><button type="button" class="wrap-code" aria-pressed="false" aria-label="切换代码自动换行">换行</button>'
            f'<button type="button" class="copy-code" aria-label="复制 {label} 代码" title="复制代码">{copy_icon}<span>复制</span></button>'
            f'</div></div><pre class="code-source" tabindex="0" aria-label="{label} 代码"><code>{colored}</code></pre></div>')


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
    for pre in list(root.iter("pre")):
        code = pre.find("code")
        if code is not None:
            language = next((value[9:] for value in code.get("class", "").split() if value.startswith("language-")), "")
            block = lxml_html.fragment_fromstring(code_block(code.text_content(), language))
            block.tail = pre.tail
            pre.getparent().replace(pre, block)
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


def render_widgets(note: dict) -> str:
    widgets = []
    for index, explorer in enumerate(note.get("explorers", [])):
        steps = explorer.get("steps", [])
        if not steps:
            continue
        buttons = ''.join(f'<button type="button" role="tab" id="explore-{index}-tab-{step}" aria-controls="explore-{index}-panel-{step}" aria-selected="{str(step == 0).lower()}" tabindex="{0 if step == 0 else -1}" data-step="{step}"><span>{step + 1:02}</span>{html.escape(item["title"])}</button>' for step, item in enumerate(steps))
        panels = ''.join(f'<div class="explore-panel prose" role="tabpanel" id="explore-{index}-panel-{step}" aria-labelledby="explore-{index}-tab-{step}" {"hidden" if step else ""}>{rich_text(item["markdown"])}</div>' for step, item in enumerate(steps))
        widgets.append(f'<section class="explorer"><header><div><span class="label">EXPLORE · 互动演示</span><h3>{html.escape(explorer["title"])}</h3></div><button type="button" class="explore-play" aria-pressed="false">自动演示</button></header><div class="explore-steps" role="tablist" aria-label="{html.escape(explorer["title"], quote=True)}">{buttons}</div><progress value="1" max="{len(steps)}" aria-label="演示步骤"></progress>{panels}</section>')
    if note.get("review"):
        questions = ''.join(f'<details class="review-card"><summary><span>{index:02}</span>{html.escape(item["question"])}</summary><div class="prose">' + ('<ol class="question-options">' + ''.join('<li>' + html.escape(option) + '</li>' for option in item.get("options", [])) + '</ol>' if item.get("options") else '') + rich_text(item["answer"]) + '</div></details>' for index, item in enumerate(note["review"], 1))
        widgets.append('<section class="review-deck"><span class="label">RECALL · 自测卡片</span><h3>合上答案，你能解释吗？</h3>' + questions + '</section>')
    if note.get("extensions"):
        extras = ''.join(f'<details class="extension-card"><summary>{html.escape(item["title"])}<span>拓展阅读 ＋</span></summary><div class="prose">{rich_text(item["markdown"])}</div></details>' for item in note["extensions"])
        widgets.append('<section class="extension-deck"><span class="label">GO FURTHER · 拓展</span>' + extras + '</section>')
    return '<div class="study-widgets">' + ''.join(widgets) + '</div>' if widgets else ""


def render_note(note: dict, base: Path, library_href: str | None = None, obsidian_href: str | None = None, note_id: str = "") -> tuple[str, str]:
    title = note["title"]
    kind = sources.source_kind(note)
    style = sources.reading_style(note)
    local_source = None
    if note.get("source_url"):
        source = source_link(note["source_url"])
        source_action = f'<a href="{html.escape(source, quote=True)}" target="_blank" rel="noopener">{"查看原视频" if kind == "video" else "查看来源"} ↗</a>'
        source_md = f"[{note.get('platform', sources.SOURCE_LABELS[kind])}]({source})"
    elif kind in {"topic", "text"}:
        source = ""
        source_action = f'<span class="source-local">{sources.SOURCE_LABELS[kind]}</span>'
        source_md = sources.SOURCE_LABELS[kind]
    else:
        local_source = Path(note["source_ref"])
        if not local_source.is_absolute() or not local_source.is_file():
            raise ValueError("source_ref 必须是实际存在的本地文件绝对路径")
        source = str(local_source)
        source_action = f'<span class="source-local" title="{html.escape(source, quote=True)}">本地素材：{html.escape(local_source.name)}</span>'
        source_md = f"本地文件 `{source}`"
    origin = note.get("subtitle_origin") or note.get("source_origin") or ("字幕来源待核实" if kind == "video" else "")
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
        note.get("platform", sources.SOURCE_LABELS[kind]), note.get("uploader"),
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
        if start is not None and kind in {"video", "local"}:
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
    reference_links = sources.source_links(note)
    references = '<div class="source-list">' + ''.join(f'<a href="{html.escape(item["url"], quote=True)}" target="_blank" rel="noopener">{html.escape(item["title"])} ↗</a>' for item in reference_links) + '</div>' if reference_links else ""
    if reference_links:
        body.append("## 参考资料\n\n" + "\n".join(f'- [{item["title"]}]({item["url"]})' for item in reference_links))
    for item in note.get("explorers", []):
        body.append(f'## {item["title"]}')
        for step in item.get("steps", []):
            body.extend([f'### {step["title"]}', step["markdown"]])
    for item in note.get("review", []):
        body.append(f'### 自测：{item["question"]}')
        if item.get("options"):
            body.append("\n".join(f'{index}. {option}' for index, option in enumerate(item["options"], 1)))
        body.append(item["answer"])
    for item in note.get("extensions", []):
        body.extend([f'## 拓展：{item["title"]}', item["markdown"]])
    markdown_body = "\n\n".join(value for value in body if value)
    tree = note.get("mind_map")
    mindmap = '<p class="muted">这篇笔记没有提供脑图。</p>'
    if tree:
        mindmap = export.render_mindmap(tree, title)
    widgets = render_widgets(note)
    math_css, math_js = math_assets() if any('class="arithmatex"' in section for section in [*sections, widgets]) else ("", "")
    code_css = "\n".join(line for line in CODE_FORMATTER.get_style_defs(".code-source").splitlines() if line.startswith(".code-source"))
    template = Template((Path(__file__).resolve().parents[1] / "assets" / "notebook.html").read_text(encoding="utf-8"))
    assets = Path(__file__).resolve().parents[1] / "assets"
    hand_font = base64.b64encode((assets / "handwritten" / "ma-shan-zheng.woff2").read_bytes()).decode("ascii")
    handwriting_assets = ('/* ' + (assets / "handwritten" / "LICENSE-note-skill.txt").read_text(encoding="utf-8") + '\n'
                          + (assets / "handwritten" / "OFL-MaShanZheng.txt").read_text(encoding="utf-8") + ' */\n'
                          + '@font-face{font-family:SeagullHand;src:url(data:font/woff2;base64,' + hand_font + ') format("woff2");font-weight:400;font-style:normal;font-display:swap}')
    theme_art = '\n:root{' + ''.join('--' + name + ':url(data:image/webp;base64,' + base64.b64encode((assets / 'themes' / file).read_bytes()).decode('ascii') + ');' for name, file in [('whale-art', 'whale-girl.webp'), ('whale-explain-art', 'whale-explain.webp'), ('whale-think-art', 'whale-think.webp'), ('whale-celebrate-art', 'whale-celebrate.webp'), ('journal-reference', 'journal-reference.webp'), ('journal-banner', 'journal-banner.webp'), ('journal-flowers', 'journal-flowers.webp'), ('moon-wallpaper', 'moon-wallpaper.webp'), ('pixel-wallpaper', 'pixel-wallpaper.webp')]) + '}'
    for item in note.get("review", []):
        options = item.get("options", [])
        if options and (not isinstance(options, list) or len(options) < 2 or not all(isinstance(option, str) for option in options)):
            raise ValueError("选择题的 options 必须是至少两个文字选项的数组")
        if options and (not isinstance(item.get("correct"), int) or isinstance(item["correct"], bool) or not 0 <= item["correct"] < len(options)):
            raise ValueError("选择题的 correct 必须是 options 中正确选项的从 0 开始的索引")
    route = ''.join(f'<button type="button" class="route-card" data-chapter="{index}"><span>{index + 1:02}</span><strong>{html.escape(section["title"])}</strong><small>展开学习 ↗</small></button>' for index, section in enumerate(note["sections"]))
    shelf_entries = []
    shelf_manifest = notebook_library.directory() / "notebooks.json"
    if library_href and shelf_manifest.exists():
        for entry_id, entry in json.loads(shelf_manifest.read_text(encoding="utf-8")).items():
            if entry_id == note_id:
                continue
            parent = library_href.rsplit("/", 1)[0] + "/" if "/" in library_href else ""
            shelf_cover = notebook_library.directory() / entry.get("cover", "")
            cover_data = ("data:" + (mimetypes.guess_type(shelf_cover)[0] or "image/png") + ";base64," + base64.b64encode(shelf_cover.read_bytes()).decode("ascii")) if shelf_cover.is_file() else ""
            shelf_entries.append({"title": entry["title"], "summary": entry["summary"], "chapters": entry["chapters"],
                                  "platform": entry["platform"], "tags": entry.get("tags", []), "href": parent + entry["html"],
                                  "cover": cover_data, "current": False})
    shelf_entries.insert(0, {"title": title, "summary": summary, "chapters": len(note["sections"]),
                             "platform": note.get("platform") or sources.SOURCE_LABELS[kind], "tags": note.get("tags", []),
                             "cover": "", "current": True, "href": "#"})
    shelf_data = json.dumps({"entries": shelf_entries}, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    page = template.substitute(
        title=html.escape(title), summary=html.escape(summary), meta=html.escape(meta),
        source_action=source_action, toc="".join(toc), sections="".join(sections), chapter_count=len(note["sections"]),
        source_kicker={"local": "LOCAL NOTES · 本地精读", "video": "VIDEO NOTES · 视频精读", "topic": "TOPIC NOTES · 主题知识", "text": "TEXT NOTES · 文本整理", "article": "SOURCE NOTES · 网页精读"}[kind],
        source_hint="点击章节时间，回到原视频。" if kind == "video" else "章节时间对应本地素材的位置。" if kind == "local" else "通过目录定位知识点，参考资料保留出处。",
        cover=cover, takeaways=takeaways, subtitle=html.escape(note.get("subtitle", "")),
        mindmap=mindmap, markdown=html.escape(markdown_body),
        transcript=html.escape(note.get("transcript") or note.get("source_text") or ("未提供完整字幕原文。" if kind == "video" else "本笔记依据整理需求与所列资料编写。")),
        original_tab="字幕与出处" if kind == "video" else "资料与出处", references=references,
        style=style, note_id=html.escape(note_id or title, quote=True),
        experience_css=(assets / "experiences.css").read_text(encoding="utf-8") + "\n" + (assets / "themes.css").read_text(encoding="utf-8") + "\n" + (assets / "themes" / "studios.css").read_text(encoding="utf-8")
        + "\n" + (assets / "themes" / "scrapbook-desktop.css").read_text(encoding="utf-8") + theme_art,
        handwriting_assets=handwriting_assets,
        experience_js=(assets / "book-pagination.js").read_text(encoding="utf-8") + "\n" + (assets / "theme-scenes.js").read_text(encoding="utf-8") + "\n" + (assets / "studios.js").read_text(encoding="utf-8") + "\n" + (assets / "experiences.js").read_text(encoding="utf-8"),
        route=route, widgets=widgets,
        reader_templates="\n".join((assets / "themes" / (mode + ".html")).read_text(encoding="utf-8") for mode in ("whale", "journal", "moonlight", "pixel")),
        shelf_data=shelf_data,
        math_css=math_css, math_js=math_js, code_css=code_css,
        library_action=f'<a class="library-link" href="{html.escape(library_href, quote=True)}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 7h7l2-3h9v16H3V7z"/></svg>笔记夹</a>' if library_href else "",
        obsidian_action=f'<a class="obsidian-link" href="{html.escape(obsidian_href, quote=True)}" download>导入 Obsidian ↓</a>' if obsidian_href else "",
    )
    return page, markdown_body


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="笔记 JSON → 图文 HTML + Markdown")
    parser.add_argument("note", type=Path)
    parser.add_argument("--out", type=Path, help="输出文件基名，不含扩展名")
    parser.add_argument("--style", choices=list(sources.STYLE_LABELS), help=" / ".join(sources.STYLE_LABELS.values()))
    parser.add_argument("--obsidian-vault", type=Path, help="将可编辑笔记与图片导入指定 vault，保留已存在的文件")
    args = parser.parse_args()
    try:
        note = json.loads(args.note.read_text(encoding="utf-8-sig"))
        if args.style:
            note["style"] = args.style
        source = args.note.resolve()
        folder = notebook_library.directory().resolve()
        identity = notebook_library.notebook_id(source)
        bundle = obsidian_export.export_bundle(note, source, folder / (identity + ".obsidian.zip"))
        out = args.out or folder / notebook_library.notebook_id(source)
        out.parent.mkdir(parents=True, exist_ok=True)
        html_path, md_path = Path(f"{out}.html"), Path(f"{out}.md")
        try:
            library_href = quote(os.path.relpath(folder / "index.html", html_path.resolve().parent).replace(os.sep, "/"), safe="/")
        except ValueError:
            library_href = (folder / "index.html").as_uri()
        obsidian_href = library_href.rsplit("/", 1)[0] + "/" + identity + ".obsidian.zip" if "/" in library_href else identity + ".obsidian.zip"
        page, body = render_note(note, source.parent, library_href, obsidian_href, identity)
        html_path.write_text(page, encoding="utf-8")
        md_path.write_text(body, encoding="utf-8")
        canonical = folder / (notebook_library.notebook_id(source) + ".html")
        canonical_page = page if html_path.resolve() == canonical else render_note(note, source.parent, "index.html", identity + ".obsidian.zip", identity)[0]
        collected = notebook_library.register(note, source, canonical_page, body, Path(__file__).resolve().parents[1] / "assets" / "library.html", bundle)
        if args.obsidian_vault:
            collected["obsidian_import"] = obsidian_export.import_bundle(Path(bundle["obsidian_zip"]), args.obsidian_vault)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, "html": str(html_path.resolve()), "markdown": str(md_path.resolve()), **bundle, **collected}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
