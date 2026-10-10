"""MCP server：把管线包成 AI 客户端能调的工具。

传输方式：stdio（AI 客户端在自己机器上拉起这个进程，天然可信，无需认证）。

设计要点：默认走"素材模式"——服务端只负责下载和转写，笔记由 AI 客户端自己写。
这样用户不需要任何额外的 LLM API key，用客户端自带的模型额度就够了。

工具面：create_note / get_generation_job / get_material / save_note
       list_notes / get_note / export_note / prepare_model / runtime_info
"""

from __future__ import annotations

import asyncio
from typing import Any

from mcp.server.mcpserver import MCPServer

from . import asr, config, export, media, pipeline, storage

_NOTE_FORMAT_HINT = """写笔记时的约定：

mind_map 是树形结构，每个节点 {"title": "短标题", "children": [...]}。
根节点一个，第二层 3-7 个主分支，第三层是具体要点，节点标题控制在 10 字以内。

调 save_note 时传：
  job_id   —— 当前作业 id
  markdown —— 完整 Markdown 正文，用 # 一级标题开头，## / ### 分层
  mind_map —— 脑图树，JSON 数组
  title    —— 可选，不传就用素材标题
"""

mcp = MCPServer(
    "seagull-notes",
    title="Seagull Notes",
    version="0.2.0",
    instructions=(
        "把视频、网页、PDF、长文本转成结构化 Markdown 笔记和脑图。"
        "默认流程：create_note 抽素材 → 轮询 get_generation_job → "
        "get_material 取转写稿 → 你自己写 Markdown 和脑图树 → save_note 交付。"
        "这条路径不需要任何 API key。"
    ),
)

# 后台作业句柄，防止 task 被 GC 回收
_tasks: set[asyncio.Task] = set()


@mcp.tool()
async def create_note(
    content: str,
    output_type: str = "material",
    locale: str = "zh-CN",
    style: str = "auto",
) -> dict[str, Any]:
    """把视频链接、网页、本地文件路径或长文本，抽取成可写笔记的素材。

    **默认不需要任何 API key** —— 服务端只负责下载和转写，笔记由你自己（AI 客户端）来写。

    content 可以是：
      - 视频/音频平台链接（B站、YouTube 等）
      - 普通网页链接
      - 本地文件绝对路径（视频、音频、PDF、txt、md）
      - 直接粘贴的长文本

    output_type 取值：
      "material"          —— 默认。只抽素材，抽完你自己写笔记再调 save_note
      "detailed_markdown" —— 服务端自己生成（需要配 LLM key，没配会走降级模式）
      "mind_map"          —— 同上
      "long_image"        —— 同上

    这是异步作业：立即返回 job_id，用 get_generation_job 轮询。
    状态变成 completed 且 stage 为 awaiting_note 时，调 get_material 取素材。
    """
    if not content.strip():
        return {"error": {"code": "empty_input", "message": "content 不能为空"}}

    source = content.strip()
    job = storage.create_job(output_type=output_type, source=source, locale=locale)

    task = pipeline.spawn_job(job.id)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)

    return {
        "job_id": job.id,
        "status": job.status,
        "stage": job.stage,
        "output_type": output_type,
        "source_kind": _peek_kind(source),
        "poll_after_seconds": config.JOB_POLL_BACKOFF[0],
        "max_wait_seconds": config.JOB_MAX_WAIT_SECONDS,
        "next_step": (
            "轮询 get_generation_job 到 completed，然后调 get_material 取素材"
            if output_type == "material"
            else "轮询 get_generation_job 到 completed，然后调 export_note"
        ),
    }


@mcp.tool()
async def get_material(
    job_id: str,
    offset: int = 0,
    max_chars: int = 30000,
) -> dict[str, Any]:
    """取回作业抽取的素材（转写稿或正文），用来写笔记。

    素材可能很长（一小时的视频能到几万字），所以支持分段：
    先不传参数拿前 30000 字，如果返回 truncated: true，再用 offset 往下读。

    拿到素材后，你自己整理成 Markdown 笔记和脑图树，然后调 save_note 交付。
    """
    job = storage.get_job(job_id)
    if job is None:
        return {"error": {"code": "job_not_found", "message": f"作业不存在：{job_id}"}}

    material = storage.get_material(job_id)
    if material is None:
        return {
            "error": {
                "code": "material_not_ready",
                "message": f"素材还没准备好，当前状态：{job.status} / {job.stage}",
            }
        }

    body = material.body
    chunk = body[offset:offset + max_chars]
    has_more = offset + max_chars < len(body)

    return {
        "job_id": job_id,
        "title": material.title,
        "source_kind": material.source_kind,
        "content": chunk,
        "offset": offset,
        "char_count": material.char_count,
        "has_more": has_more,
        "next_offset": offset + max_chars if has_more else None,
        "note_format": _NOTE_FORMAT_HINT,
    }


