"""Temporary workspace lifecycle and safe source-file reads."""

from __future__ import annotations

import errno
import logging
import os
import re
import shutil
import stat
import tempfile
import time
import unicodedata
from collections.abc import Callable, Collection
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Literal

from app.github.clone import is_link_or_reparse

logger = logging.getLogger(__name__)
_RUN_DIRECTORY_PATTERN = re.compile(r"^run-([1-9][0-9]*)$")
_WINDOWS_RESERVED_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "CONIN$",
        "CONOUT$",
        *(f"COM{number}" for number in range(1, 10)),
        *(f"LPT{number}" for number in range(1, 10)),
        *(f"COM{digit}" for digit in ("¹", "²", "³")),
        *(f"LPT{digit}" for digit in ("¹", "²", "³")),
    }
)


class WorkspaceError(RuntimeError):
    """The configured temporary workspace cannot be used safely."""


class SourceReadError(Exception):
    """A source file could not be read under the safe-read policy."""

    def __init__(
        self, reason: Literal["too_large", "unsafe_path", "not_regular", "unreadable"]
    ) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class CleanupWarning:
    stage: Literal["cleanup"]
    code: Literal["cleanup_failed"]
    message: str


@dataclass(frozen=True, slots=True)
class SweepResult:
    removed_ids: tuple[int, ...]
    failed_ids: tuple[int, ...]


def prepare_temp_root(root: Path | str) -> Path:
    """Create and validate the private root used for per-run workspaces."""
    candidate = _absolute_path(root)
    if os.name == "nt":
        _validate_windows_root_location(candidate)
        _reject_reparse_components(
            candidate, Path(tempfile.gettempdir()).resolve(strict=True)
        )
    else:
        _reject_root_or_home(candidate)

    try:
        candidate_stat = candidate.lstat()
    except FileNotFoundError:
        try:
            candidate.mkdir(mode=0o700)
        except OSError as error:
            raise WorkspaceError(
                "Temporary workspace could not be prepared."
            ) from error
        try:
            candidate_stat = candidate.lstat()
        except OSError as error:
            raise WorkspaceError(
                "Temporary workspace could not be prepared."
            ) from error
    except OSError as error:
        raise WorkspaceError("Temporary workspace could not be prepared.") from error

    if not stat.S_ISDIR(candidate_stat.st_mode) or is_link_or_reparse(candidate_stat):
        raise WorkspaceError("Temporary workspace configuration is unsafe.")

    resolved = candidate.resolve(strict=True)
    resolved_stat = resolved.lstat()
    if not _same_file(candidate_stat, resolved_stat):
        raise WorkspaceError(
            "Temporary workspace configuration changed during validation."
        )
    if os.name == "nt":
        _validate_windows_root_location(resolved)
        _reject_reparse_components(resolved, Path(tempfile.gettempdir()).resolve())
    else:
        _reject_root_or_home(resolved)
        if (
            resolved_stat.st_uid != os.getuid()
            or stat.S_IMODE(resolved_stat.st_mode) != 0o700
        ):
            raise WorkspaceError("Temporary workspace permissions are unsafe.")
    return resolved


def create_run_dir(root: Path | str, run_id: int) -> Path:
    """Exclusively create the private ``run-<int>`` directory."""
    if isinstance(run_id, bool) or not isinstance(run_id, int) or run_id <= 0:
        raise ValueError("run_id must be a positive integer.")

    resolved_root = prepare_temp_root(root)
    run_dir = resolved_root / f"run-{run_id}"
    try:
        run_dir.mkdir(mode=0o700, exist_ok=False)
        run_stat = run_dir.lstat()
    except OSError as error:
        raise WorkspaceError("Temporary run directory could not be created.") from error
    if not stat.S_ISDIR(run_stat.st_mode) or is_link_or_reparse(run_stat):
        raise WorkspaceError("Temporary run directory could not be created safely.")
    return run_dir


