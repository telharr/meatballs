"""Safehouse command protocol and overlap helpers."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from panel.safehouses import (
    decode_members,
    encode_cmd,
    encode_members,
    parse_cmd_blocks,
    percent_decode,
    percent_encode,
    rects_overlap,
    status_note,
)


def test_percent_roundtrip_unicode() -> None:
    raw = "Приват Bob's house"
    assert percent_decode(percent_encode(raw)) == raw


def test_encode_create_block() -> None:
    block = encode_cmd(
        "create",
        x=12000,
        y=7000,
        w=12,
        h=8,
        nonce="abc123",
        owner="Bob",
        title="West Point Depot",
        members=["Alice", "Eve"],
    )
    parsed = parse_cmd_blocks(block)
    assert len(parsed) == 1
    cmd = parsed[0]
    assert cmd["op"] == "create"
    assert cmd["nonce"] == "abc123"
    assert cmd["x"] == "12000"
    assert percent_decode(cmd["owner"]) == "Bob"
    assert percent_decode(cmd["title"]) == "West Point Depot"
    assert decode_members(cmd["members"]) == ["Alice", "Eve"]


def test_overlap_true_and_false() -> None:
    a = {"x": 100, "y": 100, "w": 10, "h": 10}
    b = {"x": 105, "y": 105, "w": 10, "h": 10}
    c = {"x": 200, "y": 200, "w": 5, "h": 5}
    assert rects_overlap(a, b)
    assert not rects_overlap(a, c)


def test_members_comma_names() -> None:
    encoded = encode_members(["Alice", "Bob Jr"])
    assert decode_members(encoded) == ["Alice", "Bob Jr"]


def test_status_note_waiting_restart() -> None:
    note = status_note(
        bridge={"loaded": False},
        install={"ready": True, "files_ok": True, "ini_ok": True},
        dump_live=False,
    )
    assert "уже на диске" in note
    assert "рестарт" in note.lower()


def test_status_note_missing_mod() -> None:
    note = status_note(
        bridge={"loaded": False},
        install={"ready": False, "files_ok": False, "ini_ok": False},
        dump_live=False,
    )
    assert "не найден" in note


if __name__ == "__main__":
    test_percent_roundtrip_unicode()
    test_encode_create_block()
    test_overlap_true_and_false()
    test_members_comma_names()
    test_status_note_waiting_restart()
    test_status_note_missing_mod()
    print("ok")
