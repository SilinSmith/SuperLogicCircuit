"""原子写：同目录 tmp + fsync + os.replace。

Windows 不伪造目录 fsync：跳过并记 I01。权限/占用重试 3 次（50/150/400 ms），
仍失败报 E12 并保留 tmp 供取证。
"""

from __future__ import annotations

import os
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path

from .diag import DiagnosticSink

_RETRY_DELAYS_MS = (50, 150, 400)
_MAX_BACKUPS = 20


class AtomicWriteError(OSError):
    code = "E12"

    def __init__(self, path: Path, tmp_path: Path, message: str) -> None:
        super().__init__(message)
        self.path = path
        self.tmp_path = tmp_path


def _fsync_dir(directory: Path, sink: DiagnosticSink | None) -> None:
    if os.name == "nt":
        if sink is not None:
            sink.info("I01", "Windows 不支持目录 fsync，已跳过")
        return
    try:
        fd = os.open(str(directory), os.O_RDONLY)
    except OSError as exc:
        if sink is not None:
            sink.info("I01", f"目录 fsync 打开失败，已跳过：{exc}")
        return
    try:
        os.fsync(fd)
    except OSError as exc:
        if sink is not None:
            sink.info("I01", f"目录 fsync 失败，已跳过：{exc}")
    finally:
        os.close(fd)


def _backup_existing(path: Path, bak_dir: Path) -> None:
    bak_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    backup = bak_dir / f"{path.name}.{stamp}"
    shutil.copy2(path, backup)
    backups = sorted(bak_dir.glob(f"{path.name}.*"))
    for stale in backups[:-_MAX_BACKUPS]:
        stale.unlink(missing_ok=True)


def atomic_write(
    path: Path,
    data: str | bytes,
    *,
    bak_dir: Path | None = None,
    retries: int = 3,
    sink: DiagnosticSink | None = None,
) -> Path:
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = data.encode("utf-8") if isinstance(data, str) else data
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")

    try:
        with tmp_path.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise AtomicWriteError(path, tmp_path, f"写临时文件失败：{exc}") from exc

    if bak_dir is not None and path.exists():
        try:
            _backup_existing(path, Path(bak_dir))
        except OSError as exc:
            raise AtomicWriteError(path, tmp_path, f"备份失败：{exc}") from exc

    attempts = max(1, retries)
    last_error: OSError | None = None
    for attempt in range(attempts):
        try:
            os.replace(tmp_path, path)
        except PermissionError as exc:
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(_RETRY_DELAYS_MS[min(attempt, len(_RETRY_DELAYS_MS) - 1)] / 1000)
                continue
            raise AtomicWriteError(
                path,
                tmp_path,
                f"原子写失败（权限/占用），已重试 {attempts} 次；tmp 保留在 {tmp_path}",
            ) from exc
        except OSError as exc:
            raise AtomicWriteError(
                path,
                tmp_path,
                f"原子写失败：{exc}；tmp 保留在 {tmp_path}",
            ) from exc
        else:
            _fsync_dir(path.parent, sink)
            return path

    raise AtomicWriteError(path, tmp_path, f"原子写失败：{last_error}")
