"""管线编排：把各阶段串起来，驱动作业状态机。

阶段顺序对齐 CuteNote：
    claimed → normalize_input_url → cache_lookup → (reuse_transcript | fetch_transcript
    | media_download_and_transcribe | speech_to_text | remote_pdf_extract | extract_content)
    → generate_note → save_note
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

from . import asr, config, extract, generate, media, storage

URL_RE = re.compile(r"^https?://", re.I)
# 看起来像文件路径的特征：盘符、路径分隔符、常见扩展名
PATH_RE = re.compile(
    r"^(?:[a-zA-Z]:[\\/]|\\\\|\.{1,2}[\\/]|[\\/])"
    r"|\.(?:mp4|mkv|mov|avi|webm|flv|m4v|ts|mp3|m4a|wav|flac|aac|ogg|opus"
    r"|pdf|txt|md|markdown|rst|srt|vtt|json)$",
    re.I,
)


def _looks_like_path(source: str) -> bool:
    """区分"本地文件路径"和"直接粘贴的文本"。

    纯文本里不会出现盘符和路径分隔符，所以用这个特征判断足够稳。
    返回 True 但文件不存在时，说明是拼错的路径——该报错就报错。
    """
    if "\n" in source or len(source) > 260:
        return False
    return bool(PATH_RE.search(source.strip()))


def _guess_title(text: str) -> str:
    """从粘贴的文本里猜个标题：优先取第一句，退而求其次取第一行。"""
    import re as _re

    for line in text.splitlines():
        line = line.strip().lstrip("#").strip()
        if not line:
            continue
        # 中文句号 / 问号 / 感叹号 / 英文句点，取第一句
        sentence = _re.split(r"(?<=[。！？!?])|(?<=\.\s)", line)[0].strip()
        candidate = sentence or line
        return candidate[:40] + ("…" if len(candidate) > 40 else "")
    return "未命名文本"


@dataclass
class PipelineResult:
    job_id: str
    note_id: str | None
    status: str
    stage: str
    transcript_origin: str | None = None
    generator: str | None = None


async def _resolve_content(source: str, job_id: str) -> tuple[str, str, str]:
    """来源 → (正文文本, 标题, 来源种类)。

    这一层负责分流：视频 / 网页 / PDF / 纯文本 / 本地文件。
    """
    # --- 本地文件 ---
    if not URL_RE.match(source):
        path = Path(source)
        if not path.exists():
            if _looks_like_path(source):
                raise FileNotFoundError(f"文件不存在：{source}")
            # 不像路径，就当成直接粘贴的文本
            doc = extract.extract_raw_text(source, _guess_title(source))
            return doc.text, doc.title, "raw"

        kind = extract.classify_local_file(path)
        if kind == "media":
            storage.update_job(job_id, status="processing", stage="media_download_and_transcribe")
            key = storage.content_key(f"{path.resolve()}:{path.stat().st_mtime_ns}")
            cached = storage.get_transcript(key)
            if cached:
                storage.update_job(job_id, stage="reuse_transcript")
                return cached["text"], path.stem, "media"
            return await _transcribe_media(path, key, job_id, path.stem)

        if kind == "pdf":
            storage.update_job(job_id, status="processing", stage="remote_pdf_extract")
            doc = extract.extract_pdf(path)
            return doc.text, doc.title, "pdf"

        doc = extract.extract_local_text(path)
        return doc.text, doc.title, "text"

    # --- URL ---
    storage.update_job(job_id, status="processing", stage="normalize_input_url")

    if media.is_video_url(source):
        storage.update_job(job_id, stage="media_download")
        info = await media.fetch_media(source, want_subtitle=True)

        # 有平台字幕 → 直接复用，跳过 ASR（最省时间的一步）
        if info.subtitle_text:
            storage.update_job(job_id, stage="fetch_transcript")
            key = storage.content_key(f"subtitle:{info.video_id}")
            storage.save_transcript(
                key, text=info.subtitle_text, segments=[], duration=info.duration,
                origin="platform_subtitle",
            )
            return info.subtitle_text, info.title, "media"

        # 没字幕 → 下载音频跑 ASR
        if info.media_path is None:
            raise RuntimeError("下载完成但没有拿到媒体文件")

        storage.update_job(job_id, stage="speech_to_text")
        key = storage.content_key(f"asr:{info.video_id}")
        cached = storage.get_transcript(key)
        if cached:
            storage.update_job(job_id, stage="reuse_transcript")
            return cached["text"], info.title, "media"

        text, _, _ = await _transcribe_media(
            info.media_path, key, job_id, info.title, duration=info.duration
        )
        return text, info.title, "media"

    # 普通网页
    storage.update_job(job_id, stage="extract_content")
    doc = await extract.extract_url(source)
    return doc.text, doc.title, doc.kind


async def _transcribe_media(
    path: Path, key: str, job_id: str, title: str, duration: float = 0.0,
) -> tuple[str, str, str]:
    """跑 ASR 并写缓存。"""
    storage.update_job(job_id, stage="speech_to_text")
    result = await asr.transcribe(path)

    storage.save_transcript(
        key, text=result.text, segments=result.segments,
        duration=result.duration or duration, origin="asr",
    )
    return result.text, title, "media"


async def run_job(job_id: str) -> PipelineResult:
    """执行一个作业。异常一律转成 failed 状态，不往外抛。

    两种收尾方式：
      output_type == "material"  → 抽完素材就停，等 AI 客户端调 save_note 交付笔记。
                                    这条路径不需要任何 API key。
      其他 output_type            → 服务端自己生成笔记（配了 LLM 用 LLM，没配走降级）。
    """
    job = storage.get_job(job_id)
    if job is None:
        raise KeyError(f"作业不存在：{job_id}")

    try:
        storage.update_job(job_id, status="processing", stage="cache_lookup")

        content, title, source_kind = await _resolve_content(job.source, job_id)

        if not content.strip():
            storage.update_job(
                job_id, status="blocked", stage="extract_content",
                error_code="empty_content",
                error_message="没有从来源里抽取到任何文本内容",
            )
            return PipelineResult(job_id, None, "blocked", "extract_content")

        # 素材模式：存下来，交给客户端写笔记
        if job.output_type == "material":
            storage.update_job(job_id, stage="material_ready")
            storage.save_material(job_id, title=title, body=content, source_kind=source_kind)
            storage.update_job(
                job_id, status="completed", stage=storage.AWAITING_NOTE_STAGE,
            )
            return PipelineResult(
                job_id=job_id, note_id=None, status="completed",
                stage=storage.AWAITING_NOTE_STAGE,
                transcript_origin=source_kind, generator="client",
            )

        storage.update_job(job_id, stage="generate_note")
        note = await generate.generate(
            content, title=title, output_type=job.output_type, locale=job.locale,
        )

        storage.update_job(job_id, stage="save_note")
        saved = storage.save_note(
            title=note.title, markdown=note.markdown, mind_map=note.mind_map,
            source_kind=source_kind, source_ref=job.source, locale=job.locale,
        )

        storage.update_job(
            job_id, status="completed", stage="done", note_id=saved.id,
        )
        return PipelineResult(
            job_id=job_id, note_id=saved.id, status="completed", stage="done",
            generator=note.generator,
        )

    except asyncio.CancelledError:
        storage.update_job(job_id, status="canceled", stage="canceled")
        raise
    except Exception as exc:                                     # noqa: BLE001
        storage.update_job(
            job_id, status="failed", stage="failed",
            error_code=type(exc).__name__,
            error_message=str(exc)[:500],
        )
        return PipelineResult(job_id, None, "failed", "failed")


def spawn_job(job_id: str) -> asyncio.Task:
    """后台跑作业，立刻返回。调用方拿 job_id 轮询。"""
    return asyncio.create_task(run_job(job_id))
