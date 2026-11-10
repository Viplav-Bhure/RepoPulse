"""Bounded, non-interactive GitHub repository retrieval."""

from __future__ import annotations

import logging
import os
import re
import signal
import stat
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.github.client import (
    GITHUB_USERNAME_PATTERN,
    GitHubClientError,
    GitHubRepository,
    get_repository_by_id,
)

CLONE_DISK_FACTOR = 2
MAX_TREE_ENTRIES = 100_000
MAX_TREE_DEPTH = 64
REPOSITORY_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
SUPPORTED_EXTENSIONS = frozenset({".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"})
GIT_POLL_INTERVAL_SECONDS = 1.0
logger = logging.getLogger(__name__)


class CloneError(Exception):
    """Safe, user-facing failure from repository retrieval."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.user_message = message


class RepositoryUnavailableError(CloneError):
    def __init__(self) -> None:
        super().__init__("repo_unavailable", "Unable to retrieve repository.")


class RepositoryTooLargeError(CloneError):
    def __init__(self) -> None:
        super().__init__(
            "repo_too_large",
            "Repository too large for current analysis limits.",
        )


class CloneTimedOutError(CloneError):
    def __init__(self) -> None:
        super().__init__("timed_out", "Analysis timed out.")


class CloneAnalysisError(CloneError):
    def __init__(self) -> None:
        super().__init__("analysis_failed", "Repository analysis failed.")


@dataclass(frozen=True, slots=True)
class CloneTarget:
    github_repo_id: int
    owner: str
    name: str
    size_kb: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.github_repo_id, bool)
            or not isinstance(self.github_repo_id, int)
            or self.github_repo_id <= 0
            or not isinstance(self.owner, str)
            or not GITHUB_USERNAME_PATTERN.fullmatch(self.owner)
            or not isinstance(self.name, str)
            or not REPOSITORY_NAME_PATTERN.fullmatch(self.name)
            or self.name in {".", ".."}
            or isinstance(self.size_kb, bool)
            or not isinstance(self.size_kb, int)
            or self.size_kb < 0
        ):
            raise RepositoryUnavailableError()

    @property
    def clone_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.name}.git"


@dataclass(frozen=True, slots=True)
class TreeMeasurement:
    size_bytes: int
    entries: int
    max_depth: int


class ProcessLike(Protocol):
    pid: int
    returncode: int | None

    def poll(self) -> int | None: ...

    def wait(self, timeout: float | None = None) -> int: ...

    def communicate(
        self, input: bytes | None = None, timeout: float | None = None
    ) -> tuple[bytes | None, bytes | None]: ...

    def kill(self) -> None: ...


Runner = Callable[..., ProcessLike]
Clock = Callable[[], float]
SizeFunction = Callable[..., TreeMeasurement]
ProcessKiller = Callable[[ProcessLike], None]
GitHubClient = Callable[[int, str], GitHubRepository]
ExclusionPredicate = Callable[[Path], bool]


def get_clone_target(
    stored_github_repo_id: int,
    stored_owner: str,
    stored_name: str,
    access_token: str,
    *,
    max_repo_size_mb: int,
    github_client: GitHubClient = get_repository_by_id,
) -> CloneTarget:
    """Validate the stored repository against GitHub's ID-based response."""
    _validate_positive_limit(max_repo_size_mb)
    if (
        isinstance(stored_github_repo_id, bool)
        or not isinstance(stored_github_repo_id, int)
        or stored_github_repo_id <= 0
    ):
        raise RepositoryUnavailableError()

    try:
        repository = github_client(stored_github_repo_id, access_token)
    except GitHubClientError:
        raise RepositoryUnavailableError() from None

    if (
        not isinstance(repository, GitHubRepository)
        or isinstance(repository.github_repo_id, bool)
        or not isinstance(repository.github_repo_id, int)
        or repository.github_repo_id != stored_github_repo_id
        or repository.private is not False
        or not isinstance(repository.owner_login, str)
        or not GITHUB_USERNAME_PATTERN.fullmatch(repository.owner_login)
        or not isinstance(repository.name, str)
        or not REPOSITORY_NAME_PATTERN.fullmatch(repository.name)
        or repository.name in {".", ".."}
        or isinstance(repository.size, bool)
        or not isinstance(repository.size, int)
        or repository.size < 0
    ):
        raise RepositoryUnavailableError()

    if repository.owner_login != stored_owner or repository.name != stored_name:
        logger.warning(
            "github_repository_identity_changed stored_repo_id=%s github_repo_id=%s",
            stored_github_repo_id,
            repository.github_repo_id,
        )

    if repository.size > max_repo_size_mb * 1024:
        raise RepositoryTooLargeError()

    return CloneTarget(
        github_repo_id=repository.github_repo_id,
        owner=repository.owner_login,
        name=repository.name,
        size_kb=repository.size,
    )


