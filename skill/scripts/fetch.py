#!/usr/bin/env python3
"""抓取素材：视频 / 网页 / PDF / 文本 → JSON。

这是 seagull-notes skill 的取数脚本。它只负责"把内容弄到手"，
整理成笔记是 Codex 的活。

用法：
    python fetch.py "<url 或文件路径或文本>"
    python fetch.py "<url>" --offset 30000 --max-chars 30000
    python fetch.py "<url>" --no-asr          # 禁用 ASR，只吃平台字幕
    python fetch.py "<file>" --format text    # 纯文本输出，不包 JSON

输出 JSON 到 stdout，日志到 stderr。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

# ------------------------------------------------------------------ 环境自举

PROJECT_HOME = Path(os.environ.get("SEAGULL_NOTES_HOME", str(Path(__file__).resolve().parents[2])))
SRC_DIR = PROJECT_HOME / "src"

_REQUIRED = ("httpx", "lxml", "yt_dlp")


def _deps_present() -> bool:
    import importlib.util

    return all(importlib.util.find_spec(m) is not None for m in _REQUIRED)


def _bootstrap() -> None:
    """检查当前解释器依赖并加载项目源码，不切换 Python 运行时。"""
    if str(SRC_DIR) not in sys.path and SRC_DIR.is_dir():
        sys.path.insert(0, str(SRC_DIR))

    if _deps_present():
        return

    print(
        "错误：当前 Python 解释器缺少依赖。\n"
        f"  缺的包: {', '.join(m for m in _REQUIRED if __import__('importlib.util').util.find_spec(m) is None)}\n"
        "  装依赖见 references/setup.md",
        file=sys.stderr,
    )
    raise SystemExit(2)


_bootstrap()


def _force_utf8() -> None:
    """Windows 控制台默认是 ANSI 代码页，中文输出会乱码。

    注意：批处理调用时必须设 PYTHONIOENCODING=utf-8，或者用同目录的 fetch.cmd
    包装器。这个函数处理的是 Python 侧。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


_force_utf8()

# ------------------------------------------------------------------ 主逻辑


def _emit(payload: dict) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def _log(message: str) -> None:
    print(f"[seagull] {message}", file=sys.stderr, flush=True)


def _ok(title: str, content: str, source_kind: str, ref: str, **extra) -> dict:
    payload = {
        "ok": True,
        "title": title,
        "source_kind": source_kind,
        "source_ref": ref,
        "content": content,
        "char_count": len(content),
    }
    payload.update(extra)
    return payload


def _err(code: str, message: str, hint: str = "") -> dict:
    payload = {"ok": False, "error": {"code": code, "message": message}}
    if hint:
        payload["error"]["hint"] = hint
    return payload


def run(source: str, *, allow_asr: bool, language: str,
        cookies_from_browser: str | None = None,
        cookie_file: str | None = None, anonymous: bool = False,
        local_browser: bool = False, refresh: bool = False) -> dict:
    from seagull_notes import config, extract, media
    from seagull_notes.pipeline import URL_RE, _looks_like_path

    if not local_browser and not (anonymous or cookies_from_browser or cookie_file):
        parsed = urlparse(source)
        host = (parsed.hostname or "").lower()
        local_browser = (parsed.scheme in ("http", "https") and parsed.path.startswith("/video/BV")
                         and (host == "bilibili.com" or host.endswith(".bilibili.com")))
    if local_browser:
        if anonymous or cookies_from_browser or cookie_file:
            return _err("conflicting_credentials", "本地专用浏览器不能与匿名模式或其他 Cookie 来源同时使用。")
        from seagull_notes.browser_captions import CaptionError, collect
        try:
            return collect(source, language=language, refresh=refresh, log=_log)
        except CaptionError as exc:
            return _err(exc.code, str(exc))

    # 没显式指定 cookies 时，自动用之前导出好的那份
    if anonymous:
        cookies_from_browser = cookie_file = None
    elif not cookies_from_browser and not cookie_file and config.COOKIE_FILE.exists():
        cookie_file = str(config.COOKIE_FILE)
        _log(f"自动使用已导出的 cookies：{config.COOKIE_FILE}")

    # --- 本地文件 ---
    if not URL_RE.match(source):
        path = Path(source)
        if path.exists():
            kind = extract.classify_local_file(path)
            if kind == "media":
                return _handle_media_file(path, allow_asr, language)
            if kind == "pdf":
                _log("抽取 PDF 文本")
                doc = extract.extract_pdf(path)
                return _ok(doc.title, doc.text, "pdf", str(path))
            if kind == "subtitle":
                _log("解析字幕文件（不需要 ASR）")
                doc = extract.extract_subtitle_file(path)
                if not doc.text.strip():
                    return _err("empty_subtitle", f"字幕文件没解析出内容：{path}",
                                "确认文件格式是 .srt / .vtt / .ass / .json3")
                return _ok(doc.title, doc.text, "subtitle", str(path),
                           origin="subtitle_file",
                           segments=media.parse_subtitle_segments(path),
                           note="来自字幕文件，没有跑 ASR")
            doc = extract.extract_local_text(path)
            return _ok(doc.title, doc.text, "text", str(path))

        if _looks_like_path(source):
            return _err("file_not_found", f"文件不存在：{source}")

        # 看着不像路径 → 当成直接粘贴的文本
        _log("收到的是文本，直接透传")
        from seagull_notes.pipeline import _guess_title

        return _ok(_guess_title(source), source.strip(), "text", "inline")

    # --- URL ---
    if media.is_video_url(source):
        return _handle_video_url(source, allow_asr, language,
                                 cookies_from_browser, cookie_file)

    _log("抓取网页正文")
    return _run_async(_handle_web(source))


