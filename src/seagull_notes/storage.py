"""存储层：SQLite 落地笔记、作业、转写缓存。

设计参照 CuteNote 的作业模型：
  job   —— 一次生成请求，有状态机，可轮询
  note  —— 产物，含 Markdown 正文与脑图树
  transcript —— 按来源内容 hash 缓存，命中即跳过 ASR（最值钱的一层）
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from . import config

JobStatus = Literal["queued", "processing", "completed", "failed", "blocked", "canceled"]
# "material" 表示只抽取素材、等 AI 客户端来写笔记——这是默认模式，不需要任何 API key
OutputType = Literal[
    "material", "long_image", "mind_map", "detailed_markdown", "transcript"
]

TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "failed", "blocked", "canceled"})

# 素材就绪、等客户端交付笔记的状态
AWAITING_NOTE_STAGE = "awaiting_note"

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id              TEXT PRIMARY KEY,
    status          TEXT NOT NULL,
    stage           TEXT NOT NULL,
    output_type     TEXT NOT NULL,
    source          TEXT NOT NULL,
    locale          TEXT NOT NULL DEFAULT 'zh-CN',
    note_id         TEXT,
    error_code      TEXT,
    error_message   TEXT,
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS notes (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    markdown        TEXT NOT NULL DEFAULT '',
    mind_map_json   TEXT,
    source_kind     TEXT NOT NULL,
    source_ref      TEXT NOT NULL,
    locale          TEXT NOT NULL DEFAULT 'zh-CN',
    created_at      REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS transcripts (
    key             TEXT PRIMARY KEY,
    text            TEXT NOT NULL,
    segments_json   TEXT NOT NULL,
    duration        REAL NOT NULL DEFAULT 0,
    origin          TEXT NOT NULL,
    created_at      REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS job_materials (
    job_id          TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    body            TEXT NOT NULL,
    source_kind     TEXT NOT NULL,
    char_count      INTEGER NOT NULL,
    created_at      REAL NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    config.ensure_dirs()
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


def content_key(payload: str) -> str:
    """来源内容指纹，用于转写缓存命中。"""
    return hashlib.sha256(payload.strip().encode("utf-8")).hexdigest()[:32]


# --------------------------------------------------------------------------- jobs

@dataclass
class Job:
    id: str
    status: JobStatus
    stage: str
    output_type: OutputType
    source: str
    locale: str = "zh-CN"
    note_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.id,
            "status": self.status,
            "stage": self.stage,
            "output_type": self.output_type,
            "terminal": self.terminal,
            "note_id": self.note_id,
            "error": (
                {"code": self.error_code, "message": self.error_message}
                if self.error_code
                else None
            ),
        }


def create_job(output_type: OutputType, source: str, locale: str = "zh-CN") -> Job:
    job = Job(
        id=new_id("job"),
        status="queued",
        stage="claimed",
        output_type=output_type,
        source=source,
        locale=locale,
    )
    with _connect() as conn:
        conn.execute(
            "INSERT INTO jobs (id,status,stage,output_type,source,locale,created_at,updated_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (job.id, job.status, job.stage, job.output_type, job.source,
             job.locale, job.created_at, job.updated_at),
        )
    return job


def update_job(
    job_id: str,
    *,
    status: JobStatus | None = None,
    stage: str | None = None,
    note_id: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    sets, params = ["updated_at = ?"], [time.time()]
    for col, val in (
        ("status", status), ("stage", stage), ("note_id", note_id),
        ("error_code", error_code), ("error_message", error_message),
    ):
        if val is not None:
            sets.append(f"{col} = ?")
            params.append(val)
    params.append(job_id)
    with _connect() as conn:
        conn.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id = ?", params)


def get_job(job_id: str) -> Job | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        return None
    return Job(
        id=row["id"], status=row["status"], stage=row["stage"],
        output_type=row["output_type"], source=row["source"], locale=row["locale"],
        note_id=row["note_id"], error_code=row["error_code"],
        error_message=row["error_message"], created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# -------------------------------------------------------------------------- notes

@dataclass
class Note:
    id: str
    title: str
    markdown: str
    mind_map: list[dict[str, Any]] | None
    source_kind: str
    source_ref: str
    locale: str = "zh-CN"
    created_at: float = field(default_factory=time.time)

    def to_dict(self, *, include: tuple[str, ...] = ()) -> dict[str, Any]:
        data: dict[str, Any] = {
            "note_id": self.id,
            "title": self.title,
            "source_kind": self.source_kind,
            "source_ref": self.source_ref,
            "locale": self.locale,
            "created_at": self.created_at,
        }
        if "content" in include:
            data["markdown"] = self.markdown
        if "mind_map" in include:
            data["mind_map"] = self.mind_map
        if "source" in include:
            data["source_ref"] = self.source_ref
        return data


def save_note(
    *, title: str, markdown: str, mind_map: list[dict[str, Any]] | None,
    source_kind: str, source_ref: str, locale: str = "zh-CN",
) -> Note:
    note = Note(
        id=new_id("note"), title=title, markdown=markdown, mind_map=mind_map,
        source_kind=source_kind, source_ref=source_ref, locale=locale,
    )
    with _connect() as conn:
        conn.execute(
            "INSERT INTO notes (id,title,markdown,mind_map_json,source_kind,source_ref,locale,created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (note.id, note.title, note.markdown,
             json.dumps(note.mind_map, ensure_ascii=False) if note.mind_map else None,
             note.source_kind, note.source_ref, note.locale, note.created_at),
        )
    return note


def get_note(note_id: str) -> Note | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    if row is None:
        return None
    return Note(
        id=row["id"], title=row["title"], markdown=row["markdown"],
        mind_map=json.loads(row["mind_map_json"]) if row["mind_map_json"] else None,
        source_kind=row["source_kind"], source_ref=row["source_ref"],
        locale=row["locale"], created_at=row["created_at"],
    )


def list_notes(
    limit: int = 20,
    cursor: float | None = None,
    cursor_id: str | None = None,
) -> tuple[list[Note], tuple[float, str] | None]:
    """按创建时间倒序返回。

    游标是 (created_at, id)——单靠时间戳不够，同一秒内建的多条笔记时间可能完全相同，
    只用时间比较会导致重复或漏条。id 做稳定 tiebreaker。
    """
    limit = max(1, min(20, limit))
    order = "ORDER BY created_at DESC, id DESC"
    with _connect() as conn:
        if cursor is None:
            rows = conn.execute(
                f"SELECT * FROM notes {order} LIMIT ?", (limit + 1,)
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT * FROM notes WHERE created_at < ? "
                f"   OR (created_at = ? AND id < ?) {order} LIMIT ?",
                (cursor, cursor, cursor_id or "", limit + 1),
            ).fetchall()

    has_more = len(rows) > limit
    rows = rows[:limit]
    notes = [
        Note(
            id=r["id"], title=r["title"], markdown=r["markdown"],
            mind_map=json.loads(r["mind_map_json"]) if r["mind_map_json"] else None,
            source_kind=r["source_kind"], source_ref=r["source_ref"],
            locale=r["locale"], created_at=r["created_at"],
        )
        for r in rows
    ]
    next_cursor = (notes[-1].created_at, notes[-1].id) if (has_more and notes) else None
    return notes, next_cursor


# --------------------------------------------------------------------- transcripts

def get_transcript(key: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM transcripts WHERE key = ?", (key,)).fetchone()
    if row is None:
        return None
    return {
        "text": row["text"],
        "segments": json.loads(row["segments_json"]),
        "duration": row["duration"],
        "origin": row["origin"],
    }


def save_transcript(key: str, *, text: str, segments: list[dict[str, Any]],
                    duration: float, origin: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO transcripts (key,text,segments_json,duration,origin,created_at)"
            " VALUES (?,?,?,?,?,?)",
            (key, text, json.dumps(segments, ensure_ascii=False), duration, origin, time.time()),
        )


# ---------------------------------------------------------------- job materials

@dataclass
class Material:
    """作业抽取出来的原始素材，交给 AI 客户端去写笔记。"""
    job_id: str
    title: str
    body: str
    source_kind: str
    char_count: int

    def to_dict(self, *, max_chars: int | None = None) -> dict[str, Any]:
        body = self.body
        truncated = False
        if max_chars is not None and len(body) > max_chars:
            body = body[:max_chars]
            truncated = True
        data: dict[str, Any] = {
            "title": self.title,
            "source_kind": self.source_kind,
            "content": body,
            "char_count": self.char_count,
        }
        if truncated:
            data["truncated"] = True
            data["hint"] = (
                f"正文已截断到 {max_chars} 字符（原文 {self.char_count} 字符）。"
                "用 offset 参数分段读取。"
            )
        return data


def save_material(job_id: str, *, title: str, body: str, source_kind: str) -> Material:
    material = Material(
        job_id=job_id, title=title, body=body,
        source_kind=source_kind, char_count=len(body),
    )
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO job_materials"
            " (job_id,title,body,source_kind,char_count,created_at) VALUES (?,?,?,?,?,?)",
            (job_id, title, body, source_kind, material.char_count, time.time()),
        )
    return material


def get_material(job_id: str) -> Material | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM job_materials WHERE job_id = ?", (job_id,)
        ).fetchone()
    if row is None:
        return None
    return Material(
        job_id=row["job_id"], title=row["title"], body=row["body"],
        source_kind=row["source_kind"], char_count=row["char_count"],
    )
