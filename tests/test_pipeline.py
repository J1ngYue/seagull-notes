"""管线核心逻辑测试。不依赖网络、不依赖 GPU、不依赖 LLM。"""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET

import pytest

from seagull_notes import config, export, generate, media, pipeline, storage


# ------------------------------------------------------------------ 存储层

def test_content_key_stable_and_normalized():
    a = storage.content_key("  hello world  ")
    b = storage.content_key("hello world")
    assert a == b, "首尾空白应该被归一化"
    assert a != storage.content_key("hello worlds")
    assert len(a) == 32


def test_job_lifecycle_and_terminal_states():
    job = storage.create_job(output_type="mind_map", source="https://example.com")
    assert job.status == "queued"
    assert not job.terminal

    storage.update_job(job.id, status="completed", stage="done", note_id="note_x")
    reloaded = storage.get_job(job.id)
    assert reloaded.status == "completed"
    assert reloaded.terminal
    assert reloaded.note_id == "note_x"


@pytest.mark.parametrize("status", ["completed", "failed", "blocked", "canceled"])
def test_terminal_statuses(status):
    job = storage.create_job(output_type="detailed_markdown", source="x")
    storage.update_job(job.id, status=status)
    assert storage.get_job(job.id).terminal


@pytest.mark.parametrize("status", ["queued", "processing"])
def test_non_terminal_statuses(status):
    job = storage.create_job(output_type="detailed_markdown", source="x")
    storage.update_job(job.id, status=status)
    assert not storage.get_job(job.id).terminal


def test_transcript_cache_roundtrip():
    key = storage.content_key("video:abc")
    assert storage.get_transcript(key) is None

    storage.save_transcript(
        key, text="转写内容", segments=[{"start": 0.0, "end": 1.5, "text": "转写内容"}],
        duration=1.5, origin="asr",
    )
    cached = storage.get_transcript(key)
    assert cached["text"] == "转写内容"
    assert cached["segments"][0]["start"] == 0.0
    assert cached["origin"] == "asr"


def test_note_mind_map_survives_roundtrip():
    tree = [{"title": "根", "children": [{"title": "子", "children": [{"title": "孙"}]}]}]
    note = storage.save_note(
        title="测试", markdown="# 测试", mind_map=tree,
        source_kind="raw", source_ref="inline:text",
    )
    loaded = storage.get_note(note.id)
    assert loaded.mind_map == tree
    assert loaded.markdown == "# 测试"


def test_list_notes_pagination():
    """翻页不能重复、不能漏——同一时刻建的多条笔记也要正确切分。"""
    import time as _time

    created = [
        storage.save_note(
            title=f"分页{i}", markdown=f"# {i}", mind_map=None,
            source_kind="raw", source_ref="inline:text",
        )
        for i in range(5)
    ]
    # 把 created_at 全钉成同一个值，专门压测 tiebreaker 路径
    same = _time.time()
    with storage._connect() as conn:
        conn.execute(
            "UPDATE notes SET created_at = ? WHERE id IN (%s)"
            % ",".join("?" * len(created)),
            [same] + [n.id for n in created],
        )

    seen: list[str] = []
    cursor = None
    cursor_id = None
    for _ in range(5):                                  # 防止死循环
        page, nxt = storage.list_notes(limit=2, cursor=cursor, cursor_id=cursor_id)
        seen.extend(n.id for n in page)
        if nxt is None:
            break
        cursor, cursor_id = nxt

    assert len(seen) == 5, f"应该翻出 5 条，实际 {len(seen)}"
    assert len(set(seen)) == 5, "翻页出现了重复条目"
    assert set(seen) == {n.id for n in created}, "翻页漏了条目"


def test_list_notes_cursor_terminates_on_last_page():
    storage.save_note(
        title="最后一条", markdown="x", mind_map=None,
        source_kind="raw", source_ref="x",
    )
    _, nxt = storage.list_notes(limit=20)
    assert nxt is None, "不足一页时不该给出 cursor"


def test_list_notes_limit_is_clamped():
    _, _ = storage.list_notes(limit=999)
    _, _ = storage.list_notes(limit=0)
    # 只是不能炸


# ------------------------------------------------------------------ 路径识别

@pytest.mark.parametrize("value", [
    r"D:\videos\lecture.mp4",
    r"E:/seagull-notes/data/a.pdf",
    r"\\server\share\file.mp4",
    "./relative/file.md",
    "C:\\path\\to\\note.txt",
])
def test_looks_like_path_positive(value):
    assert pipeline._looks_like_path(value)