async def _handle_web(url: str) -> dict:
    from seagull_notes import extract

    try:
        doc = await extract.extract_url(url)
    except Exception as exc:                                    # noqa: BLE001
        name = type(exc).__name__
        if "403" in str(exc):
            return _err("blocked_403", f"站点拒绝访问（403）：{url}",
                        "该站有反爬。让用户把正文直接粘贴过来。")
        if "JavaScript" in str(exc):
            return _err("js_rendered", str(exc),
                        "页面靠 JS 渲染，静态抓不到。让用户粘贴正文。")
        return _err(name, str(exc)[:300])

    if not doc.text.strip():
        return _err("empty_content", f"没抽到正文：{url}",
                    "可能是纯 JS 渲染的页面。让用户粘贴正文。")
    return _ok(doc.title, doc.text, "webpage", url)


def _handle_video_url(url: str, allow_asr: bool, language: str,
                      cookies_from_browser: str | None = None,
                      cookie_file: str | None = None) -> dict:
    from seagull_notes import media, storage

    # 先探元数据（不下载），拿 video_id 查缓存
    _log("探测视频信息（不下载）")
    try:
        meta = _run_async(media.probe_video(
            url, cookies_from_browser=cookies_from_browser, cookie_file=cookie_file,
        ))
    except Exception as exc:                                    # noqa: BLE001
        name = type(exc).__name__
        message = str(exc)[:300]
        lowered = message.lower()

        needs_login = any(k in lowered for k in (
            "login", "cookie", "sign in", "412", "precondition failed",
            "not a bot", "会员", "登录",
        ))

        if needs_login:
            hint = "打开原视频，先复用已有登录态并检查完整字幕；确认当前会话失效时才交接登录。登录不保证解除平台风控。"
        else:
            hint = "取视频信息失败。检查链接是否有效。"

        return _err("browser_required" if needs_login else name, message, hint)

    video_id = meta.get("video_id") or url
    title = meta.get("title") or video_id

    cached = storage.get_transcript(storage.content_key(f"subtitle:{video_id}"))
    if not cached and allow_asr:
        cached = storage.get_transcript(storage.content_key(f"asr:{video_id}"))
    if cached:
        _log("命中转写缓存，跳过下载和 ASR")
        return _ok(title, cached["text"], "media", url,
                   origin=cached["origin"], duration=cached["duration"],
                   uploader=meta.get("uploader", ""),
                   segments=cached["segments"],
                   note="来自本地缓存，没有重新下载")

    _log(f"下载视频字幕：{title}")

    # 探测阶段已经知道有没有字幕轨 —— 有就只抓字幕，不下视频本体
    has_subtitle = bool(meta.get("has_subtitle"))
    if has_subtitle:
        _log("探到字幕轨，只抓字幕文件（不下载视频）")

    try:
        info = _run_async(media.fetch_media(
            url, want_subtitle=True,
            subtitle_only=True,
            cookies_from_browser=cookies_from_browser, cookie_file=cookie_file,
        ))
    except Exception as exc:                                    # noqa: BLE001
        if not allow_asr:
            return _err("browser_required", str(exc)[:300],
                        "字幕获取失败。打开内置浏览器检查原视频、登录要求和字幕列表。")
        _log("字幕获取失败；已显式允许 ASR，继续尝试可访问音频")
        info = None

    # 平台字幕优先
    if info and info.subtitle_text:
        _log("命中平台字幕，跳过 ASR")
        key = storage.content_key(f"subtitle:{video_id}")
        try:
            storage.save_transcript(
                key, text=info.subtitle_text, segments=info.subtitle_segments,
                duration=info.duration, origin="platform_subtitle",
            )
        except Exception as exc:                                # noqa: BLE001
            _log(f"缓存写入失败（不影响结果）：{exc}")
        return _ok(
            info.title, info.subtitle_text, "media", url,
            origin="platform_subtitle", duration=info.duration, uploader=info.uploader,
            segments=info.subtitle_segments,
            note="用的是平台自带字幕，没跑模型",
        )

    if not allow_asr:
        return _err("browser_required", f"未取得平台字幕：{url}",
                    "这不等于视频没有字幕。打开内置浏览器，先复用已有登录态检查完整字幕；确认需要重新认证时才交接登录。")

    # 只有显式允许 ASR、且字幕确实未取得时，才下载音频。
    try:
        info = _run_async(media.fetch_media(
            url, want_subtitle=False, audio_only=True,
            cookies_from_browser=cookies_from_browser, cookie_file=cookie_file,
        ))
    except Exception as exc:
        return _err("download_failed", str(exc)[:300])

    if info.media_path is None:
        return _err("download_failed", "没拿到媒体文件")

    return _transcribe(info.media_path, info.title, url, language,
                       cache_key=storage.content_key(f"asr:{video_id}"),
                       duration=info.duration, uploader=info.uploader)