def cleanup_run_dir(root: Path | str, run_dir: Path | str) -> CleanupWarning | None:
    """Remove one direct run child without following links or leaving the root."""
    try:
        resolved_root = prepare_temp_root(root)
        candidate = _absolute_path(run_dir)
        if candidate.parent != resolved_root or not _RUN_DIRECTORY_PATTERN.fullmatch(
            candidate.name
        ):
            return _cleanup_warning()
        try:
            run_stat = candidate.lstat()
        except FileNotFoundError:
            return None
        if not stat.S_ISDIR(run_stat.st_mode) or is_link_or_reparse(run_stat):
            return _cleanup_warning()

        def onexc(
            function: Callable[[str], object], path: str, error: BaseException
        ) -> None:
            if not isinstance(error, PermissionError):
                raise error
            for attempt in range(3):
                if os.name == "nt":
                    try:
                        os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
                    except OSError:
                        pass
                time.sleep(0.05 * (attempt + 1))
                try:
                    function(path)
                    return
                except PermissionError:
                    if attempt == 2:
                        raise

        shutil.rmtree(candidate, onexc=onexc)
    except (OSError, ValueError, WorkspaceError):
        return _cleanup_warning()
    return None


def sweep_orphaned_runs(
    root: Path | str, active_run_ids: Collection[int] = ()
) -> SweepResult:
    """Remove inactive direct children named exactly ``run-<positive integer>``."""
    resolved_root = prepare_temp_root(root)
    removed: list[int] = []
    failed: list[int] = []
    skipped_count = 0

    try:
        with os.scandir(resolved_root) as entries:
            for entry in entries:
                match = _RUN_DIRECTORY_PATTERN.fullmatch(entry.name)
                if match is None:
                    skipped_count += 1
                    continue
                run_id = int(match.group(1))
                try:
                    entry_stat = entry.stat(follow_symlinks=False)
                except OSError:
                    failed.append(run_id)
                    continue
                if (
                    not stat.S_ISDIR(entry_stat.st_mode)
                    or is_link_or_reparse(entry_stat)
                    or run_id in active_run_ids
                ):
                    skipped_count += 1
                    continue

                warning = cleanup_run_dir(resolved_root, Path(entry.path))
                if warning is None:
                    removed.append(run_id)
                else:
                    failed.append(run_id)
    except OSError as error:
        raise WorkspaceError("Temporary workspace could not be scanned.") from error

    logger.info(
        "Temporary run sweep completed",
        extra={
            "removed_count": len(removed),
            "failure_count": len(failed),
            "skipped_count": skipped_count,
        },
    )
    return SweepResult(tuple(removed), tuple(failed))


def read_source_file(root: Path | str, relative_path: str, max_bytes: int) -> bytes:
    """Read a bounded regular file beneath root without following links."""
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 0:
        raise ValueError("max_bytes must be a nonnegative integer.")
    components = _validate_relative_path(relative_path)
    if os.name == "nt":
        return _read_windows_source_file(root, components, max_bytes)
    return _read_posix_source_file(root, components, max_bytes)


def decode_source_bytes(raw: bytes) -> str:
    """Decode source text tolerantly and remove a leading UTF-8 BOM."""
    return raw.decode("utf-8-sig", errors="replace")