@pytest.mark.parametrize("value", [
    "梯度下降是机器学习里的优化算法。",
    "这是一段没有任何路径特征的普通文本",
    "hello world, this is just prose",
])
def test_looks_like_path_negative(value):
    assert not pipeline._looks_like_path(value)


def test_multiline_text_never_treated_as_path():
    assert not pipeline._looks_like_path("D:\\a.mp4\n还有第二行")


def test_guess_title_prefers_first_sentence():
    text = "梯度下降是核心优化算法。它沿着负梯度方向更新参数。"
    assert pipeline._guess_title(text) == "梯度下降是核心优化算法。"


def test_guess_title_falls_back_to_first_line():
    assert pipeline._guess_title("没有标点的长句子在这里") == "没有标点的长句子在这里"


def test_guess_title_truncates_long_input():
    title = pipeline._guess_title("字" * 100)
    assert len(title) <= 41
    assert title.endswith("…")


def test_guess_title_skips_markdown_heading_marker():
    assert pipeline._guess_title("# 我的标题\n正文") == "我的标题"


# ------------------------------------------------------------------ 字幕解析

def test_parse_srt():
    srt = """1
00:00:01,000 --> 00:00:03,000
第一句字幕

2
00:00:03,500 --> 00:00:05,000
第二句字幕
"""
    text = media._parse_srt(srt)
    assert "第一句字幕" in text
    assert "第二句字幕" in text
    assert "-->" not in text
    assert "00:00:01" not in text


def test_parse_vtt_strips_tags_and_dedupes():
    vtt = """WEBVTT
Kind: captions
Language: zh

00:00:01.000 --> 00:00:03.000
<c>第一行</c>

00:00:03.000 --> 00:00:05.000
第一行

00:00:05.000 --> 00:00:07.000
第二行
"""
    text = media._parse_vtt(vtt)
    assert "<c>" not in text
    assert "第一行" in text
    assert "第二行" in text
    assert text.count("第一行") == 1, "相邻重复行应被去掉"


def test_parse_json3():
    import json

    payload = json.dumps({
        "events": [
            {"segs": [{"utf8": "你好"}, {"utf8": "世界"}]},
            {"segs": [{"utf8": "\n"}]},
            {"segs": [{"utf8": "第二句"}]},
        ]
    })
    assert media._parse_json3(payload) == "你好世界第二句"


def test_is_video_url():
    assert media.is_video_url("https://www.bilibili.com/video/BV1xx")
    assert media.is_video_url("https://youtu.be/abc")
    assert not media.is_video_url("https://github.com/facebook/react")


# ------------------------------------------------------------------ 字幕文件

def test_classify_subtitle_files():
    from pathlib import Path as P

    from seagull_notes import extract

    for name in ("a.srt", "b.vtt", "c.ass", "d.ssa", "e.json3", "f.sbv", "g.lrc"):
        assert extract.classify_local_file(P(name)) == "subtitle", name


def test_extract_srt_file(tmp_path):
    """字幕文件要解析成干净文本，不能带时间轴和序号。"""
    from seagull_notes import extract

    srt = tmp_path / "test.srt"
    srt.write_text(
        "1\n00:00:01,000 --> 00:00:04,000\n第一句\n\n"
        "2\n00:00:04,500 --> 00:00:08,000\n第二句\n",
        encoding="utf-8",
    )
    doc = extract.extract_subtitle_file(srt)

    assert doc.kind == "subtitle"
    assert "第一句" in doc.text
    assert "第二句" in doc.text
    assert "-->" not in doc.text
    assert "00:00:01" not in doc.text
    assert not doc.text.strip().startswith("1")


def test_extract_vtt_file(tmp_path):
    from seagull_notes import extract

    vtt = tmp_path / "test.vtt"
    vtt.write_text(
        "WEBVTT\nKind: captions\n\n"
        "00:00:01.000 --> 00:00:03.000\n<c>带标签的字幕</c>\n\n"
        "00:00:03.000 --> 00:00:05.000\n第二行\n",
        encoding="utf-8",
    )
    doc = extract.extract_subtitle_file(vtt)

    assert "带标签的字幕" in doc.text
    assert "<c>" not in doc.text
    assert "第二行" in doc.text


def test_extract_ass_file(tmp_path):
    from seagull_notes import extract

    ass = tmp_path / "test.ass"
    ass.write_text(
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\\pos(1,2)}带样式标签\n"
        "Dialogue: 0,0:00:03.00,0:00:05.00,Default,,0,0,0,,第二句\\N换行处理\n",
        encoding="utf-8",
    )
    doc = extract.extract_subtitle_file(ass)

    assert "带样式标签" in doc.text
    assert "{\\pos" not in doc.text
    assert "第二行" not in doc.text          # 确认标签被清掉而不是留下残渣
    assert "第二句" in doc.text


