"""字幕流程不能意外下载视频；笔记保留时间、配图和来源。"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from lxml import html

from seagull_notes import media, storage


def load_script(name):
    path = Path(__file__).resolve().parents[1] / "skill" / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"skill_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def fetch():
    return load_script("fetch")


@pytest.fixture
def probe(monkeypatch):
    async def fake(*args, **kwargs):
        return {"video_id": "v1", "title": "示例", "has_subtitle": False}
    monkeypatch.setattr(media, "probe_video", fake)


def test_default_cli_disallows_asr(fetch, monkeypatch):
    got = {}
    def fake(source, **options):
        got.update(options)
        return {"ok": True, "content": "测试字幕"}
    monkeypatch.setattr(fetch, "run", fake)
    monkeypatch.setattr(sys, "argv", ["fetch.py", "https://youtu.be/v1"])
    assert fetch.main() == 0
    assert got["allow_asr"] is False
    assert got["local_browser"] is False


def test_local_collector_directly_imports_its_result(fetch, monkeypatch):
    from seagull_notes import browser_captions
    expected = {"ok": True, "content": "平台全文", "segments": [{"start": 0, "end": 6575, "text": "平台全文"}], "origin": "platform_subtitle"}
    monkeypatch.setattr(browser_captions, "collect", lambda *args, **kwargs: expected)
    monkeypatch.setattr(media, "probe_video", lambda *args, **kwargs: pytest.fail("本地采集器不应重新进入下载流程"))
    assert fetch.run("https://www.bilibili.com/video/BV1LwHv6LEYz/", allow_asr=False, language="zh", local_browser=True) == expected


def test_local_collector_cannot_silently_override_anonymous_mode(fetch):
    result = fetch.run("https://www.bilibili.com/video/BV1LwHv6LEYz/", allow_asr=False, language="zh", local_browser=True, anonymous=True)
    assert result["error"]["code"] == "conflicting_credentials"


def test_bilibili_link_automatically_uses_collector(fetch, monkeypatch):
    from seagull_notes import browser_captions
    expected = {"ok": True, "content": "完整平台字幕", "origin": "platform_subtitle"}
    got = {}
    def collect(source, **options):
        got.update(options)
        return expected
    monkeypatch.setattr(browser_captions, "collect", collect)
    result = fetch.run("https://www.bilibili.com/video/BV1LwHv6LEYz/", allow_asr=False, language="zh", refresh=True)
    assert result == expected and got["refresh"] is True


def test_explicit_anonymous_bilibili_does_not_start_collector(fetch, monkeypatch):
    from seagull_notes import browser_captions
    monkeypatch.setattr(browser_captions, "collect", lambda *args, **kwargs: pytest.fail("匿名请求不应读取专用会话"))
    monkeypatch.setattr(fetch, "_handle_video_url", lambda *args: {"ok": True, "content": "公开字幕"})
    assert fetch.run("https://www.bilibili.com/video/BV1LwHv6LEYz/", allow_asr=False, language="zh", anonymous=True)["ok"]


def test_no_tracks_still_never_downloads_video(fetch, probe, monkeypatch):
    calls = []
    async def fake(url, **options):
        calls.append(options)
        return media.MediaInfo(None, None, "示例", 60, "作者", "v1")
    monkeypatch.setattr(media, "fetch_media", fake)
    result = fetch._handle_video_url("https://youtu.be/v1", False, "zh")
    assert result["error"]["code"] == "browser_required"
    assert len(calls) == 1
    assert calls[0]["subtitle_only"] is True


def test_asr_cache_does_not_override_platform_only_request(fetch, probe, monkeypatch):
    storage.save_transcript(storage.content_key("asr:v1"), text="旧 ASR", segments=[], duration=60, origin="asr")
    async def fake(url, **options):
        return media.MediaInfo(None, "平台字幕", "示例", 60, "作者", "v1")
    monkeypatch.setattr(media, "fetch_media", fake)
    result = fetch._handle_video_url("https://youtu.be/v1", False, "zh")
    assert result["origin"] == "platform_subtitle"
    assert result["content"] == "平台字幕"


def test_anonymous_mode_does_not_use_saved_cookies(fetch, monkeypatch):
    from seagull_notes import config
    config.COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.COOKIE_FILE.write_text("test-only cookie file", encoding="utf-8")
    received = {}
    def fake(url, allow_asr, language, browser, cookie):
        received.update(browser=browser, cookie=cookie)
        return {"ok": True, "content": "匿名字幕"}
    monkeypatch.setattr(fetch, "_handle_video_url", fake)
    try:
        result = fetch.run("https://youtu.be/v1", allow_asr=False, language="zh", anonymous=True)
    finally:
        config.COOKIE_FILE.unlink()
    assert result["ok"]
    assert received == {"browser": None, "cookie": None}


def test_subtitle_failure_does_not_offer_asr_as_missing_captions(fetch, probe, monkeypatch):
    calls = []
    async def fake(url, **options):
        calls.append(options)
        if options.get("want_subtitle"):
            raise RuntimeError("subtitle requires sign-in")
        return media.MediaInfo(Path("audio.mp3"), None, "示例", 60, "作者", "v1")
    monkeypatch.setattr(media, "fetch_media", fake)
    monkeypatch.setattr(fetch, "_transcribe", lambda *args, **kwargs: {"ok": True, "origin": "asr"})
    result = fetch._handle_video_url("https://youtu.be/v1", True, "zh")
    assert result["error"]["code"] == "browser_required"
    assert len(calls) == 1 and calls[0]["subtitle_only"]


def test_existing_caption_track_without_export_cannot_fall_back_to_asr(fetch, monkeypatch):
    async def probe(*args, **kwargs):
        return {"video_id": "v1", "title": "示例", "has_subtitle": True}
    calls = []
    async def download(url, **options):
        calls.append(options)
        return media.MediaInfo(None, None, "示例", 60, "作者", "v1")
    monkeypatch.setattr(media, "probe_video", probe)
    monkeypatch.setattr(media, "fetch_media", download)
    result = fetch._handle_video_url("https://youtu.be/v1", True, "zh")
    assert result["error"]["code"] == "browser_required"
    assert len(calls) == 1 and calls[0]["subtitle_only"]


def test_platform_captions_take_priority_over_authorized_asr_cache(fetch, probe, monkeypatch):
    storage.save_transcript(storage.content_key("asr:v1"), text="旧 ASR", segments=[], duration=60, origin="asr")
    async def download(url, **options):
        return media.MediaInfo(None, "平台字幕", "示例", 60, "作者", "v1")
    monkeypatch.setattr(media, "fetch_media", download)
    result = fetch._handle_video_url("https://youtu.be/v1", True, "zh")
    assert result["origin"] == "platform_subtitle"
    assert result["content"] == "平台字幕"


def test_subtitle_cache_retains_timestamps(fetch, probe, monkeypatch):
    segments = [{"start": 42, "end": 45, "text": "关键内容"}]
    async def fake(url, **options):
        return media.MediaInfo(None, "关键内容", "示例", 60, "作者", "v1", segments)
    monkeypatch.setattr(media, "fetch_media", fake)
    first = fetch._handle_video_url("https://youtu.be/v1", False, "zh")
    async def unexpected(*args, **kwargs):
        pytest.fail("缓存命中后不应再次下载")
    monkeypatch.setattr(media, "fetch_media", unexpected)
    second = fetch._handle_video_url("https://youtu.be/v1", False, "zh")
    assert first["segments"] == second["segments"] == segments


def test_local_asr_and_cache_return_identical_timestamps(fetch, tmp_path, monkeypatch):
    from seagull_notes import asr
    audio = tmp_path / "speech.wav"
    audio.write_bytes(b"local test input")
    segments = [{"start": 0.0, "end": 2.5, "text": "本地内容"}]
    async def fake(*args, **kwargs):
        return asr.Transcript("本地内容", segments, 2.5, "zh", "asr")
    monkeypatch.setattr(asr, "model_is_cached", lambda: True)
    monkeypatch.setattr(asr, "transcribe", fake)
    first = fetch._handle_media_file(audio, True, "zh")
    async def unexpected(*args, **kwargs):
        pytest.fail("第二次读取应使用缓存")
    monkeypatch.setattr(asr, "transcribe", unexpected)
    cached = fetch._handle_media_file(audio, True, "zh")
    assert first["segments"] == cached["segments"] == segments


def test_local_source_is_identified_without_fake_video_links(tmp_path):
    source = tmp_path / "speech.wav"
    source.write_bytes(b"local test input")
    page, body = load_script("notebook").render_note({
        "title": "本地笔记", "source_ref": str(source),
        "sections": [{"title": "章节", "start": 2, "markdown": "正文"}],
    }, tmp_path)
    doc = html.fromstring(page)
    assert "speech.wav" in doc.text_content()
    assert not doc.xpath('//a[@class="time"]')
    assert "00:02" in doc.text_content() and "00:02" in body
    assert str(source) in body


def test_model_cache_requires_complete_snapshot(tmp_path, monkeypatch):
    from seagull_notes import asr, config
    monkeypatch.setattr(config, "HF_HUB_CACHE", tmp_path)
    snapshot = tmp_path / f"models--Systran--faster-whisper-{config.ASR_MODEL}" / "snapshots" / "test-revision"
    snapshot.mkdir(parents=True)
    assert asr.model_is_cached() is False
    for name in ("model.bin", "config.json", "tokenizer.json", "vocabulary.json"):
        (snapshot / name).write_bytes(b"complete test fixture")
    assert asr.model_is_cached() is True


def test_explicit_asr_downloads_only_after_subtitle_attempt(fetch, probe, monkeypatch):
    calls = []
    async def fake(url, **options):
        calls.append(options)
        return media.MediaInfo(Path("audio.mp3"), None, "示例", 60, "作者", "v1")
    monkeypatch.setattr(media, "fetch_media", fake)
    monkeypatch.setattr(fetch, "_transcribe", lambda *args, **kwargs: {"ok": True})
    assert fetch._handle_video_url("https://youtu.be/v1", True, "zh")["ok"]
    assert calls[0]["subtitle_only"] is True
    assert calls[1]["want_subtitle"] is False
    assert calls[1]["audio_only"] is True


@pytest.mark.parametrize("suffix,raw", [
    (".srt", "1\n00:00:42,000 --> 00:00:45,500\n关键内容\n"),
    (".vtt", "WEBVTT\n\n00:42.000 --> 00:45.500 align:start\n<c>关键内容</c>\n"),
    (".json3", json.dumps({"events": [{"tStartMs": 42000, "dDurationMs": 3500, "segs": [{"utf8": "关键内容"}]}]})),
])
def test_timed_captions(tmp_path, suffix, raw):
    path = tmp_path / f"captions{suffix}"
    path.write_text(raw, encoding="utf-8")
    assert media.parse_subtitle_segments(path) == [{"start": 42, "end": 45.5, "text": "关键内容"}]


def test_illustrated_note_has_real_image_timestamps_and_text(tmp_path):
    notebook = load_script("notebook")
    (tmp_path / "frame.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"><text>示意图</text></svg>', encoding="utf-8")
    note = {"title": "示例", "source_url": "https://www.bilibili.com/video/BV1/?p=2", "summary": "概览", "sections": [
        {"title": "章节", "start": 42, "markdown": "**关键内容**\n\n> 引用\n\n<script>alert(1)</script>\n\n[恶意链接](javascript:alert(1))", "image": {"path": "frame.svg", "caption": "字幕示意图"}}
    ], "transcript": "完整原文", "mind_map": [{"title": "主题"}]}
    page, body = notebook.render_note(note, tmp_path)
    doc = html.fromstring(page)
    assert doc.xpath('//figure//img')[0].get("src").startswith("data:image/svg+xml;base64,")
    assert doc.xpath('//a[@class="time"]')[0].get("href").endswith("p=2&t=42")
    assert doc.xpath('//blockquote')
    assert all('alert(1)' not in (script.text or '') for script in doc.xpath('//script'))
    assert not doc.xpath('//a[starts-with(@href,"javascript:")]')
    assert "完整原文" in doc.xpath('//*[@id="transcript"]')[0].text_content()
    assert str((tmp_path / "frame.svg").as_posix()) in body


@pytest.mark.parametrize("text,expected", [
    ("```text\n<<<<<<< HEAD\n当前分支\n=======\n合入分支\n>>>>>>> feature/example\n```", "<<<<<<< HEAD\n当前分支\n=======\n合入分支\n>>>>>>> feature/example\n"),
    ("```html\n<script>alert(1)</script> &lt; & value\n```", "<script>alert(1)</script> &lt; & value\n"),
    ("`a < b && c > d`", "a < b && c > d"),
])
def test_code_preserves_source_characters(text, expected):
    doc = html.fromstring(load_script("notebook").rich_text(text))
    assert doc.xpath('//code')[0].text_content() == expected
    assert not doc.xpath('//script|//img')


@pytest.mark.parametrize("language,label,source", [
    ("python", "Python", 'for i in range(5):\n    print("Hello World", i)\n'),
    ("java", "Java", 'public class Main { public static void main(String[] args) {} }\n'),
    ("cpp", "C++", '#include <iostream>\nint main() { return 0; }\n'),
    ("bash", "Bash", 'git commit -m "添加按钮"\ngit status\n'),
    ("bash", "Bash", 'git status\n'),
])
def test_fenced_code_has_language_highlighting_and_copy_button(language, label, source):
    doc = html.fromstring(load_script("notebook").rich_text(f"```{language}\n{source}```"))
    block = doc.xpath('//div[@class="code-block"]')[0]
    assert block.xpath('.//span[@class="code-language"]')[0].text_content() == label
    assert block.xpath('.//button[@class="copy-code"]')[0].get("aria-label") == f"复制 {label} 代码"
    assert block.xpath('.//button[@class="wrap-code"]')[0].get("aria-pressed") == "false"
    assert block.xpath('.//pre/code')[0].text_content() == source
    assert any(span.text_content().strip() for span in block.xpath('.//pre/code/span[@class]'))


def test_unknown_code_language_remains_copyable_plain_text():
    source = "<unknown> &lt; & value\n"
    doc = html.fromstring(load_script("notebook").rich_text(f"```unknown-language\n{source}```"))
    assert doc.xpath('//pre/code')[0].text_content() == source
    assert doc.xpath('//button[@class="copy-code"]')
    assert not doc.xpath('//unknown')


def test_long_notes_have_searchable_directory_and_reading_navigation(tmp_path):
    page, _ = load_script("notebook").render_note({
        "title": "长课", "source_url": "https://youtu.be/v1",
        "sections": [{"title": "回滚", "markdown": "正文"}, {"title": "分支", "markdown": "正文"}],
    }, tmp_path)
    doc = html.fromstring(page)
    assert doc.xpath('//input[@id="toc-search"]')[0].get("aria-label") == "搜索章节"
    assert doc.xpath('//*[@id="toc-toggle"]')[0].get("aria-controls") == "toc-panel"
    assert doc.xpath('//progress[@id="reading-progress"]')[0].get("max") == "2"
    assert doc.xpath('//*[@id="prev-chapter"]')[0].get("aria-label") == "上一章"
    assert doc.xpath('//*[@id="next-chapter"]')[0].get("aria-label") == "下一章"
    assert doc.xpath('//a[@class="skip-link"]')[0].get("href") == "#notes"


def test_missing_timestamps_are_not_invented(tmp_path):
    page, _ = load_script("notebook").render_note({"title": "示例", "source_url": "https://youtu.be/v1", "sections": [{"title": "章节", "markdown": "正文"}]}, tmp_path)
    assert not html.fromstring(page).xpath('//a[@class="time"]')


def test_cover_and_takeaways_survive_both_formats(tmp_path):
    (tmp_path / "cover.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")
    page, body = load_script("notebook").render_note({
        "title": "标题", "subtitle": "副标题", "source_url": "https://youtu.be/v1",
        "takeaways": ["关键收获"], "cover": {"path": "cover.svg", "caption": "已核实画面"},
        "sections": [{"title": "章节", "markdown": "正文"}],
    }, tmp_path)
    doc = html.fromstring(page)
    assert doc.xpath('//figure[@class="cover"]//img')[0].get("src").startswith("data:image/svg+xml;base64,")
    assert "关键收获" in doc.xpath('//div[@class="takeaways"]')[0].text_content()
    assert "已核实画面" in body and "关键收获" in body


def test_missing_image_reports_failure(tmp_path, monkeypatch, capsys):
    notebook = load_script("notebook")
    path = tmp_path / "note.json"
    path.write_text(json.dumps({"title": "示例", "source_url": "https://youtu.be/v1", "sections": [{"title": "章节", "markdown": "正文", "image": {"path": "missing.png"}}]}), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["notebook.py", str(path)])
    assert notebook.main() == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_source_cannot_be_javascript(tmp_path):
    with pytest.raises(ValueError, match="http/https"):
        load_script("notebook").render_note({"title": "示例", "source_url": "javascript:alert(1)", "sections": []}, tmp_path)