def _read_posix_source_file(
    root: Path | str, components: tuple[str, ...], max_bytes: int
) -> bytes:
    root_path = _absolute_path(root)
    root_stat = _lstat_for_read(root_path)
    if not stat.S_ISDIR(root_stat.st_mode) or is_link_or_reparse(root_stat):
        raise SourceReadError("unsafe_path")

    root_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        root_fd = os.open(root_path, root_flags)
    except OSError as error:
        raise _source_error_for_oserror(error) from error

    opened_directories = [root_fd]
    try:
        if not _same_file(root_stat, os.fstat(root_fd)):
            raise SourceReadError("unsafe_path")
        parent_fd = root_fd
        for component in components[:-1]:
            before = _stat_at(parent_fd, component)
            if is_link_or_reparse(before):
                raise SourceReadError("unsafe_path")
            if not stat.S_ISDIR(before.st_mode):
                raise SourceReadError("not_regular")
            try:
                directory_fd = os.open(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                    dir_fd=parent_fd,
                )
            except OSError as error:
                raise _source_error_for_oserror(error) from error
            after = os.fstat(directory_fd)
            if not _same_file(before, after):
                os.close(directory_fd)
                raise SourceReadError("unsafe_path")
            opened_directories.append(directory_fd)
            parent_fd = directory_fd

        name = components[-1]
        before = _stat_at(parent_fd, name)
        _validate_regular_source(before, max_bytes)
        try:
            file_fd = os.open(
                name,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                dir_fd=parent_fd,
            )
        except OSError as error:
            raise _source_error_for_oserror(error) from error
        try:
            after = os.fstat(file_fd)
            _validate_regular_source(after, max_bytes)
            if not _same_file(before, after):
                raise SourceReadError("unsafe_path")
            return _read_bounded_fd(file_fd, max_bytes)
        finally:
            os.close(file_fd)
    finally:
        for descriptor in reversed(opened_directories):
            os.close(descriptor)


def _read_windows_source_file(
    root: Path | str, components: tuple[str, ...], max_bytes: int
) -> bytes:
    root_path = _absolute_path(root)
    root_stat = _lstat_for_read(root_path)
    if not stat.S_ISDIR(root_stat.st_mode) or is_link_or_reparse(root_stat):
        raise SourceReadError("unsafe_path")
    try:
        resolved_root = root_path.resolve(strict=True)
        candidate = root_path.joinpath(*components)
        resolved_candidate = candidate.resolve(strict=True)
        if not resolved_candidate.is_relative_to(resolved_root):
            raise SourceReadError("unsafe_path")
    except SourceReadError:
        raise
    except (OSError, ValueError) as error:
        raise _source_error_for_oserror(error) from error

    current = root_path
    checked_directories: list[tuple[Path, os.stat_result]] = [(root_path, root_stat)]
    try:
        for component in components[:-1]:
            current /= component
            component_stat = current.lstat()
            if is_link_or_reparse(component_stat):
                raise SourceReadError("unsafe_path")
            if not stat.S_ISDIR(component_stat.st_mode):
                raise SourceReadError("not_regular")
            checked_directories.append((current, component_stat))

        file_path = current / components[-1]
        before = file_path.lstat()
        _validate_regular_source(before, max_bytes)
        with file_path.open("rb") as source_file:
            after = os.fstat(source_file.fileno())
            _validate_regular_source(after, max_bytes)
            if not _same_file(before, after):
                raise SourceReadError("unsafe_path")
            # Windows path opens cannot pin parent directories like POSIX dir_fd opens.
            for directory, expected_stat in checked_directories:
                current_stat = directory.lstat()
                if is_link_or_reparse(current_stat) or not _same_file(
                    expected_stat, current_stat
                ):
                    raise SourceReadError("unsafe_path")
            final_stat = file_path.lstat()
            if is_link_or_reparse(final_stat) or not _same_file(before, final_stat):
                raise SourceReadError("unsafe_path")
            return _read_bounded_fd(source_file.fileno(), max_bytes)
    except SourceReadError:
        raise
    except OSError as error:
        raise _source_error_for_oserror(error) from error


