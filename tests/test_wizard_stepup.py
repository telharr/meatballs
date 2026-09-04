"""Wizard save step-up: confirm password in JSON, not only a native prompt header."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from panel.security_hardening import path_needs_step_up


def test_create_and_patch_skip_middleware_step_up() -> None:
    assert path_needs_step_up("POST", "/api/servers") is False
    assert path_needs_step_up("PATCH", "/api/servers/meatballs") is False


def test_delete_and_other_writes_still_need_step_up() -> None:
    assert path_needs_step_up("DELETE", "/api/servers/meatballs") is True
    assert path_needs_step_up("POST", "/api/wipe/apply") is True


def test_probes_and_activate_stay_open() -> None:
    assert path_needs_step_up("POST", "/api/servers/probe/all") is False
    assert path_needs_step_up("POST", "/api/servers/meatballs/activate") is False


def test_api_fetch_does_not_let_options_overwrite_headers() -> None:
    """apiStepUp passes Confirm-Password headers; spreading ...options after
    headers dropped X-CSRF-Token and Content-Type on wizard save (403 then 422).
    """
    src = (Path(__file__).resolve().parents[1] / "panel" / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    start = src.index("async function api(")
    chunk = src[start : src.index("\nfunction closeStepUpModal", start)]
    fetch_start = chunk.index("await fetch(path, {")
    fetch_block = chunk[fetch_start : chunk.index("});", fetch_start)]
    assert "...options" not in fetch_block
    assert "...rest" in fetch_block
    assert fetch_block.rfind("headers") > fetch_block.find("...rest")


if __name__ == "__main__":
    test_create_and_patch_skip_middleware_step_up()
    test_delete_and_other_writes_still_need_step_up()
    test_probes_and_activate_stay_open()
    test_api_fetch_does_not_let_options_overwrite_headers()
    print("ok")
