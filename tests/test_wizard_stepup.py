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


if __name__ == "__main__":
    test_create_and_patch_skip_middleware_step_up()
    test_delete_and_other_writes_still_need_step_up()
    test_probes_and_activate_stay_open()
    print("ok")