def _handle_media_file(path: Path, allow_asr: bool, language: str) -> dict:
    from seagull_notes import storage

    if not allow_asr:
        return _err("asr_disabled", f"本地音视频文件需要 ASR，但被禁用了：{path}")

    # 用 路径+修改时间 做缓存键：文件没变就复用上次的转写
    key = storage.content_key(f"{path.resolve()}:{path.stat().st_mtime_ns}")
    return _transcribe(path, path.stem, str(path), language, cache_key=key)


def _transcribe(path: Path, title: str, ref: str, language: str,
                cache_key: str | None = None, **extra) -> dict:
    from seagull_notes import asr, config, storage

    # 转写很贵，先查缓存。同一个视频第二次处理几乎秒出。
    if cache_key:
        cached = storage.get_transcript(cache_key)
        if cached:
            _log("命中转写缓存，跳过 ASR")
            return _ok(
                title, cached["text"], "media", ref,
                origin=cached["origin"], duration=cached["duration"],
                segments=cached["segments"], **extra,
            )

    if not asr.model_is_cached():
        _log(f"ASR 模型 {config.ASR_MODEL} 还没下载")
        return _err(
            "model_missing",
            f"本地没有 ASR 模型 {config.ASR_MODEL}",
            f"安装 ASR 可选依赖后下载模型（约 3 GB）：{sys.executable} -m seagull_notes.cli prepare-model",
        )

    _log(f"跑 ASR（{config.ASR_MODEL} / {config.ASR_DEVICE}）……这步可能要几分钟")
    try:
        result = _run_async(asr.transcribe(path, language=language))
    except Exception as exc:                                    # noqa: BLE001
        return _err(type(exc).__name__, str(exc)[:300],
                    "ASR 失败。检查显卡驱动和 CUDA 库，见 references/setup.md")

    _log(f"转写完成，{len(result.text)} 字符")

    if not result.text.strip():
        return _err(
            "empty_transcript",
            f"ASR 跑完了但没识别出任何内容：{ref}",
            "可能这个视频没有音轨，或者全程是纯音乐/静音。"
            "确认视频里有人说话，或者换一个有字幕的源。",
        )

    if cache_key:
        try:
            storage.save_transcript(
                cache_key, text=result.text, segments=result.segments,
                duration=result.duration, origin="asr",
            )
        except Exception as exc:                                # noqa: BLE001
            _log(f"缓存写入失败（不影响结果）：{exc}")

    # extra 里可能已经有 duration / uploader，别重复传
    payload = dict(extra)
    payload.setdefault("duration", result.duration)
    payload.setdefault("language", result.language)
    payload["asr_pass"] = result.pass_used
    payload["segments"] = result.segments

    if result.pass_used == "hallucination_suspected":
        payload["warning"] = (
            "识别结果疑似复读幻觉——这类音频通常没有清晰人声（纯音乐、"
            "强背景音）。写笔记前请核对内容是否通顺，不通顺就告诉用户"
            "这个源不适合做笔记。"
        )
    elif result.pass_used == "retry_no_context":
        payload["warning"] = (
            "第一次识别出现复读，已用抗复读参数重跑。结果可能仍有噪声，"
            "写笔记时留意。"
        )

    return _ok(title, result.text, "media", ref, origin="asr", **payload)