@mcp.tool()
async def save_note(
    job_id: str,
    markdown: str,
    mind_map: list[dict[str, Any]] | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    """保存你写好的笔记。这是完成笔记流程的最后一步。

    传 job_id（拿它的来源信息）、markdown 正文、可选的 mind_map 脑图树。
    保存完会返回 note_id，之后可以调 export_note 导出成文件或脑图图片。
    """
    job = storage.get_job(job_id)
    if job is None:
        return {"error": {"code": "job_not_found", "message": f"作业不存在：{job_id}"}}

    if not markdown.strip():
        return {"error": {"code": "empty_markdown", "message": "markdown 不能为空"}}

    material = storage.get_material(job_id)
    resolved_title = title or (material.title if material else "未命名笔记")
    source_kind = material.source_kind if material else "unknown"

    tree = _normalize_tree(mind_map) if mind_map else None

    note = storage.save_note(
        title=resolved_title,
        markdown=markdown,
        mind_map=tree,
        source_kind=source_kind,
        source_ref=job.source,
        locale=job.locale,
    )

    storage.update_job(job_id, status="completed", stage="done", note_id=note.id)

    return {
        "note_id": note.id,
        "title": note.title,
        "markdown_chars": len(note.markdown),
        "mind_map_nodes": _count_nodes(tree) if tree else 0,
        "next_step": "调 export_note 导出：markdown / svg / png / json",
    }


def _normalize_tree(nodes: list[Any]) -> list[dict[str, Any]]:
    """洗干净客户端送来的脑图树。"""
    def clean(node: Any) -> dict[str, Any] | None:
        if isinstance(node, str):
            return {"title": node.strip()} if node.strip() else None
        if not isinstance(node, dict):
            return None
        text = str(node.get("title") or node.get("name") or "").strip()
        if not text:
            return None
        out: dict[str, Any] = {"title": text}
        kids = node.get("children")
        if isinstance(kids, list):
            cleaned = [c for c in (clean(k) for k in kids) if c]
            if cleaned:
                out["children"] = cleaned
        return out

    return [c for c in (clean(n) for n in nodes) if c]


def _count_nodes(nodes: list[dict[str, Any]]) -> int:
    total = 0
    stack = list(nodes)
    while stack:
        node = stack.pop()
        total += 1
        stack.extend(node.get("children") or [])
    return total


@mcp.tool()
async def get_generation_job(job_id: str) -> dict[str, Any]:
    """查询作业状态。

    先等 poll_after_seconds，再查。未变的状态按 2→4→8→10 秒退避。
    terminal 为 true 时停止轮询：completed / failed / blocked / canceled 都是终态。
    超过 max_wait_seconds 的客户端侧超时不等于取消，服务端仍在跑。
    """
    job = storage.get_job(job_id)
    if job is None:
        return {"error": {"code": "job_not_found", "message": f"作业不存在：{job_id}"}}

    result = job.to_dict()
    if not job.terminal:
        result["poll_after_seconds"] = config.JOB_POLL_BACKOFF[min(
            max(_stage_progress(job.stage), 0), len(config.JOB_POLL_BACKOFF) - 1
        )]
    return result


_STAGE_ORDER = [
    "claimed", "create_note", "normalize_input_url", "cache_lookup",
    "reuse_transcript", "fetch_transcript", "remote_file_download",
    "media_download", "media_download_and_transcribe", "speech_to_text",
    "remote_pdf_extract", "extract_content", "generate_note", "save_note", "done",
]


def _stage_progress(stage: str) -> int:
    try:
        return _STAGE_ORDER.index(stage)
    except ValueError:
        return 0


@mcp.tool()
async def list_notes(limit: int = 20, cursor: str | None = None) -> dict[str, Any]:
    """列出最近的笔记。

    limit 取值 1-20。翻页时把上一页返回的 next_cursor 原样传回来。
    """
    parsed_cursor: float | None = None
    parsed_id: str | None = None
    if cursor:
        try:
            ts, _, note_id = cursor.partition(":")
            parsed_cursor, parsed_id = float(ts), note_id
        except ValueError:
            return {"error": {"code": "bad_cursor", "message": "cursor 格式不对，用上一页返回的值"}}

    notes, next_cursor = storage.list_notes(
        limit=limit, cursor=parsed_cursor, cursor_id=parsed_id,
    )
    return {
        "notes": [
            {
                "note_id": n.id,
                "title": n.title,
                "source_kind": n.source_kind,
                "source_ref": n.source_ref,
                "created_at": n.created_at,
            }
            for n in notes
        ],
        "count": len(notes),
        "next_cursor": f"{next_cursor[0]}:{next_cursor[1]}" if next_cursor else None,
    }


@mcp.tool()
async def get_note(note_id: str, include: str = "content,mind_map") -> dict[str, Any]:
    """读取一篇笔记。include 是逗号分隔的字段名：content / source / mind_map。

    长文本只返回预览；要完整正文或文件，用 export_note。
    """
    note = storage.get_note(note_id)
    if note is None:
        return {"error": {"code": "note_not_found", "message": f"笔记不存在：{note_id}"}}

    wanted = tuple(f.strip() for f in include.split(",") if f.strip())
    data = note.to_dict(include=wanted)

    preview_limit = 4000
    if "markdown" in data and len(data["markdown"]) > preview_limit:
        full_len = len(data["markdown"])
        data["markdown"] = data["markdown"][:preview_limit]
        data["markdown_truncated"] = True
        data["markdown_full_length"] = full_len
        data["hint"] = "正文已截断，用 export_note 取完整内容"

    return data


@mcp.tool()
async def export_note(note_id: str, format: str = "markdown") -> dict[str, Any]:
    """导出笔记。

    format 取值：
      markdown —— 返回完整正文并落盘 .md
      svg      —— 脑图矢量图 + 可在浏览器打开的 HTML
      png      —— 脑图位图（需装 playwright，否则自动退回 svg）
      json     —— 脑图原始树结构
      source   —— 内容来源标识
    """
    note = storage.get_note(note_id)
    if note is None:
        return {"error": {"code": "note_not_found", "message": f"笔记不存在：{note_id}"}}

    try:
        result = await asyncio.to_thread(export.dispatch, note, format)
    except ValueError as exc:
        return {"error": {"code": "bad_format", "message": str(exc)}}
    except Exception as exc:                                    # noqa: BLE001
        return {"error": {"code": type(exc).__name__, "message": str(exc)[:300]}}

    result["note_id"] = note_id
    return result


@mcp.tool()
async def prepare_model() -> dict[str, Any]:
    """把 ASR 模型下载到本地（E 盘）。

    首次使用前跑一次。large-v3 约 3 GB，下载耗时取决于网速。
    已经下过就直接返回缓存路径。
    """
    if asr.model_is_cached():
        return {
            "status": "cached",
            "model": config.ASR_MODEL,
            "cache_dir": str(config.HF_HUB_CACHE),
        }
    try:
        path = await asr.prefetch_model()
    except Exception as exc:                                    # noqa: BLE001
        return {"error": {"code": type(exc).__name__, "message": str(exc)[:400]}}
    return {
        "status": "downloaded",
        "model": config.ASR_MODEL,
        "path": str(path),
        "cache_dir": str(config.HF_HUB_CACHE),
    }


@mcp.tool()
async def runtime_info() -> dict[str, Any]:
    """报一下配置：模型位置、设备、是否配了 LLM。排查问题时先看这个。"""
    return {
        "project_home": str(config.HOME),
        "model": config.ASR_MODEL,
        "device": config.ASR_DEVICE,
        "compute_type": config.ASR_COMPUTE_TYPE,
        "model_cached": asr.model_is_cached(),
        "hf_cache_dir": str(config.HF_HUB_CACHE),
        "llm_configured": bool(config.LLM_API_KEY),
        "llm_model": config.LLM_MODEL if config.LLM_API_KEY else None,
        "db_path": str(config.DB_PATH),
    }


def _peek_kind(source: str) -> str:
    from pathlib import Path
    import re

    if re.match(r"^https?://", source, re.I):
        return "video_url" if media.is_video_url(source) else "web_url"
    path = Path(source)
    if path.exists():
        return "local_file"
    return "text"


def main() -> None:
    config.ensure_dirs()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