def scan_tree(
    root: Path,
    *,
    exclude_git: bool = False,
    tolerant: bool = False,
) -> TreeMeasurement:
    """Measure a tree without following links or counting directory metadata."""
    size_bytes = 0
    entries = 0
    max_depth = 0
    pending: list[tuple[Path, int, bool]] = [(root, 0, True)]

    try:
        while pending:
            directory, parent_depth, is_root = pending.pop()
            try:
                with os.scandir(directory) as iterator:
                    for entry in iterator:
                        if exclude_git and is_root and entry.name == ".git":
                            continue

                        try:
                            entry_stat = entry.stat(follow_symlinks=False)
                        except (FileNotFoundError, NotADirectoryError):
                            if tolerant:
                                continue
                            raise

                        depth = parent_depth + 1
                        entries += 1
                        max_depth = max(max_depth, depth)
                        if entries > MAX_TREE_ENTRIES or (
                            not tolerant and depth > MAX_TREE_DEPTH
                        ):
                            raise RepositoryTooLargeError()

                        mode = entry_stat.st_mode
                        if is_link_or_reparse(entry_stat):
                            size_bytes += entry_stat.st_size
                        elif stat.S_ISDIR(mode):
                            pending.append((Path(entry.path), depth, False))
                        elif stat.S_ISREG(mode):
                            size_bytes += entry_stat.st_size
                        else:
                            raise CloneAnalysisError()
            except (FileNotFoundError, NotADirectoryError):
                if not tolerant:
                    raise
    except RepositoryTooLargeError:
        raise
    except (OSError, ValueError):
        raise CloneAnalysisError() from None

    return TreeMeasurement(size_bytes, entries, max_depth)


def count_supported_files(
    root: Path,
    is_excluded: ExclusionPredicate | None = None,
) -> int:
    """Count supported-extension files without returning paths or following links."""
    count = 0
    pending: list[tuple[Path, Path, bool]] = [(root, Path(), True)]
    try:
        while pending:
            directory, relative_directory, is_root = pending.pop()
            with os.scandir(directory) as iterator:
                for entry in iterator:
                    if is_root and entry.name == ".git":
                        continue

                    relative_path = relative_directory / entry.name
                    entry_stat = entry.stat(follow_symlinks=False)
                    if is_link_or_reparse(entry_stat):
                        continue
                    if stat.S_ISDIR(entry_stat.st_mode):
                        if is_excluded is None or not is_excluded(relative_path):
                            pending.append((Path(entry.path), relative_path, False))
                    elif (
                        stat.S_ISREG(entry_stat.st_mode)
                        and Path(entry.name).suffix.lower() in SUPPORTED_EXTENSIONS
                        and (is_excluded is None or not is_excluded(relative_path))
                    ):
                        count += 1
    except (OSError, ValueError):
        raise CloneAnalysisError() from None
    return count


