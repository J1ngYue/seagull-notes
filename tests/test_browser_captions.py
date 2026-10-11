"""Caption collection keeps login conditional, full timing and local exports."""

import json
import sys
from contextlib import nullcontext
from pathlib import Path
from types import ModuleType

import pytest

from seagull_notes import browser_captions as captions, media

VIDEO = "https://www.bilibili.com/video/BV1LwHv6LEYz/"


@pytest.mark.parametrize("url", [
    "https://bilibili.com.example.org/video/BV1LwHv6LEYz/",
    "file:///video/BV1LwHv6LEYz/", VIDEO + "?p=0", VIDEO + "?p=bad",
])
def test_collector_rejects_invalid_sources(url):
    with pytest.raises(captions.CaptionError):
        captions.video_target(url)


def test_video_target_preserves_part_and_removes_tracking():
    source, bvid, part = captions.video_target(VIDEO + "?p=2&vd_source=tracking")
    assert part == 2 and bvid == "BV1LwHv6LEYz"
    assert source == VIDEO + "?p=2"


@pytest.mark.parametrize("url", ["http://aisubtitle.hdslb.com/file.json", "https://hdslb.com.example.org/file.json", "file:///captions.json"])
def test_caption_download_stays_on_platform_https_hosts(url):
    with pytest.raises(captions.CaptionError, match="HTTPS"):
        captions.caption_url(url)


@pytest.mark.parametrize("row", [
    {"from": -1, "to": 2, "content": "x"}, {"from": 2, "to": 1, "content": "x"},
    {"from": float("nan"), "to": 3, "content": "x"}, {"from": 0, "content": "x"},
    {"from": 0, "to": 1, "content": None},
])
def test_invalid_time_axis_is_not_silently_imported(row):
    with pytest.raises(captions.CaptionError):
        captions.parse_captions({"body": [row]})


def test_metadata_or_settings_response_is_not_imported_as_subtitles():
    with pytest.raises(captions.CaptionError):
        captions.parse_captions({"font_size": 1})


def sample():
    return {"ok": True, "title": "示例", "video_id": "BV1LwHv6LEYz", "part": 2, "cid": 22,
            "content": "第一句\n最后一句", "segments": [{"start": 0.25, "end": 1.5, "text": "第一句"},
            {"start": 6570, "end": 6575.75, "text": "最后一句"}], "duration": 6576,
            "origin": "platform_subtitle", "caption_language": "ai-zh"}


def test_download_uses_current_part_and_preserves_full_timeline(monkeypatch):
    calls = []
    def response(context, endpoint, params=None):
        calls.append((endpoint, params))
        if endpoint.endswith("/view"):
            return {"data": {"aid": 1, "title": "课程", "owner": {"name": "作者"}, "pages": [
                {"cid": 11, "part": "第一集", "duration": 20}, {"cid": 22, "part": "第二集", "duration": 6576}]}}
        if endpoint.endswith("/v2"):
            return {"data": {"subtitle": {"subtitles": [
                {"lan": "ai-en", "subtitle_url": "//aisubtitle.hdslb.com/english.json"},
                {"lan": "ai-zh", "subtitle_url": "//aisubtitle.hdslb.com/chinese.json"}]}}}
        return {"body": [{"from": s["start"], "to": s["end"], "content": s["text"]} for s in sample()["segments"]]}
    monkeypatch.setattr(captions, "_json", response)
    result = captions._read(object(), VIDEO + "?p=2", "BV1LwHv6LEYz", 2, "zh")
    assert calls[1][1] == {"aid": 1, "cid": 22}
    assert calls[2][0].endswith("chinese.json")
    assert result["segments"] == sample()["segments"]
    assert result["coverage"]["last_end"] == 6575.75
    assert result["origin"] == "platform_subtitle" and result["caption_language"] == "ai-zh"
    assert not any("playurl" in endpoint for endpoint, _ in calls)


def test_saved_srt_can_be_imported_without_manual_conversion():
    result = captions.save_captions(sample())
    assert media.parse_subtitle_segments(Path(result["subtitle_file"])) == result["segments"]
    saved = json.loads(Path(result["caption_file"]).read_text(encoding="utf-8"))
    assert saved["content"] == result["content"] and saved["part"] == 2


@pytest.fixture
def browser(monkeypatch):
    module = ModuleType("playwright.sync_api")
    module.sync_playwright = lambda: nullcontext(object())
    module.Error = type("PlaywrightError", (Exception,), {})
    monkeypatch.setitem(sys.modules, "playwright.sync_api", module)
    launches = []
    class Context:
        def close(self):
            pass
    monkeypatch.setattr(captions, "_launch", lambda playwright, headed: launches.append(headed) or Context())
    return launches


def test_existing_valid_session_never_opens_login(browser, monkeypatch):
    monkeypatch.setattr(captions, "_read", lambda *args: sample())
    monkeypatch.setattr(captions, "_wait_for_login", lambda *args: pytest.fail("已有登录时不应交接登录"))
    assert captions.collect(VIDEO)["ok"]
    assert browser == [False]


def test_expired_session_opens_login_once_then_automatically_imports(browser, monkeypatch):
    reads = iter([captions.CaptionError("login_required", "expired"), sample()])
    waits = []
    def read(*args):
        result = next(reads)
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr(captions, "_read", read)
    monkeypatch.setattr(captions, "_wait_for_login", lambda *args: waits.append(True))
    assert captions.collect(VIDEO)["ok"]
    assert browser == [False, True] and len(waits) == 1


def test_a_window_that_is_already_signed_in_does_not_show_prompt(monkeypatch):
    class Page:
        def goto(self, *args, **kwargs):
            pass
    class Context:
        pages = [Page()]
    monkeypatch.setattr(captions, "_logged_in", lambda context: True)
    captions._wait_for_login(Context(), 1, lambda message: pytest.fail("已登录窗口不应显示登录提示"))


def test_noninteractive_run_does_not_open_login(browser, monkeypatch):
    def read(*args):
        raise captions.CaptionError("login_required", "expired")
    monkeypatch.setattr(captions, "_read", read)
    with pytest.raises(captions.CaptionError, match="expired"):
        captions.collect(VIDEO, allow_login=False)
    assert browser == [False]
