from __future__ import annotations

from rvgen.rvopen import command_for, url_for


def test_url_for_encodes_file_and_line():
    url = url_for("rtl/gen/uart.v", 42)
    assert url == "rvgen://open?file=rtl%2Fgen%2Fuart.v&line=42"


def test_url_for_optional_node_id():
    url = url_for("rvgen.yaml", 7, "mod:uart")
    assert "line=7" in url
    assert "node=mod%3Auart" in url


def test_command_for_falls_back_to_code():
    assert command_for("rvgen.yaml", 3) == ["code", "--goto", "rvgen.yaml:3"]
    assert command_for("rvgen.yaml") == ["code", "--goto", "rvgen.yaml"]
