#!/usr/bin/env python3
"""Plot verified numeric data as a notebook figure; export SVG and PNG."""

from __future__ import annotations

import argparse
import json
import math
import sys
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
from matplotlib import font_manager, pyplot as plt

BG, INK, MUTED = "#fffdf7", "#594533", "#84725f"
CURVE, ACCENT = "#846a45", "#a36b4f"


def validate(data: dict) -> None:
    x, y = data["x"], data["y"]
    if len(x) != len(y) or len(x) < 2:
        raise ValueError("x and y must contain the same number of values, at least two")
    points = list(zip(x, y)) + [(point["x"], point["y"]) for point in data.get("steps", [])]
    if not all(isinstance(value, (int, float)) and math.isfinite(value) for point in points for value in point):
        raise ValueError("Coordinates must be finite numbers; missing values cannot be silently removed")
    if len(data.get("steps", [])) > 5:
        raise ValueError("Use at most five highlighted steps per figure to keep labels readable")


def make_figure(data: dict):
    validate(data)
    available = {font.name for font in font_manager.fontManager.ttflist}
    fonts = [name for name in ("Microsoft YaHei", "Noto Sans CJK SC", "SimHei", "DejaVu Sans") if name in available]
    bold_path = next((font.fname for font in font_manager.fontManager.ttflist if font.name == fonts[0] and font.weight == 700), None)
    with plt.rc_context({"font.family": fonts, "font.size": 12, "svg.fonttype": "path", "axes.unicode_minus": False}):
        fig = plt.figure(figsize=(10, 7.2), layout="constrained", facecolor=BG)
        fig.get_layout_engine().set(w_pad=.28, h_pad=.20)
        grid = fig.add_gridspec(3, 1, height_ratios=[1, 4.8, 1.15])
        header, ax, footer = [fig.add_subplot(grid[i]) for i in range(3)]
        header.set_axis_off()
        footer.set_axis_off()
        header.text(0, .76, textwrap.fill(data["title"], 32), fontsize=22,
                    fontproperties=font_manager.FontProperties(fname=bold_path) if bold_path else None, color=INK, va="top")
        header.text(0, .15, textwrap.fill(data.get("subtitle", ""), 60), fontsize=11, color=MUTED, va="top")
        ax.set_facecolor(BG)
        ax.plot(data["x"], data["y"], color=CURVE, linewidth=2.8)
        ax.set(xlabel=data["x_label"], ylabel=data["y_label"])
        ax.tick_params(colors=MUTED, labelsize=11, length=0, pad=9)
        ax.xaxis.label.set_color(INK)
        ax.yaxis.label.set_color(INK)
        ax.grid(axis="y", color="#e7dccb", linewidth=.8, linestyle=(0, (3, 5)))
        ax.set_axisbelow(True)
        ax.margins(x=.09, y=.16)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("bottom", "left"):
            ax.spines[side].set_color("#dcc8a8")
        steps = data.get("steps", [])
        for i, point in enumerate(steps):
            xy = point["x"], point["y"]
            ax.scatter(*xy, s=330, color=ACCENT, edgecolor=BG, linewidth=2, zorder=5)
            ax.annotate(str(i), xy=xy, color="white", fontsize=11, ha="center", va="center", zorder=6)
            if i:
                previous = steps[i-1]
                ax.annotate("", xy=xy, xytext=(previous["x"], previous["y"]),
                            arrowprops={"arrowstyle": "-|>", "color": ACCENT, "lw": 1.6,
                                        "connectionstyle": "arc3,rad=.16", "shrinkA": 13, "shrinkB": 13}, zorder=3)
            footer.text((i+.5)/len(steps), .72,
                        f'{i}  ·  {data["x_label"]} = {point["x"]:g}\n{data["y_label"]} = {point["y"]:g}',
                        ha="center", va="top", color=INK, fontsize=10, linespacing=1.8,
                        bbox={"boxstyle": "round,pad=.7", "facecolor": "#fcf7ee", "edgecolor": "none"})
        footer.text(0, -.12, textwrap.fill(data.get("note", ""), 65), color=MUTED, fontsize=9, va="top")
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        width, height = fig.bbox.size
        texts = header.texts + ax.texts + footer.texts + [ax.xaxis.label, ax.yaxis.label]
        for artist in texts:
            if artist.get_visible() and artist.get_text():
                bounds = artist.get_window_extent(renderer)
                if bounds.x0 < -1 or bounds.y0 < -1 or bounds.x1 > width+1 or bounds.y1 > height+1:
                    plt.close(fig)
                    raise ValueError(f"A label would be clipped: {artist.get_text()!r}; shorten it")
        for group in (header.texts, ax.texts, footer.texts):
            boxes = [artist.get_window_extent(renderer) for artist in group if artist.get_visible() and artist.get_text()]
            if any(left.overlaps(right) for i, left in enumerate(boxes) for right in boxes[i+1:]):
                plt.close(fig)
                raise ValueError("Labels overlap; shorten the text or highlight fewer, separated steps")
        return fig


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Numeric plot JSON → SVG + PNG")
    parser.add_argument("data", type=Path)
    parser.add_argument("--out", required=True, type=Path, help="Output base path without an extension")
    args = parser.parse_args()
    try:
        data = json.loads(args.data.read_text(encoding="utf-8-sig"))
        fig = make_figure(data)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        paths = {ext: Path(f"{args.out}.{ext}") for ext in ("svg", "png")}
        try:
            with plt.rc_context({"svg.fonttype": "path"}):
                for ext, path in paths.items():
                    fig.savefig(path, dpi=150, facecolor=BG, bbox_inches=None)
        finally:
            plt.close(fig)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, **{ext: str(path.resolve()) for ext, path in paths.items()}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
