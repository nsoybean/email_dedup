"""Parse plain-text email-thread snapshots into ordered messages."""

from __future__ import annotations

import re

from email_dedup.models import ParsedMessage, ParsedThread

# Quoted older messages begin with "| From:" or "> From:" / ">  From:".
# A dash separator may precede the quoted block.
_QUOTED_MESSAGE_START = re.compile(
    r"(?m)^(?:-{20,}\s*\n)?(?:\|\s*|>\s*)From:\s"
)

_HEADER_NAME = re.compile(r"^([A-Za-z0-9-]+):\s*(.*)$")
_PIPE_PREFIX = re.compile(r"^\|\s?")
_GT_PREFIX = re.compile(r"^>\s*")


class ParseError(ValueError):
    """Raised when a thread snapshot cannot be parsed reliably."""


def parse_thread(content: str) -> ParsedThread:
    """Parse a newest-first thread snapshot into ordered Message-ID messages."""
    if not content.strip():
        raise ParseError("content must not be blank")

    blocks = _split_message_blocks(content)
    messages = tuple(_parse_message_block(block, index) for index, block in enumerate(blocks))
    if not messages:
        raise ParseError("no messages found")
    return ParsedThread(messages=messages)


def _split_message_blocks(content: str) -> list[str]:
    matches = list(_QUOTED_MESSAGE_START.finditer(content))
    if not matches:
        return [content.strip("\n")]

    blocks: list[str] = []
    first_end = matches[0].start()
    top = content[:first_end].strip("\n")
    if top.strip():
        blocks.append(top)

    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        block = content[start:end].strip("\n")
        block = re.sub(r"^-{20,}\s*\n?", "", block)
        if block.strip():
            blocks.append(block)

    if not blocks:
        raise ParseError("no message blocks found")
    return blocks


def _parse_message_block(block: str, index: int) -> ParsedMessage:
    unquoted = _strip_quote_prefixes(block)
    headers, body = _split_headers_and_body(unquoted)
    if not headers:
        raise ParseError(f"message {index} has no headers")

    message_id = _normalize_message_id(headers.get("message-id"))
    if message_id is None:
        raise ParseError(f"message {index} is missing Message-ID")

    return ParsedMessage(message_id=message_id, headers=headers, body=body)


def _strip_quote_prefixes(block: str) -> str:
    lines = block.splitlines()
    if not lines:
        return block

    first = lines[0]
    if first.startswith("|"):
        return "\n".join(_PIPE_PREFIX.sub("", line) for line in lines)
    if first.lstrip().startswith(">") or first.startswith(">"):
        return "\n".join(_GT_PREFIX.sub("", line) for line in lines)
    return block


def _split_headers_and_body(text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    headers: dict[str, str] = {}
    body_start = 0
    current_name: str | None = None

    for index, line in enumerate(lines):
        # Near-duplicates often insert blank lines between headers.
        if line.strip() == "":
            continue

        match = _HEADER_NAME.match(line)
        if match:
            name = match.group(1).lower()
            value = match.group(2).strip()
            headers[name] = value
            current_name = name
            continue

        # Rare folded header continuation.
        if current_name is not None and line[:1].isspace():
            headers[current_name] = f"{headers[current_name]} {line.strip()}".strip()
            continue

        body_start = index
        break
    else:
        body_start = len(lines)

    body = "\n".join(lines[body_start:]).strip("\n")
    return headers, body


def _normalize_message_id(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = raw.strip()
    return value or None
