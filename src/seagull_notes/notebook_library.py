"""Local catalogue for notebooks rendered by the skill."""

from __future__ import annotations

import hashlib
import html
import json
import shutil
import time
from pathlib import Path
from string import Template

from . import config


def notebook_id(source: Path) -> str:
    return hashlib.sha256(str(source.resolve()).encode("utf-8")).hexdigest()[:16]


def directory() -> Path:
    return config.ARTIFACT_DIR / "notebooks"


def duration_label(seconds: float | None) -> str:
    if not seconds:
        return ""
    hours, rest = divmod(int(seconds), 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes}:{seconds:02}"


def render_index(entries: list[dict], template_file: Path) -> str:
    cards = []
    for index, entry in enumerate(sorted(entries, key=lambda e: e["updated_at"], reverse=True)):
        title = html.escape(entry["title"])
        summary = html.escape(entry["summary"])
        platform = html.escape(entry["platform"])
        search = html.escape(" ".join([entry["title"], entry["summary"], entry["platform"]]), quote=True)
        if entry.get("cover"):
            kind = ' class="diagram"' if entry["cover_diagram"] else ""
            image = f'<img{kind} src="{entry["cover"]}" alt="{title}配图" loading="lazy">'
        else:
            image = f'<div class="cover-placeholder"><span>{entry["chapters"]:02}</span><small>个学习章节</small></div>'
        duration = duration_label(entry.get("duration"))
        details = " · ".join(value for value in [duration, f'{entry["chapters"]} 个章节'] if value)
        cards.append(f'<a class="note-card" href="{entry["html"]}" aria-labelledby="note-title-{index}" data-search="{search}" style="--delay:{min(index, 6)*45}ms">'
                     f'<div class="card-cover">{image}</div><div class="card-body"><span class="platform">{platform}</span>'
                     f'<h2 id="note-title-{index}">{title}</h2><p>{summary}</p><div class="card-foot"><span>{details}</span>'
                     '<span class="read-label">阅读笔记 <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14m-6-6 6 6-6 6"/></svg></span>'
                     '</div></div></a>')
        if entry.get("obsidian_zip"):
            cards[-1] = ('<div class="note-entry" data-search="' + search + '">' + cards[-1] +
                         f'<a class="obsidian-download" href="{entry["obsidian_zip"]}" download aria-label="导出 {title} 到 Obsidian">'
                         '<span>导入 Obsidian</span><span>可编辑笔记与图片 ↓</span></a></div>')
    return Template(template_file.read_text(encoding="utf-8")).substitute(cards="".join(cards), count=len(entries))


def register(note: dict, source: Path, page: str, markdown: str, template_file: Path, bundle: dict | None = None) -> dict[str, str]:
    folder = directory().resolve()
    folder.mkdir(parents=True, exist_ok=True)
    identity = notebook_id(source)
    manifest = folder / "notebooks.json"
    entries = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {}
    now = time.time()
    entry = {"title": note["title"], "summary": note.get("summary", ""),
             "platform": note.get("platform") or ("本地文件" if note.get("source_ref") else "视频"),
             "duration": note.get("duration"), "chapters": len(note["sections"]),
             "html": identity + ".html", "markdown": identity + ".md",
             "created_at": entries.get(identity, {}).get("created_at", now), "updated_at": now}
    if bundle:
        entry["obsidian_zip"] = Path(bundle["obsidian_zip"]).name
    if note.get("cover"):
        cover = (source.parent / note["cover"]["path"]).resolve()
        cover_name = identity + "-cover" + cover.suffix.lower()
        if cover != folder / cover_name:
            shutil.copyfile(cover, folder / cover_name)
        entry.update(cover=cover_name, cover_diagram=note["cover"].get("kind") == "diagram" or cover.suffix.lower() == ".svg")
    (folder / entry["html"]).write_text(page, encoding="utf-8")
    (folder / entry["markdown"]).write_text(markdown, encoding="utf-8")
    entries[identity] = entry
    temporary = manifest.with_suffix(".tmp")
    temporary.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(manifest)
    index = folder / "index.html"
    index.write_text(render_index(list(entries.values()), template_file), encoding="utf-8")
    packages = [folder / value["obsidian_zip"] for value in entries.values() if value.get("obsidian_zip")]
    if packages:
        from .obsidian_export import merge_bundles
        merge_bundles(packages, folder / "Seagull-Notes-Obsidian.zip")
    return {"library": str(index), "library_note": str(folder / entry["html"])}
