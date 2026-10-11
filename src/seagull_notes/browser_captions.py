"""Collect Bilibili caption files with a private, persistent Chrome session."""

from __future__ import annotations

import json
import base64
import io
import math
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

from . import config, storage


class CaptionError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def video_target(url: str) -> tuple[str, str, int]:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    match = re.fullmatch(r"/video/(BV[0-9A-Za-z]{10})/?", parsed.path)
    if parsed.scheme not in ("http", "https") or not (host == "bilibili.com" or host.endswith(".bilibili.com")) or not match:
        raise CaptionError("unsupported_source", "本地采集器目前支持 B站 BV 视频链接；其他来源继续使用原有获取流程。")
    try:
        part = int(parse_qs(parsed.query).get("p", ["1"])[0])
    except ValueError:
        raise CaptionError("invalid_part", "分 P 参数必须是正整数。") from None
    if part < 1:
        raise CaptionError("invalid_part", "分 P 参数必须是正整数。")
    bvid = match[1]
    return f"https://www.bilibili.com/video/{bvid}/?p={part}", bvid, part


def caption_url(url: str) -> str:
    url = "https:" + url if url.startswith("//") else url
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not any(host == domain or host.endswith("." + domain) for domain in ("hdslb.com", "bilibili.com")):
        raise CaptionError("invalid_subtitle_url", "字幕地址不是平台提供的 HTTPS 资源。")
    return url


def parse_captions(payload: dict) -> list[dict]:
    segments = []
    rows = payload.get("body")
    if not isinstance(rows, list):
        raise CaptionError("invalid_subtitle", "平台未返回完整字幕条目列表。")
    for row in rows:
        try:
            start, end = float(row["from"]), float(row["to"])
            text = row["content"].strip()
        except (KeyError, TypeError, ValueError, AttributeError):
            raise CaptionError("invalid_subtitle", "字幕文件缺少有效的起止时间或正文。") from None
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end < start:
            raise CaptionError("invalid_subtitle", "字幕文件包含无效时间轴。")
        if text:
            segments.append({"start": start, "end": end, "text": text})
    if not segments:
        raise CaptionError("empty_subtitle", "平台返回的字幕文件为空。")
    return sorted(segments, key=lambda segment: (segment["start"], segment["end"]))


def _json(context, endpoint: str, params: dict | None = None) -> dict:
    # Use the project's direct-network setting; credentials stay in memory and
    # only cookies applicable to this platform URL enter this request.
    cookies = httpx.Cookies()
    for cookie in context.cookies(endpoint):
        cookies.set(cookie["name"], cookie["value"], domain=cookie["domain"], path=cookie["path"])
    transport = httpx.HTTPTransport(local_address=config.find_physical_ip())
    agent = context.pages[0].evaluate("navigator.userAgent")
    with httpx.Client(transport=transport, trust_env=False, cookies=cookies, timeout=30,
                      headers={"Referer": "https://www.bilibili.com/", "User-Agent": agent}) as client:
        response = client.get(endpoint, params=params)
        if not response.is_success:
            raise CaptionError("platform_access_limited", f"平台接口返回 HTTP {response.status_code}；这不能证明视频没有字幕。")
        received = []
        for cookie in response.cookies.jar:
            item = {"name": cookie.name, "value": cookie.value, "path": cookie.path,
                    "domain": "." + cookie.domain.lstrip(".") if cookie.domain_specified else cookie.domain,
                    "secure": cookie.secure, "httpOnly": cookie.has_nonstandard_attr("HttpOnly")}
            if cookie.expires and cookie.expires > 0:
                item["expires"] = cookie.expires
            received.append(item)
        if received:
            context.add_cookies(received)
        try:
            payload = response.json()
        except ValueError:
            raise CaptionError("invalid_subtitle", "平台接口未返回可解析的 JSON 数据。") from None
        if not isinstance(payload, dict):
            raise CaptionError("invalid_subtitle", "平台接口未返回字幕对象。")
        if payload.get("code", 0) != 0:
            code = payload["code"]
            raise CaptionError("login_required" if code == -101 else "platform_access_limited",
                               f"平台接口返回状态 {code}；未取得完整字幕。")
        return payload


def _logged_in(context) -> bool:
    try:
        return bool(_json(context, "https://api.bilibili.com/x/web-interface/nav").get("data", {}).get("isLogin"))
    except CaptionError as exc:
        if exc.code == "login_required":
            return False
        raise


