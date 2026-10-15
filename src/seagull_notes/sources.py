"""Source labels and reading defaults shared by ingestion, notes and the shelf."""
from urllib.parse import urlsplit

SOURCE_LABELS = {"video": "视频精读", "local": "本地素材", "topic": "主题知识", "text": "文本整理", "article": "网页笔记"}
STYLE_LABELS = {"paper": "米色纸页", "atlas": "手写札记", "folio": "皮革书卷",
                "whale": "肥鱼自习室", "anime": "次元放映厅", "cyber": "霓虹矩阵"}


def source_kind(note: dict) -> str:
    if note.get("source_kind"):
        kind = note["source_kind"]
        if kind not in SOURCE_LABELS:
            raise ValueError("source_kind 必须是 video/local/topic/text/article")
        return kind
    if note.get("source_url"):
        host = (urlsplit(note["source_url"]).hostname or "").lower()
        return "video" if any(host == domain or host.endswith("." + domain)
                              for domain in ("bilibili.com", "b23.tv", "youtube.com", "youtu.be")) else "article"
    if note.get("source_ref"):
        return "local"
    raise ValueError("请提供来源，或声明 topic/text 类型")


def reading_style(note: dict) -> str:
    style = note.get("style") or ("paper" if source_kind(note) in {"video", "local"} else "atlas")
    if style not in STYLE_LABELS:
        raise ValueError("style 必须是 " + "/".join(STYLE_LABELS))
    return style


def source_links(note: dict) -> list[dict]:
    links = []
    for item in note.get("sources", []):
        parts = urlsplit(item["url"])
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("资料链接必须为有效 HTTP/HTTPS 地址")
        links.append({"title": str(item.get("title") or parts.netloc), "url": item["url"]})
    return links
