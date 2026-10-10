"""笔记生成：转写稿/正文 → Markdown + 脑图树。

没有配 LLM 时自动降级成"结构化输出"——照样产出可用的 Markdown 和脑图，
不会因为缺 key 就整个跑不动。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from . import config

OutputType = Literal["long_image", "mind_map", "detailed_markdown", "transcript"]

STYLE_HINTS: dict[str, str] = {
    "auto": "根据内容自动选择最合适的组织方式",
    "fresh_note": "清新笔记风：要点清晰、层次分明、适合快速浏览",
    "business_case": "商业案例分析风：背景、问题、方案、结论四段式",
    "tech_tool": "技术工具风：概念、原理、用法、注意事项",
    "course_handout": "课程讲义风：知识点、定义、例子、小结",
    "xiaohongshu_seed": "小红书种草风：口语化、有情绪、分点短句",
}


@dataclass
class GeneratedNote:
    title: str
    markdown: str
    mind_map: list[dict[str, Any]]
    generator: str          # "llm" | "fallback"


SYSTEM_PROMPT = """你是一个专业的内容笔记整理助手。用户会给你一段视频转写稿或文章正文，你要把它整理成结构化的学习笔记。

输出要求：
1. 必须是合法的 JSON，不要包在 markdown 代码块里，不要有任何额外文字。
2. JSON 结构固定为：
{
  "title": "笔记标题，10-25字，概括核心内容",
  "markdown": "完整的 Markdown 正文",
  "mind_map": [脑图树节点数组]
}

3. markdown 字段要求：
   - 用 # 一级标题开头
   - 用 ## 和 ### 分层组织
   - 关键概念用 **加粗**
   - 有步骤/流程/并列项时用列表
   - 适当使用引用块 > 标注重点原话
   - 长度根据内容量决定，详细但不要注水

4. mind_map 字段要求：
   - 是树形结构，每个节点格式为 {"title": "节点标题", "children": [...]}
   - 根节点只有一个，对应主题
   - 第二层是主要分支（3-7个为宜）
   - 第三层是具体要点
   - 节点标题要短，10字以内，不要整句话
   - 叶子节点可以省略 children 字段

