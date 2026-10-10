"""验证 MCP server 能通过 stdio 正常握手并响应工具调用。

这不是单元测试——它真的拉起子进程，走完整的 MCP 协议握手。
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


async def main() -> int:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC)
    env["PYTHONIOENCODING"] = "utf-8"
    env["SEAGULL_NOTES_HOME"] = str(ROOT)

    params = StdioServerParameters(
        command=sys.executable,
        args=["-X", "utf8", "-m", "seagull_notes.server"],
        env=env,
        cwd=str(ROOT),
    )

    print("[1] 启动 stdio 子进程并握手……")
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            info = getattr(init, "server_info", None) or getattr(init, "serverInfo")
            print(f"    ✓ 已连接: {info.name} v{info.version}")

            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            print(f"    ✓ 工具数: {len(names)}")
            for n in sorted(names):
                print(f"        - {n}")

            print("\n[2] 调 runtime_info……")
            result = await session.call_tool("runtime_info", {})
            payload = result.content[0].text
            print("    " + payload.replace("\n", "\n    ")[:600])

            print("\n[3] 调 create_note（纯文本，走降级模式）……")
            created = await session.call_tool("create_note", {
                "content": "敏捷开发强调快速迭代和持续交付。每个迭代周期通常为两到四周。"
                           "站会是每日同步机制，用于暴露阻塞问题。回顾会用于改进流程。",
                "output_type": "detailed_markdown",
            })
            import json

            created_info = json.loads(created.content[0].text)
            job_id = created_info["job_id"]
            print(f"    ✓ job_id = {job_id}")
            print(f"    ✓ 建议 {created_info['poll_after_seconds']} 秒后开始轮询")

            print("\n[4] 轮询 get_generation_job……")
            for attempt in range(20):
                await asyncio.sleep(1.0)
                r = await session.call_tool("get_generation_job", {"job_id": job_id})
                status = json.loads(r.content[0].text)
                print(f"    [{attempt + 1}] status={status['status']} stage={status['stage']}")
                if status.get("terminal"):
                    note_id = status.get("note_id")
                    break
            else:
                print("    ✗ 轮询超时")
                return 1

            if status["status"] != "completed":
                print(f"    ✗ 作业未成功: {status}")
                return 1
            print(f"    ✓ 完成，note_id = {note_id}")

            print("\n[5] 调 get_note……")
            r = await session.call_tool("get_note", {"note_id": note_id})
            note = json.loads(r.content[0].text)
            print(f"    ✓ 标题: {note['title']}")
            print(f"    ✓ 正文 {len(note.get('markdown', ''))} 字符")
            print(f"    ✓ 脑图节点: {len(note.get('mind_map') or [])} 个根")

            print("\n[6] 调 export_note（markdown）……")
            r = await session.call_tool("export_note", {"note_id": note_id, "format": "markdown"})
            exported = json.loads(r.content[0].text)
            print(f"    ✓ 落盘: {exported['download_path']}")

            print("\n[7] 调 export_note（svg）……")
            r = await session.call_tool("export_note", {"note_id": note_id, "format": "svg"})
            exported = json.loads(r.content[0].text)
            print(f"    ✓ 落盘: {exported['download_path']}")

            print("\n[8] 调 list_notes……")
            r = await session.call_tool("list_notes", {"limit": 5})
            listing = json.loads(r.content[0].text)
            print(f"    ✓ 共 {listing['count']} 条，next_cursor={listing['next_cursor']}")

            print("\n[9] 测错误路径：不存在的 job……")
            r = await session.call_tool("get_generation_job", {"job_id": "job_不存在"})
            err = json.loads(r.content[0].text)
            assert "error" in err, "应该返回结构化错误"
            print(f"    ✓ 正确返回错误: {err['error']['code']}")

    print("\n" + "=" * 60)
    print("全部通过：MCP stdio 链路、工具调用、作业状态机、导出都正常。")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