def _read(context, source: str, bvid: str, part: int, language: str) -> dict:
    video = _json(context, "https://api.bilibili.com/x/web-interface/view", {"bvid": bvid})["data"]
    pages = video.get("pages", [])
    if part > len(pages):
        raise CaptionError("invalid_part", f"视频只有 {len(pages)} 个分 P。")
    page = pages[part - 1]
    player = _json(context, "https://api.bilibili.com/x/player/wbi/v2",
                   {"aid": video["aid"], "cid": page["cid"]})["data"]
    listed_tracks = player.get("subtitle", {}).get("subtitles", [])
    tracks = [track for track in listed_tracks if track.get("subtitle_url")]
    if not tracks and not _logged_in(context):
        raise CaptionError("login_required", "专用本地浏览器需要登录后才能继续查询平台字幕。")
    if not tracks:
        message = ("平台存在字幕轨，但未返回下载地址；继续解决字幕读取，不将其判定为无字幕。" if listed_tracks else
                   "已登录，接口未返回普通或 AI 字幕轨；需结合播放器字幕菜单确认两类字幕均不存在后，才提供 ASR 选项。")
        raise CaptionError("subtitle_unavailable", message)
    preferred = [language, "zh-CN", "zh-Hans", "zh", "ai-zh"] if language == "zh" else [language, "ai-" + language]
    track = next((track for lan in preferred for track in tracks if track.get("lan") == lan), tracks[0])
    segments = parse_captions(_json(context, caption_url(track["subtitle_url"])))
    duration = float(page.get("duration", video.get("duration", 0)))
    title = video["title"] + (f" · P{part} {page['part']}" if len(pages) > 1 else "")
    content = "\n".join(segment["text"] for segment in segments)
    return {"ok": True, "title": title, "source_kind": "media", "source_ref": source,
            "video_id": bvid, "part": part, "cid": page["cid"], "uploader": video.get("owner", {}).get("name", ""),
            "content": content, "char_count": len(content), "segments": segments, "duration": duration,
            "origin": "platform_subtitle", "caption_language": track.get("lan", ""),
            "coverage": {"first_start": segments[0]["start"], "last_end": max(s["end"] for s in segments),
                         "gap_to_video_end": max(0, duration - max(s["end"] for s in segments))},
            "note": "来自平台整条字幕文件，保留时间轴；未运行 ASR。请核对末条时间及明显缺段。"}


def _srt_time(seconds: float) -> str:
    value = round(seconds * 1000)
    hours, value = divmod(value, 3600000)
    minutes, value = divmod(value, 60000)
    seconds, milliseconds = divmod(value, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


def save_captions(result: dict) -> dict:
    folder = config.DATA_DIR / "captions" / f"{result['video_id']}-p{result['part']}"
    folder.mkdir(parents=True, exist_ok=True)
    result["caption_file"] = str(folder / "transcript.json")
    result["subtitle_file"] = str(folder / "captions.srt")
    body = "\n\n".join(f"{index}\n{_srt_time(segment['start'])} --> {_srt_time(segment['end'])}\n{segment['text']}"
                         for index, segment in enumerate(result["segments"], 1))
    Path(result["subtitle_file"]).write_text(body + "\n", encoding="utf-8")
    Path(result["caption_file"]).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    storage.save_transcript(storage.content_key(f"subtitle:{result['video_id']}:{result['cid']}"),
                            text=result["content"], segments=result["segments"], duration=result["duration"],
                            origin="platform_subtitle")
    return result


def cached_captions(bvid: str, part: int, language: str) -> dict | None:
    folder = config.DATA_DIR / "captions" / f"{bvid}-p{part}"
    path = folder / "transcript.json"
    if not path.is_file() or not (folder / "captions.srt").is_file():
        return None
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        if (not result.get("ok") or result.get("origin") != "platform_subtitle"
                or result.get("video_id") != bvid or result.get("part") != part
                or not isinstance(result.get("content"), str)):
            return None
        cached_language = result.get("caption_language", "").removeprefix("ai-").split("-")[0]
        if cached_language != language.removeprefix("ai-").split("-")[0]:
            return None
        segments = parse_captions({"body": [{"from": row["start"], "to": row["end"], "content": row["text"]}
                                            for row in result["segments"]]})
        if "\n".join(row["text"] for row in segments) != result["content"]:
            return None
    except (OSError, ValueError, KeyError, TypeError, AttributeError, CaptionError):
        return None
    result.update(caption_file=str(path), subtitle_file=str(folder / "captions.srt"),
                  collected_at=result.get("collected_at", path.stat().st_mtime), cache_hit=True,
                  note="复用完整平台字幕缓存，未重新请求平台、登录或运行 ASR；来源采集时间已保留。")
    return result


def _launch(playwright):
    options = {"user_data_dir": str(config.DATA_DIR / "caption-browser-profile"), "headless": True,
               "viewport": {"width": 1280, "height": 860}, "locale": "zh-CN"}
    try:
        context = playwright.chromium.launch_persistent_context(channel="chrome", **options)
    except Exception as exc:
        if "not found" not in str(exc).lower() and "doesn't exist" not in str(exc).lower():
            raise
        context = playwright.chromium.launch_persistent_context(**options)
    context.route("**/*", lambda route: route.abort() if route.request.resource_type == "media" or
                  urlparse(route.request.url).path.lower().endswith((".m4s", ".mp4", ".flv", ".m3u8")) else route.continue_())
    return context


def _login_page(qr_url: str, state: dict):
    import qrcode
    image = io.BytesIO()
    qrcode.make(qr_url).save(image, format="PNG")
    template = Path(__file__).resolve().parents[2] / "skill" / "assets" / "caption-login.html"
    html = template.read_text(encoding="utf-8").replace("__QR_IMAGE__", base64.b64encode(image.getvalue()).decode("ascii"))
    path = "/login/" + secrets.token_urlsafe(24)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in (path, path + "/status"):
                self.send_error(404)
                return
            status = self.path.endswith("/status")
            content = json.dumps({"state": state["state"]}) if status else html
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8" if status else "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(content.encode("utf-8"))

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}{path}"