def _run_async(coro):
    import asyncio

    return asyncio.run(coro)


# ------------------------------------------------------------------ 入口


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="fetch.py",
        description="抓取素材：视频/网页/PDF/文本 → JSON",
    )
    parser.add_argument("source", help="URL / 文件路径 / 直接粘贴的文本")
    parser.add_argument("--offset", type=int, default=0,
                        help="从第几个字符开始返回（用于分段读长内容）")
    parser.add_argument("--max-chars", type=int, default=0,
                        help="最多返回多少字符，0 表示不限制")
    asr_options = parser.add_mutually_exclusive_group()
    asr_options.add_argument("--allow-asr", action="store_true",
                        help="显式允许无字幕时下载音频并运行本地 ASR")
    asr_options.add_argument("--no-asr", action="store_true",
                        help="禁用 ASR，只吃平台字幕（不需要本地模型）")
    parser.add_argument("--lang", default="zh", help="ASR 语言提示，默认 zh")
    credentials = parser.add_mutually_exclusive_group()
    credentials.add_argument("--anonymous", action="store_true",
                        help="免登录：不读取 Cookie 文件或浏览器登录态")
    credentials.add_argument("--cookies-from-browser", default=None,
                        metavar="BROWSER",
                        help="借用浏览器的登录态（edge / chrome / firefox）。"
                             "B站的 AI 字幕、会员视频需要这个")
    credentials.add_argument("--cookie-file", default=None, metavar="PATH",
                        help="用 cookies.txt 文件（Netscape 格式）")
    credentials.add_argument("--local-browser", action="store_true",
                        help="本地专用 Chrome 自动采集 B站字幕；会话有效时直接复用，失效时交接登录")
    parser.add_argument("--refresh", action="store_true",
                        help="重新采集 B站平台字幕，不复用已保存的全文缓存")
    parser.add_argument("--format", choices=["json", "text"], default="json",
                        help="输出格式")
    args = parser.parse_args()

    result = run(
        args.source.strip(),
        allow_asr=args.allow_asr,
        language=args.lang,
        cookies_from_browser=args.cookies_from_browser,
        cookie_file=args.cookie_file,
        anonymous=args.anonymous,
        local_browser=args.local_browser,
        refresh=args.refresh,
    )

    if not result.get("ok"):
        if args.format == "json":
            _emit(result)
        else:
            print(f"ERROR: {result['error']['message']}", file=sys.stderr)
            if result["error"].get("hint"):
                print(f"HINT: {result['error']['hint']}", file=sys.stderr)
        return 1

    body = result["content"]
    total = len(body)

    if args.offset or args.max_chars:
        end = args.offset + args.max_chars if args.max_chars else None
        result["content"] = body[args.offset:end]
        result["char_count"] = len(result["content"])
        result["total_chars"] = total
        result["offset"] = args.offset
        result["has_more"] = bool(end and end < total)
        if result["has_more"]:
            result["next_offset"] = end

    if args.format == "text":
        sys.stdout.write(result["content"])
        if not result["content"].endswith("\n"):
            sys.stdout.write("\n")
    else:
        _emit(result)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