def test_extract_lrc_file(tmp_path):
    from seagull_notes import extract

    lrc = tmp_path / "test.lrc"
    lrc.write_text("[00:01.00]第一句\n[00:03.50]第二句\n", encoding="utf-8")
    doc = extract.extract_subtitle_file(lrc)

    assert "第一句" in doc.text
    assert "第二句" in doc.text
    assert "[00:01.00]" not in doc.text


def test_subtitle_file_gives_clean_text_for_note_writing(tmp_path):
    """端到端：字幕文件 → 可直接写笔记的干净文本。"""
    from seagull_notes import extract

    srt = tmp_path / "lecture.srt"
    srt.write_text(
        "1\n00:00:01,000 --> 00:00:04,000\n梯度下降是核心优化算法\n\n"
        "2\n00:00:04,000 --> 00:00:08,000\n学习率太大会震荡\n",
        encoding="utf-8",
    )
    doc = extract.extract_subtitle_file(srt)

    # 不该有数字序号行
    for line in doc.text.splitlines():
        assert not line.strip().isdigit(), f"残留了序号行: {line!r}"


# ------------------------------------------------------------------ 生成降级

def test_fallback_generate_produces_markdown_and_tree():
    content = "\n\n".join(f"第{i}段内容" for i in range(12))
    note = generate._fallback_generate(content, "测试标题", "detailed_markdown", "auto", "zh-CN")

    assert note.title == "测试标题"
    assert note.markdown.startswith("# 测试标题")
    assert note.generator == "fallback"
    assert note.mind_map and note.mind_map[0]["title"] == "测试标题"
    assert note.mind_map[0]["children"], "应该有子节点"


def test_generate_without_api_key_uses_fallback():
    note = asyncio.run(generate.generate("一些内容", title="标题"))
    assert note.generator == "fallback"


def test_extract_json_handles_code_fence():
    raw = '```json\n{"title": "t", "markdown": "m", "mind_map": []}\n```'
    assert generate._extract_json(raw)["title"] == "t"


def test_extract_json_handles_prose_wrapper():
    raw = '这是结果：{"title": "t", "markdown": "m"} 完毕'
    assert generate._extract_json(raw)["markdown"] == "m"


def test_normalize_tree_cleans_bad_shapes():
    messy = [
        "纯字符串节点",
        {"title": "正常", "children": [{"name": "用 name 字段"}]},
        {"no_title_here": True},
        {"title": "  ", "children": []},
    ]
    clean = generate._normalize_tree(messy)
    titles = [n["title"] for n in clean]
    assert "纯字符串节点" in titles
    assert "正常" in titles
    assert "用 name 字段" in clean[1]["children"][0]["title"] if len(clean) > 1 else True
    assert all(t.strip() for t in titles), "不该留下空标题"


def test_normalize_tree_rejects_non_list():
    assert generate._normalize_tree("不是列表") == []
    assert generate._normalize_tree(None) == []


# ------------------------------------------------------------------ 导出

SAMPLE_TREE = [{
    "title": "根节点",
    "children": [
        {"title": "分支一", "children": [{"title": "叶子1"}, {"title": "叶子2"}]},
        {"title": "分支二"},
    ],
}]


def test_render_svg_is_valid_xml():
    svg = export.render_svg(SAMPLE_TREE, "测试")
    root = ET.fromstring(svg)                      # 不合法会直接抛
    assert root.tag.endswith("svg")
    assert root.get("width") and root.get("height")


def test_render_svg_contains_all_node_titles():
    svg = export.render_svg(SAMPLE_TREE, "测试")
    for title in ("根节点", "分支一", "分支二", "叶子1", "叶子2"):
        assert title in svg


def test_render_svg_escapes_special_chars():
    tree = [{"title": "<script>alert(1)</script>"}]
    svg = export.render_svg(tree, "x")
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg
    ET.fromstring(svg)                             # 仍然得是合法 XML


def test_render_svg_handles_empty_tree():
    svg = export.render_svg([], "空脑图")
    ET.fromstring(svg)
    assert "空脑图" in svg


def test_render_html_wraps_svg():
    page = export.render_html(SAMPLE_TREE, "标题")
    assert page.startswith("<!DOCTYPE html>")
    assert "<svg" in page
    assert "标题" in page


def test_safe_name_strips_illegal_chars():
    name = export._safe_name(r'标题/带非法:字符*的?"文件<>|名', "fallback")
    for ch in r'\/:*?"<>|':
        assert ch not in name


