from __future__ import annotations

import json

from slc.diag import DiagnosticSink
from slc.trace import normalize, stats, summary

META = "#slc-meta\tschema=core\ttimescale=ns"


def write_tsv(tmp_path, body: str):
    path = tmp_path / "trace.tsv"
    path.write_text(body, encoding="utf-8")
    return path


def test_normalize_roundtrip_wellformed(tmp_path):
    src = write_tsv(
        tmp_path,
        META
        + "\n"
        + "0\t0\t0x0\tIDLE\t-\t-\n"
        + "10\t1\t0x4\tRX\tfifo_cnt=1\tarc=mod:uart.tx->mod:fifo.push:1;cdc=cfg:0:2\n",
    )
    dst = tmp_path / "run.jsonl"
    sink = DiagnosticSink()
    result = normalize(src, dst, "core", sink=sink)
    assert not sink.has_errors()
    assert result.rows == 2
    assert result.cycles == 2
    rows = [json.loads(line) for line in dst.read_text(encoding="utf-8").splitlines()]
    assert rows[1]["cycle"] == 1
    assert rows[1]["time_ns"] == 10.0
    assert rows[1]["ids"] == {"fifo_cnt": "1"}
    assert rows[1]["arc"] == [{"edge": "mod:uart.tx->mod:fifo.push", "toggle": 1}]
    assert rows[1]["cdc"] == [{"id": "cfg", "afull": "0", "cnt": "2"}]


def test_E11_column_count_mismatch(tmp_path):
    src = write_tsv(tmp_path, META + "\n0\t0\t0x0\tIDLE\t-\n")
    dst = tmp_path / "run.jsonl"
    sink = DiagnosticSink()
    normalize(src, dst, "core", sink=sink)
    assert sink.has_errors()
    assert any(item.code == "E11" and "列数" in item.message for item in sink.items)
    assert not dst.exists(), "非法输入不得留下半截输出"


def test_E11_meta_line_missing(tmp_path):
    src = write_tsv(tmp_path, "0\t0\t0x0\tIDLE\t-\t-\n")
    sink = DiagnosticSink()
    normalize(src, tmp_path / "run.jsonl", "core", sink=sink)
    assert any(item.code == "E11" and "元数据" in item.message for item in sink.items)


def test_E11_ext_value_invalid(tmp_path):
    src = write_tsv(tmp_path, META + "\n0\t0\t-\tIDLE\t-\tarc=bad-arc\n")
    sink = DiagnosticSink()
    normalize(src, tmp_path / "run.jsonl", "core", sink=sink)
    assert any(item.code == "E11" and "arc" in item.message for item in sink.items)


def test_E11_cycle_regression(tmp_path):
    src = write_tsv(tmp_path, META + "\n0\t0\t-\tA\t-\t-\n0\t2\t-\tB\t-\t-\n0\t1\t-\tC\t-\t-\n")
    sink = DiagnosticSink()
    normalize(src, tmp_path / "run.jsonl", "core", sink=sink)
    assert any(item.code == "E11" and "回退" in item.message for item in sink.items)


def test_W15_unknown_ext_key_kept(tmp_path):
    src = write_tsv(tmp_path, META + "\n0\t0\t-\tIDLE\t-\tfoo=1\n")
    dst = tmp_path / "run.jsonl"
    sink = DiagnosticSink()
    normalize(src, dst, "core", sink=sink)
    assert any(item.code == "W15" for item in sink.items)
    row = json.loads(dst.read_text(encoding="utf-8").splitlines()[0])
    assert row["ext"] == {"foo": "1"}


def test_cpu_flavor_namespaces_plugin_keys(tmp_path):
    src = write_tsv(
        tmp_path,
        "#slc-meta\tschema=cpu\ttimescale=ns\n0\t0\t0x0\tIDLE\t-\tpipe=IF;ctrl=bubble\n",
    )
    dst = tmp_path / "run.jsonl"
    sink = DiagnosticSink()
    normalize(src, dst, "cpu", sink=sink)
    assert not sink.has_errors()
    row = json.loads(dst.read_text(encoding="utf-8").splitlines()[0])
    assert row["p_cpu"] == {"pipe": "IF", "ctrl": "bubble"}


def test_summary_utilization_W05(tmp_path):
    dst = tmp_path / "run.jsonl"
    dst.write_text(
        "\n".join(
            json.dumps(
                {
                    "cycle": cycle,
                    "time_ns": cycle,
                    "loc": "-",
                    "state": "-",
                    "ids": {},
                    "arc": [{"edge": "a->b", "toggle": 1}],
                    "cdc": [],
                }
            )
            for cycle in range(10)
        )
        + "\n",
        encoding="utf-8",
    )
    graph = {
        "schema_version": "1.0.0",
        "generated_by": "test",
        "source_digest": "sha256:0",
        "nodes": [
            {"id": "a", "type": "module_node", "label": "a"},
            {"id": "b", "type": "module_node", "label": "b"},
        ],
        "edges": [
            {
                "id": "a->b",
                "source": "a",
                "target": "b",
                "kind": "data",
                "width_bits": 8,
                "bandwidth": {"source": "derived", "width_bits": 8, "clock": "clk", "freq_hz": 50_000_000},
            }
        ],
    }
    graph_path = tmp_path / "node_graph.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    sink = DiagnosticSink()
    payload = summary(dst, graph_path, "core", sink=sink)
    assert payload["cycles"] == 10
    edge = payload["edges"][0]
    assert edge["toggles"] == 10
    assert edge["bytes"] == 10
    assert edge["bits_per_cycle"] == 8.0
    assert edge["utilization"] == 1.0
    assert any(item.code == "W05" for item in sink.items) is False

    # 同一位宽下每周期翻转两次 → 利用率 2.0 → W05
    dst.write_text(
        "\n".join(
            json.dumps(
                {
                    "cycle": cycle,
                    "time_ns": cycle,
                    "loc": "-",
                    "state": "-",
                    "ids": {},
                    "arc": [{"edge": "a->b", "toggle": 2}],
                    "cdc": [],
                }
            )
            for cycle in range(10)
        )
        + "\n",
        encoding="utf-8",
    )
    sink = DiagnosticSink()
    payload = summary(dst, graph_path, "core", sink=sink)
    assert payload["edges"][0]["utilization"] == 2.0
    assert any(item.code == "W05" for item in sink.items)


def test_stats_counts_jsonl_and_tsv(tmp_path):
    tsv = write_tsv(tmp_path, META + "\n0\t0\t-\tA\t-\t-\n0\t1\t-\tB\t-\t-\n")
    sink = DiagnosticSink()
    assert stats(tsv, sink=sink)["rows"] == 2
    jsonl = tmp_path / "run.jsonl"
    normalize(tsv, jsonl, "core", sink=sink)
    assert stats(jsonl, sink=sink)["cycles"] == 2
