"""Portable editable notes keep local assets and never overwrite vault edits."""

import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from seagull_notes import obsidian_export


def sample(tmp_path):
    (tmp_path / "diagram.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"><text>可编辑</text></svg>', encoding="utf-8")
    source = tmp_path / "note.json"
    note = {"title": "示例：公式与图片", "source_url": "https://www.bilibili.com/video/BV1/?p=2",
            "platform": "Bilibili", "uploader": "作者", "duration": 600,
            "summary": "概览", "takeaways": ["要点"], "subtitle_origin": "平台 AI 字幕",
            "cover": {"path": "diagram.svg", "caption": "字幕示意图", "kind": "diagram"},
            "sections": [{"title": "概念", "start": 42,
                          "markdown": '$$\\frac{a}{b}$$\n\n```bash\ngit status\n```',
                          "image": {"path": "diagram.svg", "caption": "同一张示意图"}}],
            "mind_map": [{"title": "主题", "children": [{"title": "概念"}]}], "transcript": "真实全文"}
    source.write_text(json.dumps(note, ensure_ascii=False), encoding="utf-8")
    return note, source


def test_bundle_uses_relative_attachments_and_keeps_editable_markdown(tmp_path):
    note, source = sample(tmp_path)
    package = tmp_path / "out" / "note.obsidian.zip"
    result = obsidian_export.export_bundle(note, source, package)
    with ZipFile(package) as archive:
        names = archive.namelist()
        md_path = result["obsidian_note"]
        text = archive.read(md_path).decode("utf-8")
        assert "cssclasses:\n  - seagull-notes" in text
        assert "$$\\frac{a}{b}$$" in text and "```bash\ngit status\n```" in text
        assert "p=2&t=42" in text
        assert "![[" in text and "|760]]" in text
        assert str(tmp_path) not in text and "data:image" not in text
        assets = [name for name in names if name.endswith(".svg")]
        assert len(assets) == 1
        assert archive.read(assets[0]) == (tmp_path / "diagram.svg").read_bytes()
        assert ".obsidian/snippets/seagull-notes.css" in names
        assert all(not Path(name).is_absolute() and ".." not in Path(name).parts for name in names)


def test_import_keeps_existing_user_note_and_image_edits(tmp_path):
    note, source = sample(tmp_path)
    package = tmp_path / "out" / "note.obsidian.zip"
    result = obsidian_export.export_bundle(note, source, package)
    vault = tmp_path / "vault"
    vault.mkdir()
    first = obsidian_export.import_bundle(package, vault)
    imported = vault / result["obsidian_note"]
    assert imported.is_file() and first["imported"] > 0
    image = next((vault / "Seagull Notes").rglob("*.svg"))
    imported.write_text("用户修改后的正文", encoding="utf-8")
    image.write_text("用户修改后的图片", encoding="utf-8")
    obsidian_export.import_bundle(package, vault)
    assert imported.read_text(encoding="utf-8") == "用户修改后的正文"
    assert image.read_text(encoding="utf-8") == "用户修改后的图片"


def test_local_media_export_does_not_require_original_file_after_import(tmp_path):
    note, source = sample(tmp_path)
    audio = tmp_path / "source.wav"
    audio.write_bytes(b"local audio")
    note.pop("source_url")
    note["source_ref"] = str(audio)
    result = obsidian_export.export_bundle(note, source, tmp_path / "note.zip")
    with ZipFile(result["obsidian_zip"]) as archive:
        text = archive.read(result["obsidian_note"]).decode("utf-8")
        assert "source.wav" in text and "youtube.com" not in text
        assert "00:42" in text


def test_combined_bundle_keeps_each_note_and_editable_canvas(tmp_path):
    note, source = sample(tmp_path)
    first = obsidian_export.export_bundle(note, source, tmp_path / "first.zip")
    other = tmp_path / "other.json"
    other.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    second = obsidian_export.export_bundle(note, other, tmp_path / "second.zip")
    combined = tmp_path / "all.zip"
    obsidian_export.merge_bundles([Path(first["obsidian_zip"]), Path(second["obsidian_zip"])], combined)
    with ZipFile(combined) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names))
        assert first["obsidian_note"] in names and second["obsidian_note"] in names
        canvases = [name for name in names if name.endswith(".canvas")]
        assert len(canvases) == 2
        for name in canvases:
            canvas = json.loads(archive.read(name))
            assert [node["text"] for node in canvas["nodes"]] == ["主题", "概念"]
            assert all(node["type"] == "text" for node in canvas["nodes"])
            assert canvas["edges"][0]["fromNode"] == canvas["nodes"][0]["id"]
            assert canvas["edges"][0]["toNode"] == canvas["nodes"][1]["id"]


def test_import_rejects_files_outside_vault(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    package = tmp_path / "invalid.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr("../outside.md", "must not be written")
    with pytest.raises(ValueError, match="越出 vault"):
        obsidian_export.import_bundle(package, vault)
    assert not (tmp_path / "outside.md").exists()