def clone_repository(
    target: CloneTarget,
    run_dir: Path,
    *,
    max_repo_size_mb: int,
    max_source_files: int,
    deadline: float,
    runner: Runner | None = None,
    clock: Clock = time.monotonic,
    size_fn: SizeFunction = scan_tree,
    is_excluded: ExclusionPredicate | None = None,
    process_killer: ProcessKiller | None = None,
    test_source_override: str | None = None,
) -> str:
    """Clone into ``run_dir/repository`` and return the validated HEAD SHA."""
    _validate_positive_limit(max_repo_size_mb)
    _validate_positive_limit(max_source_files)
    selected_runner = runner or _start_process
    selected_killer = process_killer or _kill_process_tree
    run_dir = Path(run_dir)
    _validate_run_directory(run_dir)

    repository_dir = run_dir / "repository"
    template_dir = run_dir / "empty-template"
    hooks_dir = run_dir / "empty-hooks"
    try:
        template_dir.mkdir()
        hooks_dir.mkdir()
    except (FileExistsError, OSError):
        raise CloneAnalysisError() from None
    try:
        repository_dir.lstat()
    except FileNotFoundError:
        pass
    except OSError:
        raise CloneAnalysisError() from None
    else:
        raise CloneAnalysisError()

    source = target.clone_url
    test_config: tuple[str, ...] = ()
    if test_source_override is not None:
        source = test_source_override
        test_config = ("protocol.file.allow=always",)

    clone_argv = _build_clone_argv(
        source,
        repository_dir,
        template_dir,
        hooks_dir,
        test_config=test_config,
    )
    env = _git_environment()
    max_clone_bytes = max_repo_size_mb * 1024 * 1024 * CLONE_DISK_FACTOR

    _run_monitored(
        clone_argv,
        env=env,
        cwd=run_dir,
        deadline=deadline,
        runner=selected_runner,
        clock=clock,
        size_fn=size_fn,
        size_root=run_dir,
        max_size_bytes=max_clone_bytes,
        process_killer=selected_killer,
        failure_error=RepositoryUnavailableError,
    )

    full_measurement = size_fn(repository_dir)
    if full_measurement.size_bytes > max_clone_bytes:
        raise RepositoryTooLargeError()
    if (
        full_measurement.entries > MAX_TREE_ENTRIES
        or full_measurement.max_depth > MAX_TREE_DEPTH
    ):
        raise RepositoryTooLargeError()

    checkout_measurement = size_fn(repository_dir, exclude_git=True)
    if checkout_measurement.size_bytes > max_repo_size_mb * 1024 * 1024:
        raise RepositoryTooLargeError()
    if count_supported_files(repository_dir, is_excluded) > max_source_files:
        raise RepositoryTooLargeError()

    rev_parse_argv = _git_prefix() + [
        "-C",
        str(repository_dir),
        "rev-parse",
        "HEAD",
    ]
    output = _run_monitored(
        rev_parse_argv,
        env=env,
        cwd=run_dir,
        deadline=deadline,
        runner=selected_runner,
        clock=clock,
        process_killer=selected_killer,
        capture_stdout=True,
    )
    try:
        commit_sha = output.decode("ascii", errors="strict").strip()
    except UnicodeDecodeError:
        raise CloneAnalysisError() from None
    if not re.fullmatch(r"[0-9a-fA-F]{40,64}", commit_sha):
        raise CloneAnalysisError()
    return commit_sha


def _build_clone_argv(
    source: str,
    repository_dir: Path,
    template_dir: Path,
    hooks_dir: Path,
    *,
    test_config: Sequence[str] = (),
) -> list[str]:
    argv = _git_prefix()
    for config in test_config:
        argv.extend(("-c", config))
    argv.extend(
        (
            "clone",
            "--no-recurse-submodules",
            "--single-branch",
            "--no-hardlinks",
            "--template",
            str(template_dir),
            "-c",
            "core.symlinks=false",
            "-c",
            f"core.hooksPath={hooks_dir}",
            "--",
            source,
            str(repository_dir),
        )
    )
    return argv


def _git_prefix() -> list[str]:
    return [
        "git",
        "-c",
        "protocol.allow=never",
        "-c",
        "protocol.https.allow=always",
        "-c",
        "http.followRedirects=false",
        "-c",
        "credential.helper=",
    ]


