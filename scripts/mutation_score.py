#!/usr/bin/env python
"""计算 mutmut 导出的 CI/CD 统计并执行变异分数门槛（nightly 用）。

用法：python scripts/mutation_score.py --min 80
退出码：0 达标；1 未达标或缺少统计文件。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

DEFAULT_STATS = Path("mutants") / "mutmut-cicd-stats.json"


def mutation_score(stats: dict[str, Any]) -> float:
    killed = float(stats.get("killed", 0))
    survived = float(stats.get("survived", 0))
    timeout = float(stats.get("timeout", 0))
    suspicious = float(stats.get("suspicious", 0))
    total = killed + survived + timeout + suspicious
    return 100.0 if total == 0 else 100.0 * killed / total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stats", type=Path, default=DEFAULT_STATS)
    parser.add_argument("--min", type=float, default=80.0)
    args = parser.parse_args(argv)

    if not args.stats.is_file():
        print(f"缺少变异统计文件：{args.stats}", file=sys.stderr)
        return 1
    stats = json.loads(args.stats.read_text(encoding="utf-8"))
    score = mutation_score(stats)
    killed = stats.get("killed", 0)
    survived = stats.get("survived", 0)
    timeout = stats.get("timeout", 0)
    suspicious = stats.get("suspicious", 0)
    print(
        f"mutation score {score:.1f}% (killed={killed}, survived={survived}, "
        f"timeout={timeout}, suspicious={suspicious})"
    )
    return 0 if score >= args.min else 1


if __name__ == "__main__":
    raise SystemExit(main())
