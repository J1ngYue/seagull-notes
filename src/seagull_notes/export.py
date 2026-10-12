"""导出：Markdown / 脑图 SVG / 脑图 PNG / 源文本。

PNG 需要 playwright（可选依赖）。没装的话自动退回 SVG + HTML，
用户在浏览器里打开一样能看能截图。
"""

from __future__ import annotations

import base64
import html
import json
import re
import unicodedata
from pathlib import Path
from string import Template
from typing import Any

from . import config, storage

# ---------------------------------------------------------------- 树布局

NODE_H = 44
NODE_GAP_Y = 12
LEVEL_GAP_X = 52
PADDING = 36


def _text_units(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(char) in "FW" else 1 for char in text)


def _wrap_label(text: str, limit: int) -> list[str]:
    lines, line = [], ""
    for token in re.findall(r'[A-Za-z0-9_.:/-]+|[^A-Za-z0-9_.:/-]', text):
        fragments = list(token) if _text_units(token) > limit else [token]
        for fragment in fragments:
            if fragment == "\n" or (line and _text_units(line + fragment) > limit):
                lines.append(line.strip())
                line = ""
            if fragment != "\n":
                line += fragment
    return lines + [line.strip()] if line.strip() else lines or [""]


def _layout(nodes: list[dict[str, Any]], title: str = "") -> tuple[list[dict[str, Any]], float, float]:
    """中心主题与均衡两侧分支；x/y 是节点左上角，尺寸包含完整文字。"""
    root = nodes[0] if len(nodes) == 1 else {"title": title or "知识总览", "children": nodes}
    placed: list[dict[str, Any]] = []
    children: dict[int, list[int]] = {}

    def index(node, depth=0, parent=None, branch=0):
        identity = len(placed)
        font = 24 if depth == 0 else 19 if depth == 1 else 18
        lines = _wrap_label(node["title"], 24 if depth == 0 else 28)
        width = max(210 if depth == 0 else 154, max(map(_text_units, lines)) * font * .54 + 38)
        height = max(NODE_H, len(lines) * 23 + (42 if depth == 0 else 22))
        placed.append({"title": node["title"], "depth": depth, "parent": parent, "branch": branch,
                       "w": width, "h": height, "font": font, "lines": lines})
        children[identity] = [index(child, depth + 1, identity, i if depth == 0 else branch)
                              for i, child in enumerate(node.get("children") or [])]
        return identity

    index(root)
    spans = {}

    def span(identity):
        kids = children[identity]
        spans[identity] = max(placed[identity]["h"], sum(span(child) for child in kids)
                              + NODE_GAP_Y * max(0, len(kids) - 1))
        return spans[identity]

    span(0)
    columns = {}
    for node in placed:
        columns[node["depth"]] = max(columns.get(node["depth"], 0), node["w"])
    sides, heights = {1: [], -1: []}, {1: 0, -1: 0}
    for child in children[0]:
        side = 1 if heights[1] <= heights[-1] else -1
        sides[side].append(child)
        heights[side] += spans[child] + 32
    heights = {side: max(0, value - 32) for side, value in heights.items()}
    height = max(placed[0]["h"], *heights.values())
    placed[0].update(x=0, y=(height - placed[0]["h"]) / 2, side=0)

    def place(identity, top, side):
        node = placed[identity]
        depth = node["depth"]
        x = columns[0] + LEVEL_GAP_X * depth + sum(columns[level] for level in range(1, depth)) if side == 1 else -LEVEL_GAP_X * depth - sum(columns[level] for level in range(1, depth)) - node["w"]
        node.update(x=x, y=top + (spans[identity] - node["h"]) / 2, side=side)
        kids = children[identity]
        child_height = sum(spans[child] for child in kids) + NODE_GAP_Y * max(0, len(kids) - 1)
        cursor = top + (spans[identity] - child_height) / 2
        for child in kids:
            place(child, cursor, side)
            cursor += spans[child] + NODE_GAP_Y

    for side, items in sides.items():
        cursor = (height - heights[side]) / 2
        for child in items:
            place(child, cursor, side)
            cursor += spans[child] + 32
    left = min(node["x"] for node in placed)
    width = max(node["x"] + node["w"] for node in placed) - left
    for node in placed:
        node["x"] -= left
    return placed, width, height - NODE_H


# ---------------------------------------------------------------- SVG 渲染

PALETTE = ["#aa8662", "#b17e60", "#9c8b71", "#a58b80", "#a38e5d", "#947960"]
FILLS = ["#f7eddb", "#f8eee3", "#f5efe3", "#f6eee7", "#f8f0db", "#f2e9dc"]
BG = "#fffefa"
TEXT = "#3b332a"


