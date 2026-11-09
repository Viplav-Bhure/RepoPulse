"""Tests for bounded repository cloning without network access."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.github.client import GitHubRepository
from app.github.clone import (
    CLONE_DISK_FACTOR,
    CloneAnalysisError,
    CloneTarget,
    CloneTimedOutError,
    RepositoryTooLargeError,
    RepositoryUnavailableError,
    TreeMeasurement,
    _kill_process_tree,
    _run_monitored,
    clone_repository,
    count_supported_files,
    get_clone_target,
    scan_tree,
)

COMMIT_SHA = "a" * 40


def repository(
    *,
    repository_id: int = 17,
    owner: str = "octocat",
    name: str = "demo",
    size_kb: int = 50 * 1024,
    private: bool = False,
) -> GitHubRepository:
    return GitHubRepository(
        github_repo_id=repository_id,
        name=name,
        owner_login=owner,
        owner_type="User",
        default_branch="main",
        is_fork=False,
        is_archived=False,
        primary_language="Python",
        updated_at=datetime(2026, 11, 1, tzinfo=UTC),
        size=size_kb,
        private=private,
    )


def test_target_checks_id_visibility_names_and_size() -> None:
    get_target = lambda repo: get_clone_target(  # noqa: E731
        17,
        "octocat",
        "demo",
        "test-token",
        max_repo_size_mb=50,
        github_client=lambda _repo_id, _token: repo,
    )

    assert get_target(repository()).clone_url == ("https://github.com/octocat/demo.git")
    with pytest.raises(RepositoryTooLargeError):
        get_target(repository(size_kb=50 * 1024 + 1))
    with pytest.raises(RepositoryUnavailableError):
        get_target(repository(repository_id=18))
    with pytest.raises(RepositoryUnavailableError):
        get_target(repository(private=True))


@pytest.mark.parametrize(
    ("owner", "name"),
    [
        ("../octocat", "demo"),
        ("octocat;--upload-pack=x", "demo"),
        ("octocat", "../demo"),
        ("octocat", "."),
        ("octocat", ".."),
        ("octocat", "demo/repo"),
        ("octocat", "demo\n--upload-pack=x"),
    ],
)
def test_target_rejects_hostile_owner_or_name(owner: str, name: str) -> None:
    with pytest.raises(RepositoryUnavailableError):
        get_clone_target(
            17,
            "octocat",
            "demo",
            "test-token",
            max_repo_size_mb=50,
            github_client=lambda _repo_id, _token: repository(owner=owner, name=name),
        )


@pytest.mark.parametrize("name", ["../x", "a b", "x;y", "", ".", ".."])
def test_clone_target_rejects_hostile_names(name: str) -> None:
    with pytest.raises(RepositoryUnavailableError):
        CloneTarget(17, "octocat", name, 0)


def test_clone_target_rejects_boolean_id() -> None:
    with pytest.raises(RepositoryUnavailableError):
        CloneTarget(True, "octocat", "demo", 0)


def test_identity_change_logs_no_repository_name_or_url(
    caplog: pytest.LogCaptureFixture,
):
    target = get_clone_target(
        17,
        "old-owner",
        "old-name",
        "test-token",
        max_repo_size_mb=50,
        github_client=lambda _repo_id, _token: repository(
            owner="new-owner", name="new-name"
        ),
    )

    assert target.clone_url == "https://github.com/new-owner/new-name.git"
    assert "github_repository_identity_changed" in caplog.text
    assert "new-owner" not in caplog.text
    assert "new-name" not in caplog.text
    assert "https://" not in caplog.text


class CompletedProcess:
    pid = 123
    returncode = 0

    def poll(self) -> int:
        return 0

    def wait(self, timeout: float | None = None) -> int:
        return 0

    def communicate(
        self, input: bytes | None = None, timeout: float | None = None
    ) -> tuple[bytes, None]:
        return COMMIT_SHA.encode("ascii") + b"\n", None

    def kill(self) -> None:
        self.returncode = -9


class RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], dict[str, str], Path, bool]] = []

    def __call__(
        self,
        argv: list[str],
        *,
        env: dict[str, str],
        cwd: Path,
        capture_stdout: bool = False,
    ) -> CompletedProcess:
        self.calls.append((argv, env, cwd, capture_stdout))
        if "clone" in argv:
            destination = Path(argv[-1])
            destination.mkdir()
            (destination / ".git").mkdir()
            (destination / "source.py").write_bytes(b"pass\n")
        return CompletedProcess()


def test_clone_argv_environment_and_commit_sha(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-17"
    run_dir.mkdir()
    runner = RecordingRunner()
    target = CloneTarget(17, "octocat", "demo", 10)

    commit_sha = clone_repository(
        target,
        run_dir,
        max_repo_size_mb=50,
        max_source_files=1000,
        deadline=time.monotonic() + 10,
        runner=runner,
        test_source_override="file:///test/hostile;--upload-pack=x",
    )

    clone_argv, environment, cwd, capture = runner.calls[0]
    assert clone_argv == [
        "git",
        "-c",
        "protocol.allow=never",
        "-c",
        "protocol.https.allow=always",
        "-c",
        "http.followRedirects=false",
        "-c",
        "credential.helper=",
        "-c",
        "protocol.file.allow=always",
        "clone",
        "--no-recurse-submodules",
        "--single-branch",
        "--no-hardlinks",
        "--template",
        str(run_dir / "empty-template"),
        "-c",
        "core.symlinks=false",
        "-c",
        f"core.hooksPath={run_dir / 'empty-hooks'}",
        "--",
        "file:///test/hostile;--upload-pack=x",
        str(run_dir / "repository"),
    ]
    assert clone_argv.count("core.symlinks=false") == 1
    assert clone_argv.count("credential.helper=") == 1
    assert CLONE_DISK_FACTOR == 2
    assert clone_argv.count("--single-branch") == 1
    assert "--depth" not in clone_argv
    assert "--branch" not in clone_argv
    assert cwd == run_dir
    assert capture is False
    assert environment["GIT_CONFIG_NOSYSTEM"] == "1"
    assert environment["GIT_CONFIG_GLOBAL"] == os.devnull
    assert environment["GIT_TERMINAL_PROMPT"] == "0"
    assert environment["GIT_LFS_SKIP_SMUDGE"] == "1"
    assert set(environment).issubset(
        {
            "PATH",
            "SYSTEMROOT",
            "WINDIR",
            "TEMP",
            "TMP",
            "TMPDIR",
            "GIT_CONFIG_NOSYSTEM",
            "GIT_CONFIG_GLOBAL",
            "GIT_TERMINAL_PROMPT",
            "GIT_LFS_SKIP_SMUDGE",
        }
    )
    assert runner.calls[1][0][-2:] == ["rev-parse", "HEAD"]
    assert runner.calls[1][3] is True
    assert commit_sha == COMMIT_SHA


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class SlowProcess:
    pid = 456

    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self.returncode: int | None = None
        self.killed = False

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        if self.returncode is not None:
            return self.returncode
        self.clock.now += timeout or 0
        raise subprocess.TimeoutExpired(["git"], timeout)

    def communicate(
        self, input: bytes | None = None, timeout: float | None = None
    ) -> tuple[bytes | None, None]:
        self.wait(timeout)
        return None, None

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9


def _never_finishing_runner(process: SlowProcess):
    def run(
        _argv: list[str],
        *,
        env: dict[str, str],
        cwd: Path,
        capture_stdout: bool = False,
    ) -> SlowProcess:
        return process

    return run


def test_watcher_kills_slow_process_on_deadline(tmp_path: Path) -> None:
    clock = FakeClock()
    process = SlowProcess(clock)
    killed: list[int] = []

    with pytest.raises(CloneTimedOutError):
        _run_monitored(
            ["git", "clone"],
            env={},
            cwd=tmp_path,
            deadline=2.5,
            runner=_never_finishing_runner(process),
            clock=clock,
            process_killer=lambda child: (killed.append(child.pid), child.kill()),
        )

    assert process.killed
    assert killed == [process.pid]


def test_watcher_kills_process_when_size_cap_is_breached(tmp_path: Path) -> None:
    clock = FakeClock()
    process = SlowProcess(clock)
    killed: list[int] = []

    with pytest.raises(RepositoryTooLargeError):
        _run_monitored(
            ["git", "clone"],
            env={},
            cwd=tmp_path,
            deadline=10,
            runner=_never_finishing_runner(process),
            clock=clock,
            size_fn=lambda _root, **_kwargs: TreeMeasurement(101, 1, 1),
            size_root=tmp_path,
            max_size_bytes=100,
            process_killer=lambda child: (killed.append(child.pid), child.kill()),
        )

    assert process.killed
    assert killed == [process.pid]


def test_watcher_kills_process_and_propagates_size_function_error(
    tmp_path: Path,
) -> None:
    clock = FakeClock()
    process = SlowProcess(clock)

    def broken_size_fn(_root: Path, **_kwargs) -> TreeMeasurement:
        raise TypeError("test size function failure")

    with pytest.raises(TypeError, match="test size function failure"):
        _run_monitored(
            ["git", "clone"],
            env={},
            cwd=tmp_path,
            deadline=10,
            runner=_never_finishing_runner(process),
            clock=clock,
            size_fn=broken_size_fn,
            size_root=tmp_path,
            max_size_bytes=100,
            process_killer=lambda child: child.kill(),
        )

    assert process.killed
    assert process.returncode == -9


def test_scan_tree_tolerant_mode_skips_vanished_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()

    class VanishingEntry:
        name = "vanished.py"
        path = str(root / name)

        def stat(self, *, follow_symlinks: bool) -> os.stat_result:
            raise FileNotFoundError()

    class EntryIterator:
        def __enter__(self):
            return iter([VanishingEntry()])

        def __exit__(self, *_args) -> None:
            return None

    monkeypatch.setattr("app.github.clone.os.scandir", lambda _path: EntryIterator())

    with pytest.raises(CloneAnalysisError):
        scan_tree(root)

    assert scan_tree(root, tolerant=True) == TreeMeasurement(0, 0, 0)


def test_clone_watcher_caps_whole_run_directory_at_twice_repository_limit(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run-17"
    run_dir.mkdir()
    clock = FakeClock()
    process = SlowProcess(clock)
    killed: list[int] = []
    observed_roots: list[Path] = []

    def size_fn(
        root: Path, *, exclude_git: bool = False, tolerant: bool = False
    ) -> TreeMeasurement:
        observed_roots.append(root)
        return TreeMeasurement(100 * 1024 * 1024 + 1, 1, 1)

    with pytest.raises(RepositoryTooLargeError):
        clone_repository(
            CloneTarget(17, "octocat", "demo", 1),
            run_dir,
            max_repo_size_mb=50,
            max_source_files=1000,
            deadline=10,
            runner=_never_finishing_runner(process),
            clock=clock,
            size_fn=size_fn,
            process_killer=lambda child: (killed.append(child.pid), child.kill()),
        )

    assert observed_roots == [run_dir]
    assert process.killed
    assert killed == [process.pid]


def test_post_clone_total_size_including_git_respects_two_x_cap(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run-17"
    run_dir.mkdir()
    max_clone_bytes = 2 * 1024 * 1024

    def size_fn(root: Path, *, exclude_git: bool = False, tolerant: bool = False):
        if root.name == "repository" and not exclude_git:
            return TreeMeasurement(max_clone_bytes + 1, 1, 1)
        return scan_tree(root, exclude_git=exclude_git, tolerant=tolerant)

    with pytest.raises(RepositoryTooLargeError):
        clone_repository(
            CloneTarget(17, "octocat", "demo", 1),
            run_dir,
            max_repo_size_mb=1,
            max_source_files=1000,
            deadline=time.monotonic() + 10,
            runner=RecordingRunner(),
            size_fn=size_fn,
        )


@pytest.mark.parametrize(
    ("failure_index", "expected_error"),
    [
        (0, RepositoryUnavailableError),
        (1, CloneAnalysisError),
    ],
)
def test_clone_and_rev_parse_nonzero_exit_map_to_distinct_errors(
    tmp_path: Path,
    failure_index: int,
    expected_error: type[Exception],
) -> None:
    run_dir = tmp_path / "run-17"
    run_dir.mkdir()

    class ExitedProcess(CompletedProcess):
        def __init__(self, returncode: int) -> None:
            self.returncode = returncode

        def poll(self) -> int:
            return self.returncode

        def communicate(
            self, input: bytes | None = None, timeout: float | None = None
        ) -> tuple[bytes, None]:
            return COMMIT_SHA.encode("ascii") + b"\n", None

    class ExitRunner(RecordingRunner):
        def __call__(
            self,
            argv: list[str],
            *,
            env: dict[str, str],
            cwd: Path,
            capture_stdout: bool = False,
        ) -> ExitedProcess:
            self.calls.append((argv, env, cwd, capture_stdout))
            if "clone" in argv and failure_index == 0:
                return ExitedProcess(128)
            if "clone" in argv:
                destination = Path(argv[-1])
                destination.mkdir()
                (destination / ".git").mkdir()
                (destination / "source.py").write_text("pass\n", encoding="ascii")
            return ExitedProcess(1 if capture_stdout else 0)

    with pytest.raises(expected_error):
        clone_repository(
            CloneTarget(17, "octocat", "demo", 1),
            run_dir,
            max_repo_size_mb=50,
            max_source_files=1000,
            deadline=time.monotonic() + 10,
            runner=ExitRunner(),
        )


@pytest.mark.parametrize(
    ("measurement", "max_repo_size_mb", "expected_error"),
    [
        (TreeMeasurement(0, 100_001, 1), 50, RepositoryTooLargeError),
        (TreeMeasurement(0, 1, 65), 50, RepositoryTooLargeError),
    ],
)
def test_post_clone_entry_and_depth_limits(
    tmp_path: Path,
    measurement: TreeMeasurement,
    max_repo_size_mb: int,
    expected_error: type[Exception],
) -> None:
    run_dir = tmp_path / "run-17"
    run_dir.mkdir()
    runner = RecordingRunner()

    def size_fn(root: Path, *, exclude_git: bool = False) -> TreeMeasurement:
        if root.name == "repository" and not exclude_git:
            return measurement
        return scan_tree(root, exclude_git=exclude_git)

    with pytest.raises(expected_error):
        clone_repository(
            CloneTarget(17, "octocat", "demo", 1),
            run_dir,
            max_repo_size_mb=max_repo_size_mb,
            max_source_files=1000,
            deadline=time.monotonic() + 10,
            runner=runner,
            size_fn=size_fn,
        )


def test_post_clone_checkout_size_limit(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-17"
    run_dir.mkdir()

    def size_fn(root: Path, *, exclude_git: bool = False) -> TreeMeasurement:
        if root.name == "repository" and exclude_git:
            return TreeMeasurement(1024 * 1024 + 1, 1, 1)
        return scan_tree(root, exclude_git=exclude_git)

    with pytest.raises(RepositoryTooLargeError):
        clone_repository(
            CloneTarget(17, "octocat", "demo", 1),
            run_dir,
            max_repo_size_mb=1,
            max_source_files=1000,
            deadline=time.monotonic() + 10,
            runner=RecordingRunner(),
            size_fn=size_fn,
        )


def test_supported_file_count_has_no_inventory_and_accepts_predicate(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repository"
    (root / "nested").mkdir(parents=True)
    (root / ".git").mkdir()
    (root / "one.py").touch()
    (root / "nested" / "two.ts").touch()
    (root / ".git" / "ignored.js").touch()

    assert count_supported_files(root) == 2
    assert count_supported_files(root, lambda relative: "nested" in relative.parts) == 1


def test_post_clone_supported_file_count_limit(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-17"
    run_dir.mkdir()

    def create_two_files(argv, **kwargs):
        if "clone" in argv:
            destination = Path(argv[-1])
            destination.mkdir()
            (destination / ".git").mkdir()
            (destination / "one.py").touch()
            (destination / "two.ts").touch()
        return CompletedProcess()

    with pytest.raises(RepositoryTooLargeError):
        clone_repository(
            CloneTarget(17, "octocat", "demo", 1),
            run_dir,
            max_repo_size_mb=50,
            max_source_files=1,
            deadline=time.monotonic() + 10,
            runner=create_two_files,
        )


def test_clone_uses_injected_count_exclusion_predicate(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-17"
    run_dir.mkdir()

    def create_two_files(argv, **kwargs):
        if "clone" in argv:
            destination = Path(argv[-1])
            destination.mkdir()
            (destination / ".git").mkdir()
            (destination / "one.py").touch()
            (destination / "two.ts").touch()
        return CompletedProcess()

    commit_sha = clone_repository(
        CloneTarget(17, "octocat", "demo", 1),
        run_dir,
        max_repo_size_mb=50,
        max_source_files=1,
        deadline=time.monotonic() + 10,
        runner=create_two_files,
        is_excluded=lambda relative: relative.name == "two.ts",
    )

    assert commit_sha == COMMIT_SHA


def _git(cwd: Path, *args: str, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=True,
        shell=False,
        text=True,
    )
    return completed.stdout.strip()


def _make_local_repository(path: Path) -> str:
    path.mkdir()
    _git(path, "init")
    _git(path, "config", "user.name", "RepoPulse Test")
    _git(path, "config", "user.email", "test@example.invalid")
    (path / "source.py").write_text("value = 1\n", encoding="utf-8")
    _git(path, "add", "source.py")
    _git(path, "commit", "-m", "first")
    (path / "source.py").write_text("value = 2\n", encoding="utf-8")
    _git(path, "add", "source.py")
    _git(path, "commit", "-m", "second")
    return _git(path, "rev-parse", "HEAD")


def test_local_clone_full_history_and_commit_sha(tmp_path: Path) -> None:
    source = tmp_path / "source"
    expected_sha = _make_local_repository(source)
    run_dir = tmp_path / "run-17"
    run_dir.mkdir()

    actual_sha = clone_repository(
        CloneTarget(17, "octocat", "demo", 1),
        run_dir,
        max_repo_size_mb=50,
        max_source_files=1000,
        deadline=time.monotonic() + 60,
        test_source_override=source.as_uri(),
    )

    assert actual_sha == expected_sha
    assert _git(run_dir / "repository", "rev-list", "--count", "HEAD") == "2"
    assert count_supported_files(run_dir / "repository") == 1


def test_local_clone_checks_out_git_symlink_entry_as_regular_file(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    _make_local_repository(source)
    link_blob = tmp_path / "link-target"
    link_blob.write_text("source.py", encoding="ascii")
    blob_sha = _git(source, "hash-object", "-w", str(link_blob))
    _git(
        source,
        "update-index",
        "--add",
        "--cacheinfo",
        f"120000,{blob_sha},link.py",
    )
    _git(source, "commit", "-m", "add symlink entry")
    expected_sha = _git(source, "rev-parse", "HEAD")

    run_dir = tmp_path / "run-17"
    run_dir.mkdir()
    actual_sha = clone_repository(
        CloneTarget(17, "octocat", "demo", 1),
        run_dir,
        max_repo_size_mb=50,
        max_source_files=1000,
        deadline=time.monotonic() + 60,
        test_source_override=source.as_uri(),
    )

    checkout_link = run_dir / "repository" / "link.py"
    assert actual_sha == expected_sha
    assert checkout_link.is_file()
    assert not checkout_link.is_symlink()
    assert scan_tree(run_dir / "repository").size_bytes >= len("source.py")
    assert count_supported_files(run_dir / "repository") == 2


def test_clone_does_not_run_template_hook_or_recurse_submodule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    submodule = tmp_path / "submodule"
    _make_local_repository(submodule)

    source = tmp_path / "source-with-submodule"
    source.mkdir()
    _git(source, "init")
    _git(source, "config", "user.name", "RepoPulse Test")
    _git(source, "config", "user.email", "test@example.invalid")
    _git(
        source,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        submodule.as_uri(),
        "vendor/submodule",
    )
    _git(source, "commit", "-m", "add submodule")

    hostile_template = tmp_path / "hostile-template"
    hooks = hostile_template / "hooks"
    hooks.mkdir(parents=True)
    marker = tmp_path / "hook-ran"
    hook = hooks / "post-checkout"
    hook.write_text(
        f"#!/bin/sh\nprintf ran > '{marker}'\n",
        encoding="utf-8",
    )
    try:
        hook.chmod(0o700)
    except OSError:
        pytest.fail("The test hook could not be made executable.")
    monkeypatch.setenv("GIT_TEMPLATE_DIR", str(hostile_template))

    run_dir = tmp_path / "run-17"
    run_dir.mkdir()
    clone_repository(
        CloneTarget(17, "octocat", "demo", 1),
        run_dir,
        max_repo_size_mb=50,
        max_source_files=1000,
        deadline=time.monotonic() + 60,
        test_source_override=source.as_uri(),
    )

    checkout = run_dir / "repository"
    assert not marker.exists()
    assert not (checkout / ".git" / "hooks" / "post-checkout").exists()
    assert not (checkout / "vendor" / "submodule" / "source.py").exists()


def test_clone_does_not_follow_symlink(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_bytes(b"x" * 4096)
    link = root / "linked.py"
    try:
        link.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"OS refused symlink creation: {error}")

    assert scan_tree(root).size_bytes < outside.stat().st_size
    assert count_supported_files(root) == 0


def test_real_process_tree_is_killed_after_size_breach(tmp_path: Path) -> None:
    pid_file = tmp_path / "grandchild.pid"
    child_script = (
        "import pathlib, subprocess, sys, time; "
        "child = subprocess.Popen([sys.executable, '-c', "
        "'import time; time.sleep(60)']); "
        f"pathlib.Path({str(pid_file)!r}).write_text(str(child.pid)); "
        "time.sleep(60)"
    )
    argv = [sys.executable, "-c", child_script]
    deadline = time.monotonic() + 15

    def size_fn(_root: Path, **_kwargs) -> TreeMeasurement:
        if pid_file.exists():
            return TreeMeasurement(2, 1, 1)
        return TreeMeasurement(0, 0, 0)

    with pytest.raises(RepositoryTooLargeError):
        _run_monitored(
            argv,
            env=_git_environment_for_python(),
            cwd=tmp_path,
            deadline=deadline,
            runner=_start_python_process,
            clock=time.monotonic,
            size_fn=size_fn,
            size_root=tmp_path,
            max_size_bytes=1,
            process_killer=_kill_process_tree,
        )

    grandchild_pid = int(pid_file.read_text(encoding="ascii"))
    _assert_process_stopped(grandchild_pid)


def _git_environment_for_python() -> dict[str, str]:
    environment = dict(os.environ)
    environment["GIT_CONFIG_NOSYSTEM"] = "1"
    environment["GIT_CONFIG_GLOBAL"] = os.devnull
    environment["GIT_TERMINAL_PROMPT"] = "0"
    environment["GIT_LFS_SKIP_SMUDGE"] = "1"
    return environment


def _start_python_process(
    argv,
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
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        shell=False,
        start_new_session=not is_windows,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if is_windows else 0,
    )


def _assert_process_stopped(pid: int) -> None:
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.1)
    if os.name == "nt":
        subprocess.run(
            ["taskkill.exe", "/PID", str(pid), "/T", "/F"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            check=False,
        )
    else:
        os.kill(pid, signal.SIGKILL)
    pytest.fail("The cloned process tree outlived the monitored operation.")