5. 如果转写稿里有口语、重复、语气词，要清理掉，提炼成书面表达。
6. 如果内容中有明确的数字、人名、产品名、时间点，要保留。"""


def _strip_code_fence(text: str) -> str:
    """LLM 有时会把 JSON 包在 ```json ``` 里，扒掉。"""
    text = text.strip()
    fence = re.match(r"^```(?:json)?\s*\n(.*?)\n```\s*$", text, re.S)
    if fence:
        return fence.group(1).strip()
    return text


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = _strip_code_fence(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # 退一步：找出最外层花括号
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end > start:
        return json.loads(cleaned[start:end + 1])
    raise ValueError("LLM 返回的内容不是合法 JSON")


def _normalize_tree(nodes: Any) -> list[dict[str, Any]]:
    """把 LLM 给的树洗干净：保证 title 存在、children 是列表或不存在。"""
    if not isinstance(nodes, list):
        return []

    def clean(node: Any) -> dict[str, Any] | None:
        if isinstance(node, str):
            return {"title": node.strip()}
        if not isinstance(node, dict):
            return None
        title = str(node.get("title") or node.get("name") or node.get("label") or "").strip()
        if not title:
            return None
        cleaned: dict[str, Any] = {"title": title}
        children = node.get("children")
        if isinstance(children, list):
            kids = [c for c in (clean(x) for x in children) if c]
            if kids:
                cleaned["children"] = kids
        return cleaned

    return [c for c in (clean(n) for n in nodes) if c]


# --------------------------------------------------------------- LLM 调用

async def _call_anthropic(prompt: str, system: str) -> str:
    payload = {
        "model": config.LLM_MODEL,
        "max_tokens": 8192,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "x-api-key": config.LLM_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(
            f"{config.LLM_BASE_URL.rstrip('/')}/v1/messages", json=payload, headers=headers
        )
        resp.raise_for_status()
        data = resp.json()
    return "".join(block.get("text", "") for block in data.get("content", []))


async def _call_openai_compatible(prompt: str, system: str) -> str:
    payload = {
        "model": config.LLM_MODEL,
        "max_tokens": 8192,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    }
    headers = {
        "Authorization": f"Bearer {config.LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(
            f"{config.LLM_BASE_URL.rstrip('/')}/v1/chat/completions",
            json=payload, headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
    return data["choices"][0]["message"]["content"]


async def _call_llm(prompt: str, system: str) -> str:
    base = config.LLM_BASE_URL.lower()
    if "anthropic" in base:
        return await _call_anthropic(prompt, system)
    return await _call_openai_compatible(prompt, system)


# --------------------------------------------------------------- 降级模式

def _fallback_generate(content: str, title: str, output_type: OutputType,
                       style: str, locale: str) -> GeneratedNote:
    """没配 LLM 时的兜底：按段落切分，做成可用的结构化笔记。"""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]
    if not paragraphs:
        paragraphs = [ln.strip() for ln in content.splitlines() if ln.strip()]

    # 按每 5 段归成一个小节
    buckets: list[list[str]] = []
    chunk = 5
    for i in range(0, len(paragraphs), chunk):
        buckets.append(paragraphs[i:i + chunk])

    md_lines = [f"# {title}", ""]
    tree_children: list[dict[str, Any]] = []
    for idx, bucket in enumerate(buckets, 1):
        section_title = f"第 {idx} 部分"
        md_lines.append(f"## {section_title}")
        md_lines.append("")
        for para in bucket:
            md_lines.append(f"- {para}")
        md_lines.append("")
        tree_children.append({
            "title": section_title,
            "children": [{"title": p[:18]} for p in bucket[:6]],
        })

    note = GeneratedNote(
        title=title,
        markdown="\n".join(md_lines).strip(),
        mind_map=[{"title": title, "children": tree_children}],
        generator="fallback",
    )
    return note


# --------------------------------------------------------------- 主入口

def _build_prompt(content: str, output_type: OutputType, style: str,
                  locale: str, source_title: str) -> str:
    lang = "中文" if locale.startswith("zh") else "English"
    style_hint = STYLE_HINTS.get(style, STYLE_HINTS["auto"])

    focus = {
        "long_image": "内容要适合排版成长图，段落短、要点密、视觉层次强。",
        "mind_map": "脑图树要尽量细致，分支可以多到四层，覆盖全部要点。",
        "detailed_markdown": "Markdown 要尽量详尽，保留所有重要细节和上下文。",
        "transcript": "以忠实还原为主，不要过度提炼。",
    }.get(output_type, "")

    return f"""请把下面的内容整理成{lang}学习笔记。

内容来源标题：{source_title}
输出语言：{lang}
风格要求：{style_hint}
重点提示：{focus}

=== 内容开始 ===
{content}
=== 内容结束 ===

请严格按照系统提示里的 JSON 格式输出。"""


async def generate(
    content: str,
    *,
    title: str = "未命名内容",
    output_type: OutputType = "detailed_markdown",
    style: str = "auto",
    locale: str = "zh-CN",
) -> GeneratedNote:
    """生成笔记。有 LLM 走 LLM，没配就自动降级。"""
    if not config.LLM_API_KEY:
        return _fallback_generate(content, title, output_type, style, locale)

    # 超长内容截断，避免爆 token；转写稿通常几万字，留够余量
    max_chars = 120_000
    trimmed = content[:max_chars]
    if len(content) > max_chars:
        trimmed += f"\n\n[内容过长，已截断，原文共 {len(content)} 字]"

    prompt = _build_prompt(trimmed, output_type, style, locale, title)

    try:
        raw = await _call_llm(prompt, SYSTEM_PROMPT)
        data = _extract_json(raw)
    except Exception as exc:                                    # noqa: BLE001
        note = _fallback_generate(content, title, output_type, style, locale)
        note.generator = f"fallback(llm_error: {type(exc).__name__})"
        return note

    md = str(data.get("markdown") or "").strip()
    tree = _normalize_tree(data.get("mind_map"))

    if not md:
        note = _fallback_generate(content, title, output_type, style, locale)
        note.generator = "fallback(empty_llm_output)"
        return note

    return GeneratedNote(
        title=str(data.get("title") or title).strip(),
        markdown=md,
        mind_map=tree or [{"title": str(data.get("title") or title)}],
        generator="llm",
    )