def render_svg(nodes: list[dict[str, Any]], title: str = "") -> str:
    """脑图 → SVG 字符串。纯手工布局，不依赖外部渲染库。"""
    if not nodes:
        nodes = [{"title": title or "空脑图"}]

    placed, width, max_y = _layout(nodes, title)
    total_w = width + PADDING * 2
    total_h = max_y + NODE_H + PADDING * 2

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_w:.0f}" height="{total_h:.0f}" '
        f'viewBox="0 0 {total_w:.0f} {total_h:.0f}" role="img">',
        f'<title>{html.escape(title or placed[0]["title"])}</title>',
        '<defs><filter id="card-shadow" x="-15%" y="-30%" width="130%" height="160%"><feDropShadow dx="0" dy="3" stdDeviation="4" flood-color="#725a3f" flood-opacity=".045"/></filter><pattern id="paper-dots" width="20" height="20" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r=".65" fill="#ad9577" opacity=".13"/></pattern></defs>',
        f'<rect width="100%" height="100%" fill="{BG}"/>',
        '<rect width="100%" height="100%" fill="url(#paper-dots)"/>',
        '<g font-family="Microsoft YaHei,PingFang SC,system-ui,sans-serif">',
    ]

    # 边：三次贝塞尔
    for child in placed[1:]:
        parent = placed[child["parent"]]
        side = child["side"]
        x1 = parent["x"] + (parent["w"] if side == 1 else 0) + PADDING
        x2 = child["x"] + (0 if side == 1 else child["w"]) + PADDING
        y1, y2 = parent["y"] + parent["h"] / 2 + PADDING, child["y"] + child["h"] / 2 + PADDING
        mid = (x1 + x2) / 2
        color = PALETTE[child["branch"] % len(PALETTE)]
        parts.append(
            f'<path d="M {x1:.1f} {y1:.1f} C {mid:.1f} {y1:.1f}, {mid:.1f} {y2:.1f}, '
            f'{x2:.1f} {y2:.1f}" fill="none" stroke="{color}" stroke-width="{2.2 if child["depth"] == 1 else 1.6}" opacity=".62"/>'
        )

    # 节点
    for node in placed:
        x, y, depth = node["x"] + PADDING, node["y"] + PADDING, node["depth"]
        color, fill = PALETTE[node["branch"] % len(PALETTE)], FILLS[node["branch"] % len(FILLS)]
        parts.append(f'<g class="map-node" data-depth="{depth}"><title>{html.escape(node["title"])}</title>')
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{node["w"]:.1f}" height="{node["h"]:.1f}" rx="{16 if depth == 0 else 10}" fill="{"#eee0c8" if depth == 0 else fill if depth == 1 else "#fffefa"}" stroke="{"#cfb796" if depth == 0 else color}" stroke-opacity=".45" filter="url(#card-shadow)"/>')
        if depth == 0:
            parts.append(f'<text x="{x + node["w"] / 2:.1f}" y="{y + 23:.1f}" text-anchor="middle" font-size="8" letter-spacing="2.3" fill="#8d7356">KNOWLEDGE MAP</text>')
        else:
            parts.append(f'<circle cx="{x + 14:.1f}" cy="{y + node["h"] / 2:.1f}" r="{3 if depth == 1 else 2}" fill="{color}" opacity=".8"/>')
        text_y = y + (node["h"] - len(node["lines"]) * 23) / 2 + 17 + (7 if depth == 0 else 0)
        parts.append(f'<text x="{x + node["w"] / 2 + (0 if depth == 0 else 4):.1f}" y="{text_y:.1f}" text-anchor="middle" font-size="{node["font"]}" font-weight="{600 if depth <= 1 else 400}" fill="{TEXT}">')
        for index, line in enumerate(node["lines"]):
            parts.append(f'<tspan x="{x + node["w"] / 2 + (0 if depth == 0 else 4):.1f}" dy="{0 if index == 0 else 23}">{html.escape(line)}</tspan>')
        parts.append('</text></g>')

    parts.append("</g></svg>")
    return "\n".join(parts)


def render_mindmap(nodes: list[dict[str, Any]], title: str) -> str:
    """Shared offline viewer for notebooks and standalone mind maps."""
    svg = render_svg(nodes, title)
    import xml.etree.ElementTree as ET
    document = ET.fromstring(svg)
    template = Path(__file__).resolve().parents[2] / "skill" / "assets" / "mindmap.html"
    return Template(template.read_text(encoding="utf-8")).substitute(
        image="data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii"),
        title=html.escape(title, quote=True), width=document.get("width"), height=document.get("height"),
        node_count=len(document.findall('.//{http://www.w3.org/2000/svg}g[@class="map-node"]')),
    )


