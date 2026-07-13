from pathlib import Path

import pytest

from email_dedup.eval_labels import eval_label_from_path, normalize_eval_stem
from email_dedup.parser import ParseError, parse_thread

EVAL_DIR = Path(__file__).resolve().parents[2] / "data" / "eval"


def test_parse_single_message_root() -> None:
    thread = parse_thread((EVAL_DIR / "1.txt").read_text(encoding="utf-8"))

    assert len(thread.messages) == 1
    assert thread.message_ids == ("<bd00efc44ea59bc0@starkindustries.com>",)


def test_parse_pipe_quoted_chain() -> None:
    thread = parse_thread((EVAL_DIR / "1_0.txt").read_text(encoding="utf-8"))

    assert thread.message_ids == (
        "<33c9e4f89c8e7127@cyberdyne.systems>",
        "<bd00efc44ea59bc0@starkindustries.com>",
    )


def test_parse_double_space_gt_quotes() -> None:
    thread = parse_thread((EVAL_DIR / "6_0b.txt").read_text(encoding="utf-8"))

    assert len(thread.messages) == 2
    assert thread.message_ids[0] == "<1fe3851d203e8599@initech.com>"
    assert thread.message_ids[1] == "<a810a1821b67baee@starkindustries.com>"


def test_parse_to_first_top_headers() -> None:
    thread = parse_thread((EVAL_DIR / "14_0c.txt").read_text(encoding="utf-8"))

    assert len(thread.messages) == 2
    assert "message-id" in thread.messages[0].headers
    assert thread.messages[0].headers["from"].startswith("Mona Lopez")


def test_parse_quote_only_without_dash_separator() -> None:
    thread = parse_thread((EVAL_DIR / "12_1_0_0.txt").read_text(encoding="utf-8"))

    assert len(thread.messages) == 4
    assert all(message_id.startswith("<") for message_id in thread.message_ids)


def test_variants_share_message_id_sequence() -> None:
    base = parse_thread((EVAL_DIR / "1_0_0.txt").read_text(encoding="utf-8"))
    variant = parse_thread((EVAL_DIR / "1_0_0b.txt").read_text(encoding="utf-8"))

    assert base.message_ids == variant.message_ids


def test_headers_tolerate_blank_lines_between_fields() -> None:
    thread = parse_thread((EVAL_DIR / "12_1b.txt").read_text(encoding="utf-8"))

    assert len(thread.messages) == 2
    assert thread.message_ids[1] == "<bfcf837cb0c234a6@initech.com>"


def test_missing_message_id_raises() -> None:
    with pytest.raises(ParseError, match="Message-ID"):
        parse_thread("From: a@example.com\nTo: b@example.com\n\nHello\n")


def test_blank_content_raises() -> None:
    with pytest.raises(ParseError, match="blank"):
        parse_thread("   \n")


@pytest.mark.parametrize(
    ("stem", "expected"),
    [
        ("1", "1"),
        ("1_0_0b", "1_0_0"),
        ("12_1_0_0e", "12_1_0_0"),
        ("15_0_0d", "15_0_0"),
    ],
)
def test_normalize_eval_stem(stem: str, expected: str) -> None:
    assert normalize_eval_stem(stem) == expected


def test_eval_label_expected_message_count() -> None:
    label = eval_label_from_path(Path("1_0_0b.txt"))

    assert label.canonical_label == "1_0_0"
    assert label.parent_label == "1_0"
    assert label.expected_message_count == 3
