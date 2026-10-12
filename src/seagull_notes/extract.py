"""内容抽取：网页正文、PDF、本地文本。

对应 CuteNote 管线里的 extract_content / remote_pdf_extract 两个阶段。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

BROWSER_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
              "image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Connection": "keep-alive",
}

PDF_SUFFIXES = {".pdf"}
TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".rst"}
SUBTITLE_SUFFIXES = {".srt", ".vtt", ".ass", ".ssa", ".json3", ".sbv", ".lrc"}
AUDIO_SUFFIXES = {".mp3", ".m4a", ".wav", ".flac", ".aac", ".ogg", ".opus", ".wma"}
VIDEO_SUFFIXES = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".ts", ".m4v"}


@dataclass
class Extracted:
    text: str
    title: str
    kind: str            # "webpage" | "pdf" | "text" | "media" | "raw"
    ref: str             # 来源标识：URL 或本地路径


def classify_local_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in PDF_SUFFIXES:
        return "pdf"
    if suffix in SUBTITLE_SUFFIXES:
        return "subtitle"
    if suffix in TEXT_SUFFIXES:
        return "text"
    if suffix in AUDIO_SUFFIXES or suffix in VIDEO_SUFFIXES:
        return "media"
    return "text"


def extract_subtitle_file(path: Path) -> "Extracted":
    """字幕文件 → 干净文本。

    用户在浏览器里导出字幕（.srt/.vtt）丢进来时走这条路——
    这样就能完全绕开 ASR，不需要本地模型。
    """
    from . import media

    raw = path.read_text(encoding="utf-8", errors="ignore")
    lowered_name = path.name.lower()

    if ".json3" in lowered_name:
        text = media._parse_json3(raw)
    elif path.suffix.lower() == ".srt" or path.suffix.lower() == ".sbv":
        text = media._parse_srt(raw)
    elif path.suffix.lower() == ".vtt":
        text = media._parse_vtt(raw)
    elif path.suffix.lower() in {".ass", ".ssa"}:
        text = _parse_ass(raw)
    elif path.suffix.lower() == ".lrc":
        text = _parse_lrc(raw)
    else:
        text = raw.strip()

    if not text:
        # 解析失败就别装聪明，原样返回
        text = raw.strip()

    return Extracted(text=text, title=path.stem, kind="subtitle", ref=str(path))


def _parse_ass(raw: str) -> str:
    """ASS/SSA 字幕 → 纯文本。只取 Dialogue 行，去掉样式标签。"""
    import re as _re

    lines: list[str] = []
    for line in raw.splitlines():
        if not line.startswith("Dialogue:"):
            continue
        # 格式：Dialogue: layer,start,end,style,name,marginL,marginR,marginV,effect,text
        parts = line.split(",", 9)
        if len(parts) < 10:
            continue
        text = parts[9]
        text = _re.sub(r"\{[^}]*\}", "", text)      # 去掉 {\pos(..)} 之类的标签
        text = text.replace("\\N", " ").replace("\\n", " ")
        text = text.strip()
        if text:
            lines.append(text)
    return " ".join(lines).strip()


def _parse_lrc(raw: str) -> str:
    """LRC 歌词 → 纯文本。"""
    import re as _re

    lines: list[str] = []
    for line in raw.splitlines():
        cleaned = _re.sub(r"\[\d{1,2}:\d{2}(?:[.:]\d{1,3})?\]", "", line).strip()
        if cleaned:
            lines.append(cleaned)
    return " ".join(lines).strip()


def extract_pdf(path: Path) -> Extracted:
    """PDF 文本层抽取。扫描件抽不出内容时返回空串，调用方需另行 OCR。"""
    import pymupdf

    doc = pymupdf.open(str(path))
    pages: list[str] = []
    for page in doc:
        pages.append(page.get_text())
    doc.close()

    title = path.stem
    return Extracted(
        text="\n\n".join(pages).strip(),
        title=title,
        kind="pdf",
        ref=str(path),
    )


def extract_local_text(path: Path) -> Extracted:
    raw = path.read_text(encoding="utf-8", errors="ignore").strip()
    title = path.stem
    # Markdown 文件优先用一级标题当标题
    for line in raw.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break
    return Extracted(text=raw, title=title, kind="text", ref=str(path))


def _html_to_text(html: str, url: str) -> tuple[str, str]:
    """readability 提正文；失败则退化为粗暴去标签。"""
    try:
        from readability import Document

        doc = Document(html)
        title = doc.short_title() or url
        # readability 输出的是清理过的 HTML，再去一层标签
        content_html = doc.summary(html_partial=True)
    except Exception:
        title, content_html = url, html

    try:
        from lxml import html as lxml_html

        original = lxml_html.fromstring(html)
        container = None
        for selector in [
            '//*[contains(concat(" ", normalize-space(@class), " "), " markdown-body ")]',
            '//article', '//main', '//*[@role="main"]', '//*[@id="main" or @id="main-content"]', '//*[@id="content"]',
        ]:
            candidates = original.xpath(selector)
            if candidates:
                container = max(candidates, key=lambda element: len(element.text_content()))
                break
        tree = container if container is not None else lxml_html.fromstring(content_html)
        for element in tree.xpath('.//script|.//style|.//noscript|.//nav|.//aside'):
            element.drop_tree()
        text = tree.text_content()
    except Exception:
        import re

        text = re.sub(r"<script.*?</script>|<style.*?</style>", "", content_html, flags=re.S)
        text = re.sub(r"<[^>]+>", " ", text)

    lines = [ln.strip() for ln in text.splitlines()]
    cleaned = "\n".join(ln for ln in lines if ln)
    return title, cleaned.strip()


def _looks_like_spa(html: str, text: str) -> bool:
    """判断页面是不是靠 JS 渲染的空壳。

    特征：HTML 很长但正文极短，且带 SPA 框架的标记。
    """
    if len(text) > 500:
        return False
    if len(html) < 2000:
        return False
    markers = (
        "__NEXT_DATA__", "__NUXT__", "window.__INITIAL_STATE__",
        'id="app"', "id='app'", 'id="root"', "id='root'",
        "window.__NUXT__", "__remixContext", "data-reactroot",
    )
    return any(m in html for m in markers)


def _build_client(url: str, timeout: float) -> httpx.AsyncClient:
    """造 httpx 客户端。国内站点绑定物理网卡直连，绕开 TUN 代理。"""
    from . import config

    kwargs: dict = {
        "follow_redirects": True,
        "timeout": timeout,
        "headers": BROWSER_HEADERS,
    }
    if config.needs_direct(url):
        bind_ip = config.find_physical_ip()
        if bind_ip:
            kwargs["transport"] = httpx.AsyncHTTPTransport(local_address=bind_ip, retries=1)
    return httpx.AsyncClient(**kwargs)


async def extract_url(url: str, *, timeout: float = 30.0) -> Extracted:
    """网页 → 正文文本。带浏览器头，遇到 403 会换一套头重试一次。"""
    async with _build_client(url, timeout) as client:
        resp = await client.get(url)

        if resp.status_code in (403, 412):
            # 有些站点按 Sec-Fetch-* 判机器人，去掉这几个头再试
            fallback_headers = {
                k: v for k, v in BROWSER_HEADERS.items()
                if not k.startswith("Sec-Fetch")
            }
            resp = await client.get(url, headers=fallback_headers)

        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "").lower()

        if "application/pdf" in content_type:
            return await _extract_remote_pdf(resp.content, url)

        html = resp.text

    title, text = _html_to_text(html, url)

    if _looks_like_spa(html, text):
        raise RuntimeError(
            f"页面正文由 JavaScript 渲染，静态抓取拿不到内容：{url}\n"
            "建议：把文章正文直接粘贴进来，或用能输出静态 HTML 的链接。"
        )

    return Extracted(text=text, title=title, kind="webpage", ref=url)


async def _extract_remote_pdf(payload: bytes, url: str) -> Extracted:
    """远程 PDF：先落盘到 media 目录再抽，避免大文件全塞内存。"""
    import pymupdf

    from . import config

    config.ensure_dirs()
    name = url.rstrip("/").split("/")[-1] or "remote.pdf"
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    cached = config.MEDIA_DIR / name
    cached.write_bytes(payload)

    doc = pymupdf.open(str(cached))
    pages = [page.get_text() for page in doc]
    doc.close()

    return Extracted(
        text="\n\n".join(pages).strip(),
        title=cached.stem,
        kind="pdf",
        ref=url,
    )


def extract_raw_text(text: str, title: str = "未命名文本") -> Extracted:
    return Extracted(text=text.strip(), title=title, kind="raw", ref="inline:text")