def render_html(nodes: list[dict[str, Any]], title: str) -> str:
    """把 SVG 包成独立 HTML，浏览器直接打开。"""
    viewer = render_mindmap(nodes, title)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{html.escape(title)} - 脑图</title>
<style>
  body {{ margin: 0; padding: 32px; background: #f5f3ed;
         font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif; }}
  h1 {{ font-size: 22px; color: #3b332a; margin: 0 0 24px; }}
  .canvas {{ background: #fff; border-radius: 16px; padding: 24px;
             box-shadow: 0 4px 24px rgba(0,0,0,0.06); overflow: auto; }}
  @media(max-width:650px) {{ body {{ padding:16px; }} .canvas {{ padding:0; }} h1 {{ font-size:19px; }} }}
  @media print {{ body {{ background: #fff; padding: 0; }} .canvas {{ box-shadow: none; }} }}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
<div class="canvas">
{viewer}
</div>
</body>
</html>"""


# ---------------------------------------------------------------- 落盘

def _safe_name(title: str, fallback: str) -> str:
    """标题 → 合法文件名。去掉非法字符和句末标点，太长截断。"""
    cleaned = "".join(c for c in title if c not in r'\/:*?"<>|').strip()
    cleaned = cleaned.rstrip("。．.!！?？,，;；:：、…~～ ").strip()
    if len(cleaned) > 48:
        cleaned = cleaned[:48].rstrip()
    return cleaned or fallback


def _write(name: str, text: str) -> Path:
    config.ensure_dirs()
    path = config.ARTIFACT_DIR / name
    path.write_text(text, encoding="utf-8")
    return path


def export_markdown(note: storage.Note) -> dict[str, Any]:
    safe = _safe_name(note.title, note.id)
    path = _write(f"{safe}.md", note.markdown)
    return {
        "format": "markdown",
        "content": note.markdown,
        "download_path": str(path),
        "size": len(note.markdown.encode("utf-8")),
    }


def export_source(note: storage.Note) -> dict[str, Any]:
    return {
        "format": "source",
        "content": note.source_ref,
        "source_kind": note.source_kind,
    }


def export_svg(note: storage.Note) -> dict[str, Any]:
    nodes = note.mind_map or [{"title": note.title}]
    svg = render_svg(nodes, note.title)
    safe = _safe_name(note.title, note.id)
    path = _write(f"{safe}.svg", svg)
    html_path = _write(f"{safe}.html", render_html(nodes, note.title))
    return {
        "format": "svg",
        "download_path": str(path),
        "html_path": str(html_path),
        "size": len(svg.encode("utf-8")),
    }


def export_json_tree(note: storage.Note) -> dict[str, Any]:
    """脑图原始树。给前端渲染用（markmap 之类的输入）。"""
    return {
        "format": "json",
        "tree": note.mind_map or [{"title": note.title}],
        "title": note.title,
    }


def export_png(note: storage.Note) -> dict[str, Any]:
    """脑图 → PNG。需要 playwright；没装就退回 SVG。"""
    nodes = note.mind_map or [{"title": note.title}]
    safe = _safe_name(note.title, note.id)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        result = export_svg(note)
        result["format"] = "svg"
        result["note"] = (
            "未安装 playwright，已退回 SVG。"
            "要 PNG 请运行：pip install playwright && playwright install chromium"
        )
        return result

    placed, width, max_y = _layout(nodes, note.title)
    total_w = int(width + PADDING * 2)
    total_h = int(max_y + NODE_H + PADDING * 2)
    page = render_html(nodes, note.title)
    page_path = _write(f"{safe}.html", page)
    png_path = config.ARTIFACT_DIR / f"{safe}.png"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={"width": total_w + 80, "height": total_h + 160})
        pg.goto(page_path.as_uri())
        pg.screenshot(path=str(png_path), full_page=True)
        browser.close()

    return {
        "format": "png",
        "download_path": str(png_path),
        "download_urls": [str(png_path)],
        "page_count": 1,
        "size": png_path.stat().st_size,
    }


def dispatch(note: storage.Note, fmt: str) -> dict[str, Any]:
    if fmt == "markdown":
        return export_markdown(note)
    if fmt == "source":
        return export_source(note)
    if fmt == "svg":
        return export_svg(note)
    if fmt in ("json", "tree"):
        return export_json_tree(note)
    if fmt == "png":
        return export_png(note)
    raise ValueError(f"不支持的导出格式：{fmt}")
