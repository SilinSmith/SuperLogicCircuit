from __future__ import annotations

from slc.rvopen import command_for, url_for


def test_url_for_encodes_file_and_line():
    url = url_for("rtl/gen/uart.v", 42)
    assert url == "slc://open?file=rtl%2Fgen%2Fuart.v&line=42"


def test_url_for_optional_node_id():
    url = url_for("slc.yaml", 7, "mod:uart")
    assert "line=7" in url
    assert "node=mod%3Auart" in url


def test_command_for_falls_back_to_code():
    assert command_for("slc.yaml", 3) == ["code", "--goto", "slc.yaml:3"]
    assert command_for("slc.yaml") == ["code", "--goto", "slc.yaml"]
