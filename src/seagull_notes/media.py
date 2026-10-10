"""媒体获取：下载视频/音频，优先抢平台自带字幕。

顺序参照 CuteNote 的管线：
    fetch_transcript（有字幕）> media_download_and_transcribe（没字幕才跑 ASR）
字幕优先是核心优化——省时间且比 ASR 准。
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import config

VIDEO_HOSTS = (
    "youtube.com", "youtu.be", "bilibili.com", "b23.tv",
    "vimeo.com", "twitter.com", "x.com", "tiktok.com", "douyin.com",
)


@dataclass
class MediaInfo:
    """下载结果。subtitle 有值就说明拿到了平台字幕，不必跑 ASR。"""
    media_path: Path | None
    subtitle_text: str | None
    title: str
    duration: float
    uploader: str
    video_id: str
    subtitle_segments: list[dict] = field(default_factory=list)


def is_video_url(url: str) -> bool:
    lowered = url.lower()
    return any(host in lowered for host in VIDEO_HOSTS)


# --------------------------------------------------------------------- 字幕解析

def _parse_srt(raw: str) -> str:
    """SRT → 纯文本。去掉序号行和时间轴行。"""
    out: list[str] = []
    for block in re.split(r"\n\s*\n", raw.strip()):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        if len(lines) >= 3 and "-->" in lines[1]:
            out.append(" ".join(lines[2:]))
        elif len(lines) == 2 and "-->" in lines[0]:
            out.append(lines[1])
    return " ".join(out).strip()


def _parse_vtt(raw: str) -> str:
    """WebVTT → 纯文本。"""
    out: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")):
            continue
        if "-->" in line or line.isdigit():
            continue
        line = re.sub(r"<[^>]+>", "", line)   # 去掉 <c> 之类的标签
        if line:
            out.append(line)
    # VTT 有滚屏重复行，按出现顺序去重相邻重复
    deduped: list[str] = []
    for line in out:
        if not deduped or deduped[-1] != line:
            deduped.append(line)
    return " ".join(deduped).strip()


def _parse_json3(raw: str) -> str:
    """YouTube json3 字幕格式 → 纯文本。"""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    parts: list[str] = []
    for event in data.get("events", []):
        for seg in event.get("segs", []) or []:
            text = seg.get("utf8", "")
            if text and text != "\n":
                parts.append(text)
    return "".join(parts).strip()


def parse_subtitle_file(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    suffix = path.suffix.lower()
    if suffix == ".srt":
        return _parse_srt(raw)
    if suffix == ".vtt":
        return _parse_vtt(raw)
    if ".json3" in path.name.lower():
        return _parse_json3(raw)
    return raw.strip()


def parse_subtitle_segments(path: Path) -> list[dict]:
    """保留 SRT/VTT/json3 的时间轴，供章节定位和配图使用。"""
    raw = path.read_text(encoding="utf-8-sig", errors="replace")
    if path.suffix.lower() == ".json3":
        events = json.loads(raw).get("events", [])
        return [
            {"start": e.get("tStartMs", 0) / 1000,
             "end": (e.get("tStartMs", 0) + e.get("dDurationMs", 0)) / 1000,
             "text": "".join(s.get("utf8", "") for s in e.get("segs") or []).strip()}
            for e in events if any(s.get("utf8", "").strip() for s in e.get("segs") or [])
        ]
    if path.suffix.lower() not in {".srt", ".vtt"}:
        return []
    timestamp = r"(?:\d+:)?\d{2}:\d{2}[.,]\d{3}"
    cue = re.compile(rf"({timestamp})\s*-->\s*({timestamp})[^\n]*\n(.*?)(?=\n\s*\n|\Z)", re.S)

    def seconds(value: str) -> float:
        parts = value.replace(",", ".").split(":")
        return sum(float(part) * 60 ** i for i, part in enumerate(reversed(parts)))

    segments = []
    for match in cue.finditer(raw):
        text = re.sub(r"<[^>]+>", "", match[3]).strip().replace("\n", " ")
        if text:
            segments.append({"start": seconds(match[1]), "end": seconds(match[2]), "text": text})
    return segments


# ------------------------------------------------------------------------ 下载

def _apply_direct_bind(opts: dict[str, Any], url: str) -> str | None:
    """国内站点强制直连，绕开 TUN 代理。

    开着 Clash 之类的全局代理时，B站 看到的是境外机房 IP，会直接 412 风控。
    绑定到物理网卡地址就能让这次请求走真实出口。
    """
    if not config.needs_direct(url):
        return None
    bind_ip = config.find_physical_ip()
    if not bind_ip:
        return None
    opts["source_address"] = bind_ip
    return bind_ip


def _apply_cookies(opts: dict[str, Any], cookies_from_browser: str | None = None,
                   cookie_file: str | None = None) -> None:
    """给 yt-dlp 加 cookies。

    B站的 AI 字幕、会员视频、需要登录的内容都得带 cookies 才拿得到。
    """
    if cookie_file:
        opts["cookiefile"] = cookie_file
    elif cookies_from_browser:
        # yt-dlp 期望元组形式：(浏览器名, 配置文件, 钥匙串, 容器)
        browser = cookies_from_browser.strip().lower()
        opts["cookiesfrombrowser"] = (browser, None, None, None)


def _download_sync(url: str, *, want_subtitle: bool = True, audio_only: bool = False,
                   subtitle_only: bool = False,
                   cookies_from_browser: str | None = None,
                   cookie_file: str | None = None) -> MediaInfo:
    """阻塞式下载。调用方负责丢进线程池。

    subtitle_only=True 时只抓字幕文件，不下载媒体本体——省流量省时间。
    """
    import yt_dlp

    config.ensure_dirs()
    out_dir = config.MEDIA_DIR / "%(id)s"
    outtmpl = str(out_dir / ("audio.%(ext)s" if audio_only else "media.%(ext)s"))

    opts: dict[str, Any] = {
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "retries": 3,
        "socket_timeout": 30,
    }
    _apply_cookies(opts, cookies_from_browser, cookie_file)
    bound = _apply_direct_bind(opts, url)
    if bound:
        print(f"[seagull] 国内站点，绑定 {bound} 直连（绕开代理）", file=__import__("sys").stderr)

    if want_subtitle:
        opts.update({
            "writesubtitles": True,
            "writeautomaticsub": True,
            # 中文优先，然后英文；bilibili 常见 ai-zh，YouTube 常见 zh-Hans
            "subtitleslangs": ["zh-Hans", "zh-CN", "zh", "zh-Hant", "ai-zh", "en"],
            "subtitlesformat": "srt/vtt/best",
        })

    if subtitle_only:
        # 只要字幕，别下视频
        opts["skip_download"] = True
    else:
        opts["skip_download"] = False

    if audio_only and not subtitle_only:
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "128",
        }]

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)

    video_id = info.get("id", "unknown")
    video_dir = config.MEDIA_DIR / video_id

    subtitle_text: str | None = None
    subtitle_segments: list[dict] = []
    if want_subtitle:
        for sub_path in sorted(video_dir.glob("*.srt")) + sorted(video_dir.glob("*.vtt")):
            parsed = parse_subtitle_file(sub_path)
            if parsed:
                subtitle_text = parsed
                subtitle_segments = parse_subtitle_segments(sub_path)
                break

    media_path: Path | None = None
    for pattern in ("audio.mp3", "media.*"):
        found = sorted(video_dir.glob(pattern))
        if found:
            media_path = found[0]
            break

    return MediaInfo(
        media_path=media_path,
        subtitle_text=subtitle_text,
        title=info.get("title") or video_id,
        duration=float(info.get("duration") or 0.0),
        uploader=info.get("uploader") or "",
        video_id=video_id,
        subtitle_segments=subtitle_segments,
    )


async def fetch_media(url: str, *, want_subtitle: bool = True, audio_only: bool = False,
                      subtitle_only: bool = False,
                      cookies_from_browser: str | None = None,
                      cookie_file: str | None = None) -> MediaInfo:
    """异步包装：yt-dlp 是阻塞的，丢线程池跑。"""
    return await asyncio.to_thread(
        _download_sync, url,
        want_subtitle=want_subtitle, audio_only=audio_only,
        subtitle_only=subtitle_only,
        cookies_from_browser=cookies_from_browser, cookie_file=cookie_file,
    )


def _probe_sync(url: str, *, cookies_from_browser: str | None = None,
                cookie_file: str | None = None) -> dict[str, Any]:
    """只取元数据，不下载任何东西。用来先拿 video_id 查缓存。"""
    import yt_dlp

    opts: dict[str, Any] = {
        "quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True,
    }
    _apply_cookies(opts, cookies_from_browser, cookie_file)
    _apply_direct_bind(opts, url)

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    manual = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}
    return {
        "video_id": info.get("id", ""),
        "title": info.get("title") or "",
        "duration": float(info.get("duration") or 0.0),
        "uploader": info.get("uploader") or "",
        "has_subtitle": bool(manual or auto),
        "subtitle_langs": sorted({*manual.keys(), *auto.keys()})[:12],
    }


async def probe_video(url: str, *, cookies_from_browser: str | None = None,
                      cookie_file: str | None = None) -> dict[str, Any]:
    """探测视频元数据，不下载。用于查缓存、快速判断有没有字幕。"""
    return await asyncio.to_thread(
        _probe_sync, url,
        cookies_from_browser=cookies_from_browser, cookie_file=cookie_file,
    )
