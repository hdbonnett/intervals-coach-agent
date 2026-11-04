"""Convert the agent's light Markdown into Telegram HTML and split long messages."""
from __future__ import annotations

import html
import re

TELEGRAM_LIMIT = 4000  # hard limit is 4096; leave headroom for tags


def md_to_tg_html(text: str) -> str:
    """Escape HTML, then map a safe subset: **bold**, *italic*/_italic_, `code`, ```blocks```, [t](url), # headings."""
    blocks: list[str] = []

    def stash(m: re.Match) -> str:
        blocks.append(f"<pre>{html.escape(m.group(1).strip())}</pre>")
        return f"\x00{len(blocks) - 1}\x00"

    text = re.sub(r"```(?:\w+)?\n?(.*?)```", stash, text, flags=re.S)
    text = html.escape(text, quote=False)
    text = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)([^*\n]+?)\*(?![\w*])", r"<i>\1</i>", text)
    text = re.sub(r"(?<![\w_])_(?!\s)([^_\n]+?)_(?![\w_])", r"<i>\1</i>", text)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"(?m)^#{1,6}\s+(.+)$", r"<b>\1</b>", text)
    text = re.sub(r"(?m)^(\s*)[-*]\s+", r"\1• ", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: blocks[int(m.group(1))], text)


def split_message(text: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    """Split on paragraph, then line, boundaries so each chunk fits Telegram's limit."""
    if len(text) <= limit:
        return [text]
    chunks, current = [], ""
    for para in text.split("\n\n"):
        piece = para if not current else "\n\n" + para
        if len(current) + len(piece) <= limit:
            current += piece
            continue
        if current:
            chunks.append(current)
        current = ""
        while len(para) > limit:
            cut = para.rfind("\n", 0, limit)
            cut = cut if cut > 0 else limit
            chunks.append(para[:cut])
            para = para[cut:].lstrip("\n")
        current = para
    if current:
        chunks.append(current)
    return chunks
