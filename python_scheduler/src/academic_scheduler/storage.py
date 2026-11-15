"""Atomic workspace files with backups and cooperative optimistic concurrency."""

import hashlib
import json
import os
from pathlib import Path
import tempfile

from .workspace import Workspace, WorkspaceError


class StorageError(ValueError):
    """A storage operation was rejected without discarding in-memory work."""


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise StorageError(f"存档 JSON 含重复字段：{key}")
        result[key] = value
    return result


def _constant(value):
    raise StorageError(f"存档 JSON 不允许 {value}。")


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _decode(content: bytes) -> Workspace:
    try:
        document = json.loads(content.decode("utf-8-sig"), object_pairs_hook=_pairs, parse_constant=_constant)
        return Workspace.from_document(document)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise StorageError(f"无法读取工作区存档：{exc}") from exc


class WorkspaceStore:
    def __init__(self, path):
        self.path = Path(path).expanduser().absolute()
        self._fingerprint: str | None = None

    def load(self) -> Workspace:
        try:
            content = self.path.read_bytes()
        except OSError as exc:
            raise StorageError(f"无法打开存档 {self.path}：{exc}") from exc
        workspace = _decode(content)
        self._fingerprint = _digest(content)
        return workspace

    def _check_current(self) -> bytes | None:
        try:
            current = self.path.read_bytes()
        except FileNotFoundError:
            if self._fingerprint is not None:
                raise StorageError("存档已被其他程序删除；请先核对磁盘文件。")
            return None
        if self._fingerprint is None:
            raise StorageError("存档已存在但尚未加载；请先加载，不能直接覆盖。")
        if _digest(current) != self._fingerprint:
            raise StorageError("存档已被其他程序修改；请先重新加载或另存到新路径。")
        return current

    @staticmethod
    def _temporary(parent: Path, filename: str, content: bytes) -> Path:
        descriptor, name = tempfile.mkstemp(prefix=f".{filename}.", suffix=".tmp", dir=parent)
        path = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            return path
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    def save(self, workspace: Workspace) -> None:
        try:
            document = workspace.to_document()
            Workspace.from_document(document)
            content = (json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")
        except (WorkspaceError, ValueError, TypeError, UnicodeError, RecursionError) as exc:
            raise StorageError(f"工作区验证失败，尚未保存：{exc}") from exc
        lock_path = Path(str(self.path) + ".lock")
        owned_lock = False
        temporary = []
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            try:
                descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError as exc:
                raise StorageError("存档正在被其他进程保存，或留有锁文件；请核对后重试。") from exc
            owned_lock = True
            with os.fdopen(descriptor, "w", encoding="ascii") as stream:
                stream.write(str(os.getpid()))
            previous = self._check_current()
            pending = self._temporary(self.path.parent, self.path.name, content)
            temporary.append(pending)
            if previous is not None:
                backup = self._temporary(self.path.parent, self.path.name + ".bak", previous)
                temporary.append(backup)
                self._check_current()
                os.replace(backup, Path(str(self.path) + ".bak"))
            self._check_current()
            os.replace(pending, self.path)
            self._fingerprint = _digest(content)
        except StorageError:
            raise
        except OSError as exc:
            raise StorageError(f"保存失败，内存数据仍保留：{exc}") from exc
        finally:
            for path in temporary:
                path.unlink(missing_ok=True)
            if owned_lock:
                lock_path.unlink(missing_ok=True)
