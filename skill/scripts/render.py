#!/usr/bin/env python3
"""渲染脑图：JSON 树 → SVG + HTML。

这是 seagull-notes skill 的出图脚本。Codex 写好脑图树之后调它出图。

用法：
    python render.py mindmap.json
    python render.py mindmap.json --out 我的脑图
    cat mindmap.json | python render.py -

输出 JSON 到 stdout，说明生成的文件在哪。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_HOME = Path(os.environ.get("SEAGULL_NOTES_HOME", str(Path(__file__).resolve().parents[2])))
SRC_DIR = PROJECT_HOME / "src"

if str(SRC_DIR) not in sys.path and SRC_DIR.is_dir():
    sys.path.insert(0, str(SRC_DIR))


def _bootstrap() -> None:
    import importlib.util

    if importlib.util.find_spec("seagull_notes") is not None:
        return
    print(
        f"错误：找不到 seagull_notes 包。\n"
        f"  期望位置: {SRC_DIR}\n"
        f"  设 SEAGULL_NOTES_HOME 指向项目根目录，或参考 references/setup.md",
        file=sys.stderr,
    )
    raise SystemExit(2)


_bootstrap()

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from seagull_notes import export                      # noqa: E402


def _load_tree(source: str) -> list[dict]:
    if source == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(source).read_text(encoding="utf-8")

    data = json.loads(raw)

    # 允许三种形态：裸数组 / {"mind_map": [...]} / {"tree": [...]}
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("mind_map", "tree", "children", "nodes"):
            if isinstance(data.get(key), list):
                return data[key]
    raise ValueError("搞不清这个 JSON 的结构，期望是数组或含 mind_map/tree 字段的对象")


def main() -> int:
    parser = argparse.ArgumentParser(prog="render.py", description="脑图 JSON → SVG + HTML")
    parser.add_argument("tree", help="脑图 JSON 文件路径，或 - 从 stdin 读")
    parser.add_argument("--out", default="mindmap", help="输出文件名（不带扩展名）")
    parser.add_argument("--title", default="", help="图上显示的标题，默认用文件名")
    parser.add_argument("--png", action="store_true",
                        help="同时尝试导出 PNG（需要 playwright，没有就跳过）")
    args = parser.parse_args()

    try:
        tree = _load_tree(args.tree)
    except (json.JSONDecodeError, ValueError) as exc:
        json.dump({"ok": False, "error": {"code": "bad_json", "message": str(exc)}},
                  sys.stdout, ensure_ascii=False, indent=2)
        return 1

    safe = export._safe_name(args.out, "mindmap")
    title = args.title or safe

    svg = export.render_svg(tree, title)
    html = export.render_html(tree, title)

    from seagull_notes import config

    config.ensure_dirs()
    svg_path = config.ARTIFACT_DIR / f"{safe}.svg"
    html_path = config.ARTIFACT_DIR / f"{safe}.html"
    svg_path.write_text(svg, encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")

    def count(nodes: list) -> int:
        return sum(1 + count(n.get("children") or []) for n in nodes)

    result = {
        "ok": True,
        "title": title,
        "nodes": count(tree),
        "svg": str(svg_path),
        "html": str(html_path),
        "note": "HTML 可以直接在浏览器打开或打印成 PDF",
    }

    if args.png:
        try:
            from playwright.sync_api import sync_playwright   # noqa: F401
        except ImportError:
            result["png_note"] = "没装 playwright，跳过 PNG。装法见 references/setup.md"
        else:
            placed, width, max_y = export._layout(tree, title)
            total_w = int(width + export.PADDING * 2)
            total_h = int(max_y + export.NODE_H + export.PADDING * 2)
            png_path = config.ARTIFACT_DIR / f"{safe}.png"
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={"width": total_w + 80, "height": total_h + 160})
                page.goto(html_path.as_uri())
                page.screenshot(path=str(png_path), full_page=True)
                browser.close()
            result["png"] = str(png_path)

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