def _read_bounded_fd(file_fd: int, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    remaining = max_bytes + 1
    while remaining:
        try:
            chunk = os.read(file_fd, remaining)
        except OSError as error:
            raise _source_error_for_oserror(error) from error
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    data = b"".join(chunks)
    if len(data) > max_bytes:
        raise SourceReadError("too_large")
    return data


def _validate_regular_source(file_stat: os.stat_result, max_bytes: int) -> None:
    if is_link_or_reparse(file_stat):
        raise SourceReadError("unsafe_path")
    if not stat.S_ISREG(file_stat.st_mode):
        raise SourceReadError("not_regular")
    if file_stat.st_nlink != 1:
        raise SourceReadError("unsafe_path")
    if file_stat.st_size > max_bytes:
        raise SourceReadError("too_large")


def _validate_relative_path(relative_path: str) -> tuple[str, ...]:
    if not isinstance(relative_path, str) or not relative_path:
        raise SourceReadError("unsafe_path")
    if any(unicodedata.category(character) == "Cc" for character in relative_path):
        raise SourceReadError("unsafe_path")
    if "\x00" in relative_path:
        raise SourceReadError("unsafe_path")
    windows_path = PureWindowsPath(relative_path)
    if (
        Path(relative_path).is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
        or relative_path.startswith(("/", "\\"))
    ):
        raise SourceReadError("unsafe_path")

    components = tuple(re.split(r"[\\/]", relative_path))
    if any(component in {"", ".", ".."} for component in components):
        raise SourceReadError("unsafe_path")
    if os.name == "nt":
        for component in components:
            if ":" in component or component.endswith((" ", ".")):
                raise SourceReadError("unsafe_path")
            device_name = component.split(".", 1)[0].upper()
            if device_name in _WINDOWS_RESERVED_NAMES:
                raise SourceReadError("unsafe_path")
    return components


def _absolute_path(path: Path | str) -> Path:
    try:
        candidate = Path(path)
    except (TypeError, ValueError) as error:
        raise WorkspaceError("Temporary workspace path must be absolute.") from error
    if "\x00" in os.fspath(candidate):
        raise WorkspaceError("Temporary workspace path must be absolute.")
    if not candidate.is_absolute():
        raise WorkspaceError("Temporary workspace path must be absolute.")
    return Path(os.path.abspath(candidate))


def _reject_root_or_home(candidate: Path) -> None:
    try:
        resolved = candidate.resolve(strict=False)
    except OSError as error:
        raise WorkspaceError(
            "Temporary workspace path could not be resolved."
        ) from error
    if resolved == Path(resolved.anchor):
        raise WorkspaceError("Temporary workspace configuration is unsafe.")
    try:
        home = Path.home().resolve(strict=False)
    except (OSError, RuntimeError):
        return
    if resolved == home:
        raise WorkspaceError("Temporary workspace configuration is unsafe.")


def _validate_windows_root_location(candidate: Path) -> None:
    temp_root = Path(tempfile.gettempdir()).resolve(strict=True)
    try:
        relative = candidate.relative_to(temp_root)
    except ValueError as error:
        raise WorkspaceError(
            "Temporary workspace must be inside the user temp directory."
        ) from error
    if not relative.parts or relative == Path("."):
        raise WorkspaceError(
            "Temporary workspace must be below the user temp directory."
        )


def _reject_reparse_components(candidate: Path, base: Path) -> None:
    try:
        relative = candidate.relative_to(base)
    except ValueError as error:
        raise WorkspaceError(
            "Temporary workspace must be inside the user temp directory."
        ) from error
    current = base
    for component in relative.parts:
        current /= component
        try:
            component_stat = current.lstat()
        except FileNotFoundError:
            continue
        except OSError as error:
            raise WorkspaceError(
                "Temporary workspace could not be prepared."
            ) from error
        if is_link_or_reparse(component_stat):
            raise WorkspaceError("Temporary workspace configuration is unsafe.")


def _lstat_for_read(path: Path) -> os.stat_result:
    try:
        return path.lstat()
    except OSError as error:
        raise _source_error_for_oserror(error) from error


def _stat_at(parent_fd: int, name: str) -> os.stat_result:
    try:
        return os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as error:
        raise _source_error_for_oserror(error) from error


def _same_file(first: os.stat_result, second: os.stat_result) -> bool:
    return (
        first.st_dev == second.st_dev
        and first.st_ino == second.st_ino
        and stat.S_IFMT(first.st_mode) == stat.S_IFMT(second.st_mode)
    )


def _source_error_for_oserror(error: OSError) -> SourceReadError:
    if error.errno in {errno.ELOOP, errno.ENOTDIR}:
        return SourceReadError("unsafe_path")
    return SourceReadError("unreadable")


def _cleanup_warning() -> CleanupWarning:
    return CleanupWarning(
        stage="cleanup",
        code="cleanup_failed",
        message="Temporary files could not be fully removed.",
    )
