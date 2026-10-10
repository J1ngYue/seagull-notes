"""验证"素材模式"全流程：AI 客户端不需要任何 API key 就能出笔记。

模拟真实 AI 客户端的行为：
  create_note(素材模式) → 轮询 → get_material → 自己写笔记 → save_note → export
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


async def main() -> int:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["SEAGULL_NOTES_HOME"] = tempfile.mkdtemp(prefix="seagull-material-check-")
    env["SEAGULL_NOTES_LLM_API_KEY"] = ""
    env["ANTHROPIC_API_KEY"] = ""
    params = StdioServerParameters(
        command=sys.executable,
        args=["-X", "utf8", "-m", "seagull_notes.server"],
        env=env,
        cwd=str(ROOT),
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print(f"[0] 已连接，工具 {len(tools.tools)} 个")

            # --- 1. 抽素材 ---
            print("\n[1] create_note（素材模式，默认）")
            r = await session.call_tool("create_note", {
                "content": "视频笔记应保留完整来源，按照主题整理关键观点，并明确区分原始画面与示意图。",
            })
            created = json.loads(r.content[0].text)
            job_id = created["job_id"]
            print(f"    job_id={job_id}  output_type={created['output_type']}")
            print(f"    下一步提示: {created['next_step']}")

            # --- 2. 轮询 ---
            print("\n[2] 轮询到终端状态")
            for i in range(60):
                await asyncio.sleep(1.5)
                r = await session.call_tool("get_generation_job", {"job_id": job_id})
                st = json.loads(r.content[0].text)
                print(f"    [{i+1}] {st['status']} / {st['stage']}")
                if st.get("terminal"):
                    break
            else:
                print("    ✗ 轮询超时")
                return 1

            if st["status"] != "completed":
                print(f"    ✗ 失败: {st}")
                return 1
            if st["stage"] != "awaiting_note":
                print(f"    ✗ stage 应该是 awaiting_note，实际 {st['stage']}")
                return 1
            print("    ✓ 素材就绪")

            # --- 3. 取素材 ---
            print("\n[3] get_material")
            r = await session.call_tool("get_material", {"job_id": job_id})
            material = json.loads(r.content[0].text)
            print(f"    标题: {material['title']}")
            print(f"    字数: {material['char_count']}")
            print(f"    分段: has_more={material['has_more']}")
            print(f"    素材: {material['content'][:120]}")

            # --- 4. AI 写笔记（这里用固定内容模拟真实客户端的产出）---
            print("\n[4] 客户端自己写笔记（不需要 API key）")
            markdown = """# 梯度下降：机器学习的核心优化算法

梯度下降是机器学习中最基础的优化方法，通过**沿负梯度方向迭代更新参数**来逼近损失函数的最小值。

## 核心机制

- **更新方向**：沿损失函数的负梯度方向
- **目标**：逐步逼近最小值
- **学习率**：决定每一步的步长

## 学习率的取舍

| 设置 | 后果 |
|---|---|
| 过大 | 震荡，无法收敛 |
| 过小 | 收敛缓慢 |

> 学习率决定了每一步走多大。

## 实践要点

实际训练中需要根据问题规模和数据特性选择合适的学习率策略。"""

            mind_map = [
                {
                    "title": "梯度下降",
                    "children": [
                        {"title": "核心思想", "children": [
                            {"title": "负梯度方向"},
                            {"title": "逐步逼近最小值"},
                        ]},
                        {"title": "学习率", "children": [
                            {"title": "过大会震荡"},
                            {"title": "过小收敛慢"},
                        ]},
                        {"title": "实践要点", "children": [
                            {"title": "按数据特性选择"},
                        ]},
                    ],
                }
            ]

            r = await session.call_tool("save_note", {
                "job_id": job_id,
                "markdown": markdown,
                "mind_map": mind_map,
                "title": "梯度下降：机器学习的核心优化算法",
            })
            saved = json.loads(r.content[0].text)
            if "error" in saved:
                print(f"    ✗ {saved['error']}")
                return 1
            note_id = saved["note_id"]
            print(f"    ✓ note_id={note_id}")
            print(f"    ✓ 正文 {saved['markdown_chars']} 字符，脑图 {saved['mind_map_nodes']} 个节点")

            # --- 5. 导出 ---
            print("\n[5] export_note")
            for fmt in ("markdown", "svg", "json"):
                r = await session.call_tool("export_note", {"note_id": note_id, "format": fmt})
                out = json.loads(r.content[0].text)
                if "error" in out:
                    print(f"    ✗ {fmt}: {out['error']}")
                    return 1
                path = out.get("download_path") or f"<inline, {len(out.get('tree', []))} 根>"
                print(f"    ✓ {fmt}: {path}")

            # --- 6. 读回确认 ---
            print("\n[6] get_note 读回")
            r = await session.call_tool("get_note", {"note_id": note_id})
            note = json.loads(r.content[0].text)
            assert note["title"] == "梯度下降：机器学习的核心优化算法"
            assert "梯度下降" in note["markdown"]
            print(f"    ✓ 标题和正文都对得上")

    print("\n" + "=" * 62)
    print("素材模式全流程验证通过 —— 全程零 API key。")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
