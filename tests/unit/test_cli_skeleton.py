from __future__ import annotations

import json
import shutil

from rvgen.cli import main


def test_version_exits_zero(capsys) -> None:
    assert main(["--version"]) == 0
    assert "rvgen 0.1.0" in capsys.readouterr().out


def test_help_exits_zero(capsys) -> None:
    assert main(["--help"]) == 0
    out = capsys.readouterr().out
    assert "init" in out
    assert "doctor" in out
    assert "migrate" in out


def test_missing_command_is_usage_error(capsys) -> None:
    assert main([]) == 1
    err = capsys.readouterr().err
    assert "E00" in err
    assert "CLI 用法错误" in err


def test_unknown_command_is_usage_error(capsys) -> None:
    assert main(["bogus"]) == 1
    assert "E00" in capsys.readouterr().err


def test_doctor_json_shape(capsys) -> None:
    code = main(["doctor", "--json"])
    assert code in (0, 3)
    payload = json.loads(capsys.readouterr().out)
    assert "ok" in payload
    names = {tool["name"] for tool in payload["tools"]}
    assert {"python", "iverilog", "node", "npm", "git"} <= names
    if shutil.which("iverilog"):
        iverilog = next(tool for tool in payload["tools"] if tool["name"] == "iverilog")
        assert iverilog["status"] in {"ok", "present"}


def test_plugin_list_returns_zero(capsys) -> None:
    assert main(["plugin", "list"]) == 0
    assert "plugin" in capsys.readouterr().out.lower()


def test_unimplemented_command_returns_one(capsys) -> None:
    assert main(["graph", "--check"]) == 1
    err = capsys.readouterr().err
    assert "E00" in err
    assert "尚未实现" in err


def test_serve_is_wired_to_server(monkeypatch, tmp_path, capsys) -> None:
    calls: dict[str, object] = {}

    def fake_serve(root, host="127.0.0.1", port=8123, *, open_browser=True):
        calls.update(root=root, host=host, port=port, open_browser=open_browser)
        return 0

    import rvgen.server as server_module

    monkeypatch.setattr(server_module, "serve", fake_serve)
    assert main(["serve", "--project", str(tmp_path), "--port", "9000", "--no-open"]) == 0
    assert calls == {
        "root": tmp_path.resolve(),
        "host": "127.0.0.1",
        "port": 9000,
        "open_browser": False,
    }


def test_serve_rejects_missing_project(capsys, tmp_path) -> None:
    missing = tmp_path / "absent"
    assert main(["serve", "--project", str(missing), "--no-open"]) == 3
    assert "E00" in capsys.readouterr().err
