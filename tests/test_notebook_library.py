"""Rendered notebooks are collected without duplicating or losing explicit outputs."""

import importlib.util
import json
import sys
from pathlib import Path
from urllib.parse import unquote

import pytest
from lxml import html

from seagull_notes import config


@pytest.fixture
def notebook(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ARTIFACT_DIR", tmp_path / "artifacts")
    path = Path(__file__).resolve().parents[1] / "skill" / "scripts" / "notebook.py"
    spec = importlib.util.spec_from_file_location("library_notebook", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def input_note(path, title="课程笔记"):
    path.write_text(json.dumps({"title": title, "source_url": "https://youtu.be/example",
                               "summary": "关键概念和操作步骤", "platform": "YouTube", "duration": 60,
                               "sections": [{"title": "概念", "markdown": "正文"}]}, ensure_ascii=False), encoding="utf-8")


def generate(notebook, path, monkeypatch, capsys, out=None):
    args = ["notebook.py", str(path)] + (["--out", str(out)] if out else [])
    monkeypatch.setattr(sys, "argv", args)
    assert notebook.main() == 0
    return json.loads(capsys.readouterr().out)


def test_default_output_is_saved_in_library(notebook, tmp_path, monkeypatch, capsys):
    source = tmp_path / "note.json"
    input_note(source)
    result = generate(notebook, source, monkeypatch, capsys)
    folder = config.ARTIFACT_DIR / "notebooks"
    assert Path(result["html"]).parent == folder
    assert Path(result["library"]) == folder / "index.html"
    entries = json.loads((folder / "notebooks.json").read_text(encoding="utf-8"))
    assert len(entries) == 1
    doc = html.fromstring(Path(result["html"]).read_text(encoding="utf-8"))
    assert doc.xpath('//a[@class="library-link"]')[0].get("href") == "index.html"
    library = html.fromstring(Path(result["library"]).read_text(encoding="utf-8"))
    assert len(library.xpath('//a[@class="note-card"]')) == 1
    assert (folder / library.xpath('//a[@class="note-card"]')[0].get("href")).is_file()


def test_rerender_updates_same_entry_and_escapes_title(notebook, tmp_path, monkeypatch, capsys):
    source = tmp_path / "note.json"
    input_note(source)
    first = generate(notebook, source, monkeypatch, capsys)
    input_note(source, '新标题 <script>alert(1)</script>')
    second = generate(notebook, source, monkeypatch, capsys)
    assert first["html"] == second["html"]
    entries = json.loads((Path(second["library"]).parent / "notebooks.json").read_text(encoding="utf-8"))
    assert len(entries) == 1
    doc = html.fromstring(Path(second["library"]).read_text(encoding="utf-8"))
    assert '新标题 <script>alert(1)</script>' in doc.text_content()
    assert len(doc.xpath('//script')) == 1


def test_same_titles_from_different_inputs_do_not_overwrite(notebook, tmp_path, monkeypatch, capsys):
    results = []
    for name in ["one.json", "two.json"]:
        source = tmp_path / name
        input_note(source)
        results.append(generate(notebook, source, monkeypatch, capsys))
    assert results[0]["html"] != results[1]["html"]
    assert all(Path(result["html"]).is_file() for result in results)
    entries = json.loads((Path(results[0]["library"]).parent / "notebooks.json").read_text(encoding="utf-8"))
    assert len(entries) == 2


def test_explicit_output_keeps_working_and_is_also_collected(notebook, tmp_path, monkeypatch, capsys):
    source = tmp_path / "note.json"
    input_note(source)
    out = tmp_path / "existing" / "我的笔记"
    result = generate(notebook, source, monkeypatch, capsys, out)
    assert Path(result["html"]) == Path(str(out) + ".html")
    assert Path(result["library_note"]).is_file()
    original = html.fromstring(Path(result["html"]).read_text(encoding="utf-8"))
    href = unquote(original.xpath('//a[@class="library-link"]')[0].get("href"))
    assert (out.parent / href).resolve() == Path(result["library"])
    canonical = html.fromstring(Path(result["library_note"]).read_text(encoding="utf-8"))
    assert canonical.xpath('//a[@class="library-link"]')[0].get("href") == "index.html"


def test_library_keeps_cover_asset_and_all_notebook_images_embedded(notebook, tmp_path, monkeypatch, capsys):
    source = tmp_path / "note.json"
    input_note(source)
    picture = tmp_path / "cover.svg"
    picture.write_text('<svg xmlns="http://www.w3.org/2000/svg"><text>配图</text></svg>', encoding="utf-8")
    note = json.loads(source.read_text(encoding="utf-8"))
    note["cover"] = {"path": picture.name, "kind": "diagram", "caption": "根据字幕绘制的示意图"}
    source.write_text(json.dumps(note, ensure_ascii=False), encoding="utf-8")
    result = generate(notebook, source, monkeypatch, capsys)
    library = Path(result["library"])
    index = html.fromstring(library.read_text(encoding="utf-8"))
    cover_href = index.xpath('//a[@class="note-card"]//img')[0].get("src")
    assert (library.parent / cover_href).read_bytes() == picture.read_bytes()
    page = html.fromstring(Path(result["library_note"]).read_text(encoding="utf-8"))
    assert page.xpath('//figure//img')[0].get("src").startswith("data:image/svg+xml;base64,")
