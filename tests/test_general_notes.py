"""Topics, pasted text and webpages share complete notebooks and safe sources."""
import importlib.util
import json
from pathlib import Path
from zipfile import ZipFile

import pytest
from lxml import html
from seagull_notes import config, extract, obsidian_export, sources


def script(name):
    path = Path(__file__).resolve().parents[1] / "skill/scripts" / (name + ".py")
    spec = importlib.util.spec_from_file_location("general_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def topic():
    return {"title": "Git 与 GitHub", "source_kind": "topic", "source_text": "整理基础知识",
            "summary": "版本与协作", "sections": [{"title": "提交", "start": 42, "markdown": "完整解释与例子。"},
            {"title": "分支", "markdown": "分支概念与练习。"}], "tags": ["Git"],
            "sources": [{"title": "Git commit", "url": "https://git-scm.com/docs/git-commit"}],
            "explorers": [{"title": "存档流程", "steps": [{"title": "修改", "markdown": "先修改文件。"},
                            {"title": "提交", "markdown": "再创建提交。"}]}],
            "review": [{"question": "提交在哪里？", "answer": "保存在本地仓库。"}],
            "extensions": [{"title": "进一步学习", "markdown": "自己的补充解释。"}]}


@pytest.mark.parametrize("style", ["paper", "atlas", "folio", "whale", "anime", "cyber"])
def test_all_styles_keep_complete_topic_content_and_references(tmp_path, style):
    note = dict(topic(), style=style)
    page, markdown = script("notebook").render_note(note, tmp_path)
    document = html.fromstring(page)
    assert document.get("data-style") == style or document.xpath('//body/@data-style') == [style]
    assert len(document.cssselect('.chapter')) == 2
    assert not document.cssselect('.time')
    assert 'VIDEO NOTES' not in page and '字幕来源待核实' not in page
    assert document.cssselect('.explorer') and document.cssselect('.review-card') and document.cssselect('.extension-card')
    assert "先修改文件。" in markdown and "自己的补充解释。" in markdown
    assert not document.xpath('//script[@src] | //link[@rel="stylesheet"]')


@pytest.mark.parametrize("style", ["paper", "atlas", "folio", "whale", "anime", "cyber"])
def test_markdown_view_preserves_complete_source_without_executing_markup(tmp_path, style):
    note = dict(topic(), style=style)
    note["sections"][0]["markdown"] = '```html\n<script>alert("display only")</script>\n```\n\n$$x^2+1$$\n\n尾部内容。'
    page, markdown = script("notebook").render_note(note, tmp_path)
    document = html.fromstring(page)
    raw = document.cssselect('#markdown .raw')[0]
    assert raw.text_content() == markdown
    assert not raw.cssselect('script')
    assert '$$x^2+1$$' in raw.text_content() and '尾部内容。' in raw.text_content()


def test_pasted_text_is_material_but_topic_requires_research(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ARTIFACT_DIR", tmp_path)
    prepare = script("prepare")
    text = "# 用户笔记\n\n原文中有完整解释。"
    pasted = prepare.prepare(text, "text")
    assert pasted['source_kind'] == 'text' and pasted['needs_research'] is False
    assert Path(pasted['content_file']).read_text(encoding='utf-8') == text
    subject = prepare.prepare("Git 与 GitHub", "topic")
    assert subject['needs_research'] is True and subject['source_kind'] == 'topic'
    assert prepare.prepare(text, "text")['material_id'] == pasted['material_id']


def test_url_preparation_uses_real_extraction_and_keeps_asr_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ARTIFACT_DIR", tmp_path)
    prepare = script("prepare")
    calls = []
    def read(value, **options):
        calls.append(options)
        return {"ok": True, "title": "文章", "content": "实际网页正文。"}
    monkeypatch.setattr(prepare.fetch, "run", read)
    result = prepare.prepare('https://example.com/note', 'url')
    assert result['source_kind'] == 'article'
    assert calls[0]['allow_asr'] is False
    assert Path(result['content_file']).read_text(encoding='utf-8') == '实际网页正文。'


def test_failed_web_extraction_does_not_create_a_notebook(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ARTIFACT_DIR", tmp_path)
    prepare = script("prepare")
    monkeypatch.setattr(prepare.fetch, "run", lambda *args, **kwargs: {"ok": False, "error": {"code": "browser_required"}})
    assert prepare.prepare('https://example.com/note', 'url')['ok'] is False
    assert not list(tmp_path.rglob('material.txt'))


def test_source_links_reject_executable_urls():
    with pytest.raises(ValueError):
        sources.source_links({"sources": [{"title": "来源", "url": "javascript:alert(1)"}]})


@pytest.mark.parametrize("field,item", [
    ("explorers", {"title": "公式步骤", "steps": [{"title": "计算", "markdown": "$$x^2$$"}]}),
    ("review", {"question": "结果？", "answer": "$$x^2$$"}),
    ("extensions", {"title": "推导", "markdown": "$$x^2$$"}),
])
def test_formulas_in_interactive_components_load_offline_katex(tmp_path, field, item):
    note = topic()
    note[field] = [item]
    page, markdown = script("notebook").render_note(note, tmp_path)
    assert 'class="arithmatex"' in page and 'katex.render' in page
    assert '@font-face' in page and 'data:font/woff2;base64,' in page
    assert "$$x^2$$" in markdown


def test_documentation_main_container_preserves_all_sections_and_code():
    page = '<html><head><title>资料</title></head><body><div id="content"><nav>导航垃圾</nav><div id="main"><h1>正文</h1><section><h2>概念</h2><p>第一部分的解释。</p></section><section><h2>步骤</h2><pre>git status\ngit add file.txt</pre></section><section><h2>限制</h2><p>结尾的重要限制。</p></section><aside>侧栏垃圾</aside><script>alert(1)</script></div></div></body></html>'
    _, text = extract._html_to_text(page, 'https://example.com/docs')
    assert '第一部分的解释。' in text and 'git status' in text and '结尾的重要限制。' in text
    assert '导航垃圾' not in text and '侧栏垃圾' not in text and 'alert(1)' not in text


def test_topic_obsidian_export_keeps_interactive_component_text(tmp_path):
    note = topic()
    source = tmp_path/'note.json'
    source.write_text(json.dumps(note, ensure_ascii=False), encoding='utf-8')
    package = obsidian_export.export_bundle(note, source, tmp_path/'topic.zip')
    with ZipFile(package['obsidian_zip']) as archive:
        text = archive.read(package['obsidian_note']).decode('utf-8')
    assert '主题知识' in text and '视频' not in text
    assert '先修改文件。' in text and '自己的补充解释。' in text
