"""命令行：不经过 MCP 直接跑管线，方便调试和验证。

    python -m seagull_notes.cli run "https://www.bilibili.com/video/BVxxxx"
    python -m seagull_notes.cli run ./lecture.mp4 --type mind_map
    python -m seagull_notes.cli list
    python -m seagull_notes.cli show note_xxx
    python -m seagull_notes.cli export note_xxx --format svg
    python -m seagull_notes.cli prepare-model
    python -m seagull_notes.cli info
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

from . import asr, config, export, pipeline, storage


def _fmt_duration(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}h{m}m{s}s" if h else (f"{m}m{s}s" if m else f"{s}s")


async def cmd_run(args: argparse.Namespace) -> int:
    config.ensure_dirs()
    job = storage.create_job(
        output_type=args.type, source=args.source, locale=args.locale,
    )
    print(f"[job] {job.id}")
    print(f"[src] {args.source}")
    print(f"[out] {args.type}")
    print("-" * 60)

    started = time.time()
    seen_stage = ""

    async def watch() -> None:
        nonlocal seen_stage
        while True:
            current = storage.get_job(job.id)
            if current and current.stage != seen_stage:
                seen_stage = current.stage
                elapsed = time.time() - started
                print(f"  [{elapsed:6.1f}s] {current.stage}")
            await asyncio.sleep(1.0)

    watcher = asyncio.create_task(watch())
    try:
        result = await pipeline.run_job(job.id)
    finally:
        watcher.cancel()

    elapsed = time.time() - started
    print("-" * 60)

    if result.status != "completed":
        final = storage.get_job(job.id)
        print(f"[FAILED] {result.status}  ({_fmt_duration(elapsed)})")
        if final and final.error_message:
            print(f"  code: {final.error_code}")
            print(f"  msg : {final.error_message}")
        return 1

    # 素材模式：抽出内容就完事，不生成笔记
    if result.stage == storage.AWAITING_NOTE_STAGE:
        material = storage.get_material(job.id)
        print(f"[OK] {_fmt_duration(elapsed)}  素材模式")
        if material:
            print(f"[job] {job.id}")
            print(f"[title] {material.title}")
            print(f"[source] {material.source_kind}")
            print(f"[chars] {material.char_count}")
            print()
            if args.print_material:
                print("=" * 60)
                print(material.body)
            else:
                print("素材已就绪。两种用法：")
                print(f"  · 交给 AI 客户端：把 job_id ({job.id}) 给它，让它调 get_material")
                print(f"  · 命令行看内容：加 --print-material 参数")
        return 0

    note = storage.get_note(result.note_id or "")
    print(f"[OK] {_fmt_duration(elapsed)}  生成器={result.generator}")
    if note:
        print(f"[note] {note.id}")
        print(f"[title] {note.title}")
        print(f"[markdown] {len(note.markdown)} 字符")
        if note.mind_map:
            def count(nodes: list) -> int:
                return sum(1 + count(n.get("children") or []) for n in nodes)
            print(f"[mindmap] {count(note.mind_map)} 个节点")

    md = export.dispatch(note, "markdown") if note else None
    if md:
        print(f"[saved] {md['download_path']}")

    if note and note.mind_map:
        svg = export.dispatch(note, "svg")
        print(f"[svg]   {svg['download_path']}")
        print(f"[html]  {svg['html_path']}")

    if args.print_body and note:
        print("\n" + "=" * 60)
        print(note.markdown)
    return 0


async def cmd_list(args: argparse.Namespace) -> int:
    notes, _ = storage.list_notes(limit=args.limit)
    if not notes:
        print("(没有笔记)")
        return 0
    print(f"{'note_id':<28} {'title':<30} {'kind':<10} created")
    for n in notes:
        ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(n.created_at))
        title = n.title[:28] + "…" if len(n.title) > 28 else n.title
        print(f"{n.id:<28} {title:<30} {n.source_kind:<10} {ts}")
    return 0


async def cmd_show(args: argparse.Namespace) -> int:
    note = storage.get_note(args.note_id)
    if note is None:
        print(f"笔记不存在：{args.note_id}", file=sys.stderr)
        return 1
    print(f"# {note.title}")
    print(f"来源: [{note.source_kind}] {note.source_ref}")
    print("-" * 60)
    print(note.markdown)
    if note.mind_map:
        print("\n" + "=" * 60)
        print("脑图树：")

        def dump(nodes: list, indent: int = 0) -> None:
            for n in nodes:
                print("  " * indent + f"- {n['title']}")
                dump(n.get("children") or [], indent + 1)

        dump(note.mind_map)
    return 0


async def cmd_export(args: argparse.Namespace) -> int:
    note = storage.get_note(args.note_id)
    if note is None:
        print(f"笔记不存在：{args.note_id}", file=sys.stderr)
        return 1
    result = export.dispatch(note, args.format)
    for key, value in result.items():
        if key == "content" and isinstance(value, str) and len(value) > 500:
            print(f"{key}: <{len(value)} 字符，省略>")
        elif key == "tree":
            print(f"{key}:")
            print(json_indent(value))
        else:
            print(f"{key}: {value}")
    return 0


def json_indent(value: object) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, indent=2)


async def cmd_prepare_model(args: argparse.Namespace) -> int:
    print(f"[model] {config.ASR_MODEL}")
    print(f"[dest]  {config.HF_HUB_CACHE}")
    if asr.model_is_cached():
        print("[status] 已缓存，无需下载")
        return 0
    print("[status] 开始下载……大文件，耐心等")
    try:
        path = await asr.prefetch_model()
    except Exception as exc:                                    # noqa: BLE001
        print(f"[ERROR] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"[done] {path}")
    return 0


async def cmd_info(args: argparse.Namespace) -> int:
    from . import generate

    print(f"project home : {config.HOME}")
    print(f"db           : {config.DB_PATH}")
    print(f"asr model    : {config.ASR_MODEL} ({config.ASR_DEVICE}/{config.ASR_COMPUTE_TYPE})")
    print(f"model cached : {asr.model_is_cached()}")
    print(f"hf cache     : {config.HF_HUB_CACHE}")
    print(f"llm          : {'已配置 ' + config.LLM_MODEL if config.LLM_API_KEY else '未配置（走降级模式）'}")
    print(f"artifacts    : {config.ARTIFACT_DIR}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="seagull-notes", description="视频/文章 → 笔记 + 脑图")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="跑一条完整管线")
    p_run.add_argument("source", help="视频链接 / 网页链接 / 本地文件路径 / 文本")
    p_run.add_argument("--type", default="material",
                       choices=["material", "long_image", "mind_map",
                                "detailed_markdown", "transcript"])
    p_run.add_argument("--locale", default="zh-CN")
    p_run.add_argument("--print-body", action="store_true", help="跑完打印完整正文")
    p_run.add_argument("--print-material", action="store_true",
                       help="素材模式下打印抽出来的内容")
    p_run.set_defaults(func=cmd_run)

    p_list = sub.add_parser("list", help="列出笔记")
    p_list.add_argument("--limit", type=int, default=20)
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="查看笔记")
    p_show.add_argument("note_id")
    p_show.set_defaults(func=cmd_show)

    p_export = sub.add_parser("export", help="导出笔记")
    p_export.add_argument("note_id")
    p_export.add_argument("--format", default="markdown",
                          choices=["markdown", "svg", "png", "json", "source"])
    p_export.set_defaults(func=cmd_export)

    p_model = sub.add_parser("prepare-model", help="下载 ASR 模型到本地")
    p_model.set_defaults(func=cmd_prepare_model)

    p_info = sub.add_parser("info", help="显示配置")
    p_info.set_defaults(func=cmd_info)

    return parser


def main(argv: list[str] | None = None) -> int:
    # Windows 控制台默认 GBK，中文输出会乱码，强制切 UTF-8
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(args.func(args))
    except KeyboardInterrupt:
        print("\n中断", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
