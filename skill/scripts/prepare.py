#!/usr/bin/env python3
"""Stage a topic, pasted text or accessible URL for the current AI to write notes."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from seagull_notes import config, sources
import fetch


def prepare(value: str, kind: str = "auto") -> dict:
    value = value.strip()
    if not value:
        raise ValueError("素材不能为空")
    if kind == "auto":
        kind = "url" if urlsplit(value).scheme in {"http", "https"} and "\n" not in value else "text"
    if kind in {"topic", "text"}:
        material = {"ok": True, "title": value.splitlines()[0][:100], "content": value,
                    "source_kind": kind, "source_origin": "主题需求" if kind == "topic" else "用户提供文本"}
    elif kind == "url":
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("网址必须是有效 HTTP/HTTPS 地址")
        material = fetch.run(value, allow_asr=False, language="zh")
        if not material.get("ok"):
            return material
        material.update(source_url=value, source_kind=sources.source_kind({"source_url": value}),
                        source_origin=material.get("origin") or "网页正文")
    else:
        raise ValueError("kind 必须是 auto/topic/text/url")
    identity = hashlib.sha256((kind + ":" + value).encode("utf-8")).hexdigest()[:16]
    folder = config.ARTIFACT_DIR / "materials" / identity
    folder.mkdir(parents=True, exist_ok=True)
    content_file = folder / "material.txt"
    content_file.write_text(material["content"], encoding="utf-8")
    metadata = dict(material)
    metadata.pop("content")
    metadata.update(content_file=str(content_file.resolve()), char_count=len(material["content"]),
                    material_id=identity, needs_research=kind == "topic")
    (folder / "source.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description="主题 / 粘贴文本 / 网页 → 笔记素材")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--source", help="主题、短文本或网址")
    source.add_argument("--file", type=Path, help="保存用户粘贴文本的 UTF-8 文件")
    parser.add_argument("--kind", choices=["auto", "topic", "text", "url"], default="auto")
    args = parser.parse_args()
    try:
        result = prepare(args.file.read_text(encoding="utf-8-sig") if args.file else args.source, args.kind)
    except (OSError, ValueError) as error:
        result = {"ok": False, "error": {"message": str(error)}}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