def _wait_for_login(context, timeout: float, log) -> None:
    if _logged_in(context):
        return
    try:
        qr = _json(context, "https://passport.bilibili.com/x/passport-login/web/qrcode/generate")["data"]
        state = {"state": "waiting"}
        server, url = _login_page(qr["url"], state)
    except ImportError:
        raise CaptionError("browser_dependency_missing", "登录页需要 qrcode；请在当前 Python 安装项目的 [browser] 可选依赖。") from None
    log(f"LOGIN_URL {url}")
    log("请展示上面的本地登录页，使用 B站 App 扫码确认；成功后会自动采集。")
    deadline = time.monotonic() + min(timeout, 180)
    try:
        while time.monotonic() < deadline:
            result = _json(context, "https://passport.bilibili.com/x/passport-login/web/qrcode/poll",
                           {"qrcode_key": qr["qrcode_key"]})["data"]
            code = result["code"]
            if code == 0:
                if not _logged_in(context):
                    raise CaptionError("login_unverified", "扫码已确认，但平台尚未验证会话有效；未宣称登录成功。")
                state["state"] = "complete"
                log("本地采集器登录已验证，自动继续获取完整字幕。")
                time.sleep(2)
                return
            if code == 86038:
                break
            if code not in (86101, 86090):
                raise CaptionError("login_failed", f"平台扫码状态异常：{code}。")
            state["state"] = "scanned" if code == 86090 else "waiting"
            time.sleep(2)
        state["state"] = "expired"
        time.sleep(2)
        raise CaptionError("login_timeout", "二维码已失效或等待登录超时；可重新运行继续。")
    finally:
        server.shutdown()
        server.server_close()


def collect(url: str, *, language: str = "zh", allow_login: bool = True, login_timeout: float = 300,
            refresh: bool = False, log=print) -> dict:
    started = time.perf_counter()
    source, bvid, part = video_target(url)
    cached = None if refresh else cached_captions(bvid, part, language)
    if cached:
        cached["collection_seconds"] = round(time.perf_counter() - started, 4)
        return cached
    try:
        from playwright.sync_api import sync_playwright, Error
    except ImportError:
        raise CaptionError("browser_dependency_missing", '本地采集器需要 Playwright：在当前 Python 安装项目的 [browser] 可选依赖。') from None
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as playwright:
            context = _launch(playwright)
            try:
                result = _read(context, source, bvid, part, language)
            except CaptionError as exc:
                if exc.code != "login_required" or not allow_login:
                    raise
                _wait_for_login(context, login_timeout, log)
                result = _read(context, source, bvid, part, language)
            finally:
                context.close()
    except Error:
        raise CaptionError("browser_failed", "本地浏览器启动或请求失败；检查 Chrome 安装、网络及专用配置是否正在使用。缺少浏览器时可安装 Playwright Chromium。") from None
    except httpx.HTTPError:
        raise CaptionError("network_failed", "平台字幕请求失败；检查网络及项目的直连地址设置。") from None
    result.update(collected_at=time.time(), cache_hit=False,
                  collection_seconds=round(time.perf_counter() - started, 4))
    return save_captions(result)