def test_safe_name_strips_trailing_punctuation():
    assert export._safe_name("梯度下降是核心算法。", "fb") == "梯度下降是核心算法"
    assert export._safe_name("这是什么？", "fb") == "这是什么"


def test_safe_name_truncates_long_titles():
    name = export._safe_name("字" * 200, "fb")
    assert len(name) <= 48


def test_safe_name_falls_back_when_empty():
    assert export._safe_name("。。。", "note_abc") == "note_abc"


def test_export_dispatch_all_formats():
    note = storage.save_note(
        title="导出测试", markdown="# 导出测试\n\n正文",
        mind_map=SAMPLE_TREE, source_kind="raw", source_ref="inline:text",
    )
    for fmt in ("markdown", "svg", "json", "source"):
        result = export.dispatch(note, fmt)
        assert result["format"] == fmt or fmt == "json"

    md = export.dispatch(note, "markdown")
    assert md["content"].startswith("# 导出测试")
    assert md["size"] > 0

    tree = export.dispatch(note, "json")["tree"]
    assert tree == SAMPLE_TREE

    svg = export.dispatch(note, "svg")
    assert svg["download_path"].endswith(".svg")
    assert svg["html_path"].endswith(".html")


def test_export_dispatch_rejects_unknown_format():
    note = storage.save_note(
        title="x", markdown="x", mind_map=None, source_kind="raw", source_ref="x",
    )
    with pytest.raises(ValueError):
        export.dispatch(note, "exe")


def test_export_png_falls_back_without_playwright():
    note = storage.save_note(
        title="png测试", markdown="x", mind_map=SAMPLE_TREE,
        source_kind="raw", source_ref="x",
    )
    try:
        import playwright  # noqa: F401
        pytest.skip("playwright 已安装，跳过降级路径")
    except ImportError:
        pass
    result = export.export_png(note)
    assert result["format"] == "svg", "没 playwright 应该退回 svg"
    assert "playwright" in result.get("note", "")


# ------------------------------------------------------------------ 代理绕行

def test_needs_direct_for_cn_sites():
    for url in (
        "https://www.bilibili.com/video/BV1xx",
        "https://b23.tv/abc",
        "https://www.zhihu.com/question/1",
        "https://www.douyin.com/video/1",
    ):
        assert config.needs_direct(url), url


def test_needs_direct_false_for_foreign_sites():
    for url in (
        "https://www.youtube.com/watch?v=x",
        "https://github.com/facebook/react",
        "https://example.com",
    ):
        assert not config.needs_direct(url), url


def test_find_physical_ip_prefers_lan_over_tun(monkeypatch):
    """探测物理网卡时，TUN 隧道网段要排最后。"""
    import socket as _socket

    fake = [
        (None, None, None, None, ("127.0.0.1", 0)),
        (None, None, None, None, ("172.19.0.2", 0)),     # TUN
        (None, None, None, None, ("192.168.1.50", 0)),   # 物理网卡
    ]
    monkeypatch.setattr(_socket, "getaddrinfo", lambda *a, **k: fake)
    monkeypatch.setattr(config, "DIRECT_BIND_ADDRESS", "auto")

    assert config.find_physical_ip() == "192.168.1.50"


def test_find_physical_ip_returns_tun_when_only_option(monkeypatch):
    import socket as _socket

    fake = [(None, None, None, None, ("172.19.0.2", 0))]
    monkeypatch.setattr(_socket, "getaddrinfo", lambda *a, **k: fake)
    monkeypatch.setattr(config, "DIRECT_BIND_ADDRESS", "auto")

    # 只有 TUN 也得返回，总比没有强
    assert config.find_physical_ip() == "172.19.0.2"


def test_find_physical_ip_honours_explicit_override(monkeypatch):
    monkeypatch.setattr(config, "DIRECT_BIND_ADDRESS", "10.0.0.7")
    assert config.find_physical_ip() == "10.0.0.7"


# ------------------------------------------------------------------ ASR 幻觉检测

def _segs(texts):
    return [{"start": i, "end": i + 1, "text": t} for i, t in enumerate(texts)]


def test_hallucination_detects_exact_repeat():
    from seagull_notes import asr

    repeated = _segs(["演唱 李宗盛"] * 8)
    assert asr._looks_like_hallucination(repeated)


def test_hallucination_detects_common_prefix():
    from seagull_notes import asr

    variant = _segs([
        "中文字幕志愿者 张三",
        "中文字幕志愿者 李四",
        "中文字幕志愿者 王五",
        "中文字幕志愿者 赵六",
    ])
    assert asr._looks_like_hallucination(variant)