def _git_environment() -> dict[str, str]:
    inherited_names = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR"}
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in inherited_names
    }
    environment.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_LFS_SKIP_SMUDGE": "1",
        }
    )
    return environment


def _start_process(
    argv: Sequence[str],
    *,
    env: dict[str, str],
    cwd: Path,
    capture_stdout: bool = False,
) -> subprocess.Popen[bytes]:
    is_windows = os.name == "nt"
    return subprocess.Popen(
        argv,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE if capture_stdout else subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        shell=False,
        start_new_session=not is_windows,
        creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if is_windows else 0),
    )


def _run_monitored(
    argv: Sequence[str],
    *,
    env: dict[str, str],
    cwd: Path,
    deadline: float,
    runner: Runner,
    clock: Clock,
    size_fn: SizeFunction | None = None,
    size_root: Path | None = None,
    max_size_bytes: int | None = None,
    process_killer: ProcessKiller,
    capture_stdout: bool = False,
    failure_error: type[CloneError] = CloneAnalysisError,
) -> bytes:
    if clock() >= deadline:
        raise CloneTimedOutError()
    try:
        process = runner(
            argv,
            env=env,
            cwd=cwd,
            capture_stdout=capture_stdout,
        )
    except (OSError, ValueError):
        raise CloneAnalysisError() from None

    output = b""
    try:
        while process.poll() is None:
            remaining = deadline - clock()
            if remaining <= 0:
                raise CloneTimedOutError()
            wait_seconds = min(GIT_POLL_INTERVAL_SECONDS, remaining)
            try:
                if capture_stdout:
                    stdout, _ = process.communicate(timeout=wait_seconds)
                    if stdout is not None:
                        output = stdout
                else:
                    process.wait(timeout=wait_seconds)
            except subprocess.TimeoutExpired:
                if clock() >= deadline:
                    raise CloneTimedOutError() from None
                if size_fn is not None and size_root is not None:
                    measurement = size_fn(size_root, tolerant=True)
                    if max_size_bytes is not None:
                        if measurement.size_bytes > max_size_bytes:
                            raise RepositoryTooLargeError() from None
        if clock() >= deadline:
            raise CloneTimedOutError()
        if process.returncode != 0:
            raise failure_error()
        if capture_stdout and not output:
            stdout, _ = process.communicate()
            output = stdout or b""
        return output
    except BaseException as original_error:
        if process.poll() is None:
            try:
                process_killer(process)
            except BaseException as killer_error:
                try:
                    process.kill()
                    process.wait()
                except BaseException as fallback_error:
                    raise BaseExceptionGroup(
                        "Process-tree termination and fallback kill/reap failed.",
                        [killer_error, fallback_error],
                    ) from original_error
                raise
            else:
                process.wait()
        raise


def _kill_process_tree(process: ProcessLike) -> None:
    if os.name == "nt":
        try:
            completed = subprocess.run(
                [
                    "taskkill.exe",
                    "/PID",
                    str(process.pid),
                    "/T",
                    "/F",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
                check=False,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            process.kill()
            process.wait()
            raise CloneAnalysisError() from None
        if completed.returncode != 0:
            process.kill()
            process.wait()
            raise CloneAnalysisError()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError:
            process.kill()
            process.wait()
            raise CloneAnalysisError() from None
    process.wait()


def _validate_run_directory(run_dir: Path) -> None:
    try:
        run_stat = run_dir.lstat()
    except OSError:
        raise CloneAnalysisError() from None
    if not stat.S_ISDIR(run_stat.st_mode) or is_link_or_reparse(run_stat):
        raise CloneAnalysisError()


def is_link_or_reparse(entry_stat: os.stat_result) -> bool:
    if stat.S_ISLNK(entry_stat.st_mode):
        return True
    file_attributes = getattr(entry_stat, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(file_attributes & reparse_flag)


def _validate_positive_limit(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CloneAnalysisError()
