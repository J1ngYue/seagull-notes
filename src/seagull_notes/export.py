"""导出：Markdown / 脑图 SVG / 脑图 PNG / 源文本。

PNG 需要 playwright（可选依赖）。没装的话自动退回 SVG + HTML，
用户在浏览器里打开一样能看能截图。
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from . import config, storage

# ---------------------------------------------------------------- 树布局

NODE_H = 34
NODE_GAP_Y = 14
LEVEL_GAP_X = 60
PADDING = 40
CHAR_W = 8.2


def _measure(title: str) -> float:
    return max(70.0, len(title) * CHAR_W + 24)


def _layout(nodes: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], float, float]:
    """自顶向下树布局。返回 (节点列表含x/y, 总宽, 总高)。"""
    placed: list[dict[str, Any]] = []

    def node_width(node: dict[str, Any]) -> float:
        return _measure(node["title"])

    def subtree_width(node: dict[str, Any]) -> float:
        kids = node.get("children") or []
        own = node_width(node)
        if not kids:
            return own
        kids_w = sum(subtree_width(k) for k in kids) + LEVEL_GAP_X * (len(kids) - 1)
        return max(own, kids_w)

    def place(node: dict[str, Any], depth: int, left: float) -> float:
        width = subtree_width(node)
        cx = left + width / 2
        placed.append({
            "title": node["title"],
            "x": cx,
            "y": depth * (NODE_H + NODE_GAP_Y),
            "depth": depth,
        })
        kids = node.get("children") or []
        if kids:
            cursor = left
            for kid in kids:
                place(kid, depth + 1, cursor)
                cursor += subtree_width(kid) + LEVEL_GAP_X
        return width

    total_w = sum(subtree_width(n) for n in nodes) + LEVEL_GAP_X * max(0, len(nodes) - 1)
    cursor = 0.0
    for node in nodes:
        place(node, 0, cursor)
        cursor += subtree_width(node) + LEVEL_GAP_X

    max_y = max((n["y"] for n in placed), default=0.0)
    return placed, total_w, max_y


# ---------------------------------------------------------------- SVG 渲染

PALETTE = ["#4A6CF7", "#7C5CFF", "#00A886", "#F2994A", "#EB5757", "#2D9CDB"]
BG = "#FFFFFF"
TEXT = "#1A1A2E"


def _edges(nodes: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []

    def walk(node: dict[str, Any], parent: dict[str, Any] | None) -> None:
        if parent is not None:
            pairs.append((parent, node))
        for kid in node.get("children") or []:
            walk(kid, node)

    for root in nodes:
        walk(root, None)
    return pairs


def render_svg(nodes: list[dict[str, Any]], title: str = "") -> str:
    """脑图 → SVG 字符串。纯手工布局，不依赖外部渲染库。"""
    if not nodes:
        nodes = [{"title": title or "空脑图"}]

    placed, width, max_y = _layout(nodes)
    total_w = width + PADDING * 2
    total_h = max_y + NODE_H + PADDING * 2

    # 用同一次遍历建立 id → 坐标映射，保证边和节点对得上
    coords: dict[int, dict[str, Any]] = {}

    def index(node: dict[str, Any], depth: int, left: float, width_fn) -> None:
        w = width_fn(node)
        cx = left + w / 2
        coords[id(node)] = {"x": cx, "y": depth * (NODE_H + NODE_GAP_Y), "w": _measure(node["title"])}
        kids = node.get("children") or []
        cursor = left
        for kid in kids:
            index(kid, depth + 1, cursor, width_fn)
            cursor += width_fn(kid) + LEVEL_GAP_X

    def subtree_width(node: dict[str, Any]) -> float:
        kids = node.get("children") or []
        own = _measure(node["title"])
        if not kids:
            return own
        kids_w = sum(subtree_width(k) for k in kids) + LEVEL_GAP_X * (len(kids) - 1)
        return max(own, kids_w)

    cursor = 0.0
    for root in nodes:
        index(root, 0, cursor, subtree_width)
        cursor += subtree_width(root) + LEVEL_GAP_X

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_w:.0f}" height="{total_h:.0f}" '
        f'viewBox="0 0 {total_w:.0f} {total_h:.0f}">',
        f'<rect width="100%" height="100%" fill="{BG}"/>',
        '<g font-family="-apple-system,BlinkMacSystemFont,Segoe UI,PingFang SC,Microsoft YaHei,sans-serif">',
    ]

    # 边：三次贝塞尔
    for parent, child in _edges(nodes):
        p, c = coords[id(parent)], coords[id(child)]
        x1, y1 = p["x"] + PADDING, p["y"] + NODE_H / 2 + PADDING
        x2, y2 = c["x"] + PADDING, c["y"] + NODE_H / 2 + PADDING
        mid = (y1 + y2) / 2
        color = PALETTE[p["y"] // (NODE_H + NODE_GAP_Y) % len(PALETTE)]
        parts.append(
            f'<path d="M {x1:.1f} {y1:.1f} C {x1:.1f} {mid:.1f}, {x2:.1f} {mid:.1f}, '
            f'{x2:.1f} {y2:.1f}" fill="none" stroke="{color}" stroke-width="2" opacity="0.55"/>'
        )

    # 节点
    for node in nodes:
        stack = [node]
        while stack:
            current = stack.pop()
            stack.extend(current.get("children") or [])
            info = coords[id(current)]
            x = info["x"] + PADDING - info["w"] / 2
            y = info["y"] + PADDING
            depth = int(info["y"] // (NODE_H + NODE_GAP_Y))
            color = PALETTE[depth % len(PALETTE)]
            fill = color if depth <= 1 else "#FFFFFF"
            text_color = "#FFFFFF" if depth <= 1 else TEXT
            font_size = 15 if depth == 0 else (14 if depth == 1 else 13)
            weight = 600 if depth <= 1 else 400
            parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{info["w"]:.1f}" height="{NODE_H}" '
                f'rx="{NODE_H / 2:.1f}" fill="{fill}" stroke="{color}" stroke-width="2"/>'
            )
            parts.append(
                f'<text x="{info["x"] + PADDING:.1f}" y="{y + NODE_H / 2 + 5:.1f}" '
                f'text-anchor="middle" font-size="{font_size}" font-weight="{weight}" '
                f'fill="{text_color}">{html.escape(current["title"])}</text>'
            )

    parts.append("</g></svg>")
    return "\n".join(parts)


def render_html(nodes: list[dict[str, Any]], title: str) -> str:
    """把 SVG 包成独立 HTML，浏览器直接打开。"""
    svg = render_svg(nodes, title)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{html.escape(title)} - 脑图</title>
<style>
  body {{ margin: 0; padding: 32px; background: #F7F8FC;
         font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif; }}
  h1 {{ font-size: 22px; color: #1A1A2E; margin: 0 0 24px; }}
  .canvas {{ background: #fff; border-radius: 16px; padding: 24px;
             box-shadow: 0 4px 24px rgba(0,0,0,0.06); overflow: auto; }}
  @media print {{ body {{ background: #fff; padding: 0; }} .canvas {{ box-shadow: none; }} }}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
<div class="canvas">
{svg}
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

    placed, width, max_y = _layout(nodes)
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
