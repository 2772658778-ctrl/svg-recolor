"""DeepSeek 客户端（Anthropic 兼容端点）。

关键坑（已验证）：
- 必须传 thinking={"type":"disabled"}，否则思考吃光 max_tokens。
- 响应偶尔泄漏 `<span class="start-end-token">` 流式标记 → sanitize_raw 剥离。
- 输出 JSON 可能被 markdown 围栏或额外文本包裹 → extract_json 稳健提取。
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

_LOADED = False


def _env() -> None:
    global _LOADED
    if not _LOADED:
        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
        _LOADED = True


def api_key() -> str:
    _env()
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        sys.exit("[llm_utils] 缺少 DEEPSEEK_API_KEY (.env)")
    return key


def api_config() -> dict:
    _env()
    return {
        "api_key": api_key(),
        "base_url": os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/anthropic"),
        "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
    }


def sanitize_raw(text: str) -> str:
    """剥离流式/渲染泄漏的标记，返回干净文本。"""
    # 旧版 resvg/流式泄漏的 span 标记
    text = re.sub(r"<span class=\"start-end-token\">.*?</span>", "", text, flags=re.S)
    text = re.sub(r"<span class=\"end-start-token\">.*?</span>", "", text, flags=re.S)
    text = re.sub(r"<span[^>]*>\s*</span>", "", text)
    text = text.replace("</span>", "").replace("<span>", "")
    return text.strip()


def ask_deepseek(
    system: str,
    user: str,
    *,
    max_tokens: int = 8000,
    temperature: float = 0.2,
    client=None,
) -> str:
    """单次 DeepSeek 调用，返回净化后的文本。"""
    from anthropic import Anthropic

    cfg = api_config()
    c = client or Anthropic(api_key=cfg["api_key"], base_url=cfg["base_url"])
    resp = c.messages.create(
        model=cfg["model"],
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
        extra_body={"thinking": {"type": "disabled"}},
    )
    parts = []
    for block in resp.content:
        if getattr(block, "type", "") == "text":
            parts.append(block.text)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return sanitize_raw("\n".join(parts))


def extract_json(text: str) -> dict:
    """从 LLM 文本中稳健提取第一个 JSON 对象（剥 markdown 围栏/前后废话）。"""
    # 优先尝试 code fence
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
    if fence:
        return json.loads(fence.group(1))
    # 尝试第一个 { 到最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"未找到 JSON 对象。原文：\n{text[:500]}")
    return json.loads(text[start : end + 1])


def parse_sections(text: str) -> dict[str, str]:
    """把 LLM 的分节文本解析成 {标题: 正文}（供无 JSON 输出时用）。"""
    sections: dict[str, str] = {}
    cur = None
    for line in text.splitlines():
        m = re.match(r"^\s*(?:#+\s*)?\*?\*?([A-Za-z0-9_一-鿿\s()\-（）]+)\*?\*?\s*[:：]\s*$", line)
        if m and len(m.group(1).strip()) <= 40:
            cur = m.group(1).strip()
            sections.setdefault(cur, "")
            continue
        if cur:
            sections[cur] += line + "\n"
    return {k: v.strip() for k, v in sections.items()}