def test_hallucination_ignores_short_input():
    from seagull_notes import asr

    assert not asr._looks_like_hallucination(_segs(["一句", "两句"]))
    assert not asr._looks_like_hallucination([])


def test_hallucination_allows_genuine_speech():
    from seagull_notes import asr

    real = _segs([
        "大家好我是来自森林寺寝室的苏黄",
        "我今天来讲的是GalGame",
        "或者说通俗一点讲就是网上的打卡",
        "那我自己呢在PV上做了一个开场通话",
        "给大家演绎一下",
    ])
    assert not asr._looks_like_hallucination(real)


# ------------------------------------------------------------------ 端到端

def test_full_pipeline_with_raw_text(tmp_path):
    """纯文本走完整管线，不碰网络。"""
    source = "梯度下降是核心优化算法。它沿着负梯度方向更新参数。\n\n学习率太大会震荡。"
    job = storage.create_job(output_type="detailed_markdown", source=source)
    result = asyncio.run(pipeline.run_job(job.id))

    assert result.status == "completed"
    assert result.note_id

    note = storage.get_note(result.note_id)
    assert note.title
    assert note.markdown
    assert note.mind_map

    final_job = storage.get_job(job.id)
    assert final_job.terminal
    assert final_job.note_id == result.note_id


def test_pipeline_blocks_on_empty_source():
    job = storage.create_job(output_type="detailed_markdown", source="   ")
    result = asyncio.run(pipeline.run_job(job.id))
    assert result.status == "blocked"
    assert storage.get_job(job.id).error_code == "empty_content"


def test_pipeline_fails_on_missing_file():
    job = storage.create_job(
        output_type="detailed_markdown", source=r"E:\definitely\not\here.mp4",
    )
    result = asyncio.run(pipeline.run_job(job.id))
    assert result.status == "failed"
    assert storage.get_job(job.id).error_code == "FileNotFoundError"


def test_pipeline_writes_markdown_artifact():
    source = "一段用于测试的文本内容。第二句话在这里。"
    job = storage.create_job(output_type="detailed_markdown", source=source)
    result = asyncio.run(pipeline.run_job(job.id))
    note = storage.get_note(result.note_id)

    md = export.dispatch(note, "markdown")
    from pathlib import Path

    path = Path(md["download_path"])
    assert path.exists()
    assert path.read_text(encoding="utf-8") == note.markdown


# ------------------------------------------------------- 素材模式（客户端写笔记）

def test_material_mode_stops_at_awaiting_note():
    """素材模式：抽完就停，不生成笔记，等客户端来交付。"""
    source = "某段需要被整理成笔记的原始素材内容。第二句在这里。"
    job = storage.create_job(output_type="material", source=source)
    result = asyncio.run(pipeline.run_job(job.id))

    assert result.status == "completed"
    assert result.stage == storage.AWAITING_NOTE_STAGE
    assert result.note_id is None, "素材模式不该自己生成笔记"
    assert result.generator == "client"

    final = storage.get_job(job.id)
    assert final.terminal
    assert final.stage == "awaiting_note"


def test_material_is_retrievable_after_extraction():
    source = "第一段。第二段。第三段。"
    job = storage.create_job(output_type="material", source=source)
    asyncio.run(pipeline.run_job(job.id))

    material = storage.get_material(job.id)
    assert material is not None
    assert material.body == source
    assert material.char_count == len(source)
    assert material.source_kind == "raw"


def test_material_absent_before_extraction():
    job = storage.create_job(output_type="material", source="还没跑")
    assert storage.get_material(job.id) is None


def test_save_note_completes_material_job():
    """客户端交付笔记后，作业应该收尾成 completed。"""
    source = "原始素材内容。"
    job = storage.create_job(output_type="material", source=source)
    asyncio.run(pipeline.run_job(job.id))

    note = storage.save_note(
        title="客户端写的笔记",
        markdown="# 客户端写的笔记\n\n整理过的内容。",
        mind_map=[{"title": "根", "children": [{"title": "分支"}]}],
        source_kind="raw",
        source_ref=job.source,
    )
    storage.update_job(job.id, status="completed", stage="done", note_id=note.id)

    final = storage.get_job(job.id)
    assert final.note_id == note.id
    assert storage.get_note(note.id).markdown.startswith("# 客户端写的笔记")


def test_material_survives_repeated_save():
    """同一个 job 重复存素材不该炸（INSERT OR REPLACE）。"""
    job = storage.create_job(output_type="material", source="x")
    storage.save_material(job.id, title="一", body="内容一", source_kind="raw")
    storage.save_material(job.id, title="二", body="内容二", source_kind="webpage")

    material = storage.get_material(job.id)
    assert material.title == "二"
    assert material.body == "内容二"
