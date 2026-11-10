"""Tests for temporary workspace safety and bounded source reads."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import pytest

from app.github.workspace import (
    SourceReadError,
    WorkspaceError,
    cleanup_run_dir,
    create_run_dir,
    decode_source_bytes,
    prepare_temp_root,
    read_source_file,
    sweep_orphaned_runs,
)


def _make_symlink(link: Path, target: Path, *, directory: bool = False) -> None:
    try:
        link.symlink_to(target, target_is_directory=directory)
    except OSError as error:
        pytest.skip(f"OS refused symlink creation: {error}")


def _make_junction(link: Path, target: Path) -> None:
    result = subprocess.run(
        ["cmd.exe", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        pytest.skip(f"Windows refused junction creation: {result.stderr.strip()}")


def test_prepare_temp_root_creates_private_directory(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    assert prepare_temp_root(root) == root.resolve()
    assert root.is_dir()
    if os.name != "nt":
        assert stat.S_IMODE(root.stat().st_mode) == 0o700
        assert root.stat().st_uid == os.getuid()


def test_prepare_temp_root_rejects_filesystem_root_and_home(tmp_path: Path) -> None:
    invalid_roots = [Path(Path.cwd().anchor), Path.home()]
    for root in invalid_roots:
        with pytest.raises(WorkspaceError):
            prepare_temp_root(root)

    if os.name == "nt":
        with pytest.raises(WorkspaceError):
            prepare_temp_root(Path(tempfile.gettempdir()))


def test_prepare_temp_root_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    _make_symlink(link, target, directory=True)
    with pytest.raises(WorkspaceError):
        prepare_temp_root(link)


def test_prepare_temp_root_rejects_regular_file(tmp_path: Path) -> None:
    root = tmp_path / "not-a-directory"
    root.write_text("not a directory", encoding="utf-8")
    with pytest.raises(WorkspaceError):
        prepare_temp_root(root)


def test_prepare_temp_root_without_determined_home_still_checks_other_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable_home(cls: type[Path]) -> Path:
        raise RuntimeError("home directory unavailable")

    monkeypatch.setattr(Path, "home", classmethod(unavailable_home))
    root = tmp_path / "workspace"
    assert prepare_temp_root(root) == root.resolve()

    with pytest.raises(WorkspaceError):
        prepare_temp_root(Path(Path.cwd().anchor))

    wrong_mode = tmp_path / "wrong-mode"
    wrong_mode.mkdir(mode=0o755)
    wrong_mode.chmod(0o755)
    if os.name != "nt":
        with pytest.raises(WorkspaceError, match="permissions"):
            prepare_temp_root(wrong_mode)


@pytest.mark.skipif(os.name == "nt", reason="POSIX-only owner and mode validation")
def test_prepare_temp_root_rejects_existing_wrong_mode(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir(mode=0o755)
    root.chmod(0o755)
    with pytest.raises(WorkspaceError, match="permissions"):
        prepare_temp_root(root)


@pytest.mark.skipif(os.name != "nt", reason="Windows temp-root containment rule")
def test_prepare_temp_root_requires_strict_temp_descendant(tmp_path: Path) -> None:
    with pytest.raises(WorkspaceError):
        prepare_temp_root(Path(tempfile.gettempdir()))
    with pytest.raises(WorkspaceError):
        prepare_temp_root(Path.home() / "outside-temp")


def test_create_run_dir_is_exclusive_and_private(tmp_path: Path) -> None:
    root = prepare_temp_root(tmp_path / "workspace")
    run_dir = create_run_dir(root, 17)
    assert run_dir == root / "run-17"
    assert run_dir.is_dir()
    if os.name != "nt":
        assert stat.S_IMODE(run_dir.stat().st_mode) == 0o700
    with pytest.raises(WorkspaceError):
        create_run_dir(root, 17)
    with pytest.raises(ValueError):
        create_run_dir(root, True)


def test_cleanup_is_idempotent_and_rejects_outside_paths(tmp_path: Path) -> None:
    root = prepare_temp_root(tmp_path / "workspace")
    run_dir = create_run_dir(root, 18)
    assert cleanup_run_dir(root, run_dir) is None
    assert cleanup_run_dir(root, run_dir) is None

    outside = tmp_path / "run-19"
    outside.mkdir()
    warning = cleanup_run_dir(root, outside)
    assert warning is not None
    assert warning.stage == "cleanup"
    assert warning.code == "cleanup_failed"
    assert warning.message == "Temporary files could not be fully removed."
    assert str(outside) not in warning.message
    assert outside.is_dir()


def test_cleanup_does_not_follow_posix_symlinks(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("Use the junction-specific test on Windows.")
    root = prepare_temp_root(tmp_path / "workspace")
    run_dir = create_run_dir(root, 20)
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "marker"
    marker.write_text("keep", encoding="utf-8")
    _make_symlink(run_dir / "outside", outside, directory=True)
    _make_symlink(run_dir / "outside-file", marker)

    assert cleanup_run_dir(root, run_dir) is None
    assert marker.read_text(encoding="utf-8") == "keep"


@pytest.mark.skipif(os.name != "nt", reason="Windows junction behavior")
def test_cleanup_does_not_traverse_windows_junction(tmp_path: Path) -> None:
    root = prepare_temp_root(tmp_path / "workspace")
    run_dir = create_run_dir(root, 21)
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "marker.txt"
    marker.write_text("keep", encoding="utf-8")
    _make_junction(run_dir / "outside", outside)

    assert cleanup_run_dir(root, run_dir) is None
    assert outside.is_dir()
    assert marker.read_text(encoding="utf-8") == "keep"


@pytest.mark.skipif(os.name != "nt", reason="Windows junction validation")
def test_prepare_temp_root_rejects_junction(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    junction = tmp_path / "workspace-junction"
    _make_junction(junction, target)
    with pytest.raises(WorkspaceError):
        prepare_temp_root(junction)


@pytest.mark.skipif(os.name != "nt", reason="Windows read-only attribute handling")
def test_cleanup_clears_read_only_files(tmp_path: Path) -> None:
    root = prepare_temp_root(tmp_path / "workspace")
    run_dir = create_run_dir(root, 22)
    git_dir = run_dir / ".git"
    git_dir.mkdir()
    readonly = git_dir / "config"
    readonly.write_text("git metadata", encoding="utf-8")
    readonly.chmod(stat.S_IREAD)

    assert cleanup_run_dir(root, run_dir) is None
    assert not run_dir.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows open-file deletion semantics")
def test_cleanup_reports_locked_file(tmp_path: Path) -> None:
    root = prepare_temp_root(tmp_path / "workspace")
    run_dir = create_run_dir(root, 23)
    locked = run_dir / "locked"
    locked.write_bytes(b"locked")
    handle = locked.open("rb")
    try:
        warning = cleanup_run_dir(root, run_dir)
        assert warning is not None
        assert warning.code == "cleanup_failed"
        assert str(locked) not in warning.message
    finally:
        handle.close()
    assert cleanup_run_dir(root, run_dir) is None


def test_cleanup_rejects_run_directory_symlink(tmp_path: Path) -> None:
    root = prepare_temp_root(tmp_path / "workspace")
    outside = tmp_path / "outside-run"
    outside.mkdir()
    marker = outside / "marker"
    marker.write_text("keep", encoding="utf-8")
    link = root / "run-24"
    if os.name == "nt":
        _make_junction(link, outside)
    else:
        _make_symlink(link, outside, directory=True)

    warning = cleanup_run_dir(root, link)
    assert warning is not None
    assert marker.read_text(encoding="utf-8") == "keep"


def test_sweep_removes_only_inactive_canonical_run_directories(
    tmp_path: Path,
) -> None:
    root = prepare_temp_root(tmp_path / "workspace")
    removed = create_run_dir(root, 1)
    active = create_run_dir(root, 2)
    (root / "run-3").write_text("not a directory", encoding="utf-8")
    (root / "run-0").mkdir()
    (root / "run-04").mkdir()
    (root / "run-x").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "marker"
    marker.write_text("keep", encoding="utf-8")
    link = root / "run-5"
    if os.name == "nt":
        _make_junction(link, outside)
    else:
        _make_symlink(link, outside, directory=True)

    result = sweep_orphaned_runs(root, active_run_ids={2})
    assert result.removed_ids == (1,)
    assert result.failed_ids == ()
    assert not removed.exists()
    assert active.is_dir()
    assert marker.read_text(encoding="utf-8") == "keep"


def test_sweep_creates_missing_root_and_reports_empty_result(tmp_path: Path) -> None:
    root = tmp_path / "missing-workspace"
    result = sweep_orphaned_runs(root)
    assert root.is_dir()
    assert result.removed_ids == ()
    assert result.failed_ids == ()


def test_sweep_defaults_to_no_active_run_ids(tmp_path: Path) -> None:
    root = prepare_temp_root(tmp_path / "workspace")
    orphan = create_run_dir(root, 30)
    result = sweep_orphaned_runs(root)
    assert result.removed_ids == (30,)
    assert result.failed_ids == ()
    assert not orphan.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows open-file deletion semantics")
def test_sweep_reports_locked_orphan_and_continues(tmp_path: Path) -> None:
    root = prepare_temp_root(tmp_path / "workspace")
    run_dir = create_run_dir(root, 31)
    (run_dir / "locked").write_bytes(b"locked")
    handle = (run_dir / "locked").open("rb")
    try:
        result = sweep_orphaned_runs(root)
        assert result.removed_ids == ()
        assert result.failed_ids == (31,)
    finally:
        handle.close()
    assert cleanup_run_dir(root, run_dir) is None


@pytest.mark.parametrize(
    "relative_path",
    [
        "",
        ".",
        "./source.py",
        "../source.py",
        "dir/../source.py",
        "dir/./source.py",
        "dir//source.py",
        "dir\\\\source.py",
        "source.py\x00",
        "source.py\x1f",
    ],
)
def test_read_source_rejects_unsafe_relative_paths(
    tmp_path: Path, relative_path: str
) -> None:
    with pytest.raises(SourceReadError) as error:
        read_source_file(tmp_path, relative_path, 100)
    assert error.value.reason == "unsafe_path"


def test_read_source_rejects_absolute_paths(tmp_path: Path) -> None:
    absolute = tmp_path / "source.py"
    with pytest.raises(SourceReadError, match="unsafe_path"):
        read_source_file(tmp_path, str(absolute), 100)


@pytest.mark.skipif(os.name != "nt", reason="Windows-specific path forms")
@pytest.mark.parametrize(
    "relative_path",
    [r"C:\Windows\win.ini", r"\\server\share\file", "dir:name.py", "CON.txt"],
)
def test_read_source_rejects_windows_device_and_drive_paths(
    tmp_path: Path, relative_path: str
) -> None:
    with pytest.raises(SourceReadError, match="unsafe_path"):
        read_source_file(tmp_path, relative_path, 100)


def test_read_source_enforces_exact_size_limit(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    (root / "source.py").write_bytes(b"1234")
    assert read_source_file(root, "source.py", 4) == b"1234"
    with pytest.raises(SourceReadError) as error:
        read_source_file(root, "source.py", 3)
    assert error.value.reason == "too_large"


@pytest.mark.skipif(
    sys.platform != "linux", reason="Case-distinct path check requires Linux"
)
def test_read_source_preserves_case_distinct_paths(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    (root / "Case.py").write_bytes(b"upper")
    (root / "case.py").write_bytes(b"lower")
    assert read_source_file(root, "Case.py", 10) == b"upper"
    assert read_source_file(root, "case.py", 10) == b"lower"


def test_read_source_rejects_directories_and_symlinks(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    directory = root / "directory"
    directory.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_bytes(b"outside")
    link = root / "link.py"
    _make_symlink(link, outside)

    with pytest.raises(SourceReadError) as directory_error:
        read_source_file(root, "directory", 100)
    assert directory_error.value.reason == "not_regular"
    with pytest.raises(SourceReadError) as symlink_error:
        read_source_file(root, "link.py", 100)
    assert symlink_error.value.reason == "unsafe_path"


@pytest.mark.skipif(os.name != "nt", reason="Windows junction safe-read check")
def test_read_source_rejects_junction_escape(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.py").write_bytes(b"outside")
    _make_junction(root / "linked", outside)
    with pytest.raises(SourceReadError) as read_error:
        read_source_file(root, "linked/secret.py", 100)
    assert read_error.value.reason == "unsafe_path"


def test_read_source_preserves_binary_bytes(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    binary = b"\x00\xff\x80\x01"
    (root / "data.bin").write_bytes(binary)
    assert read_source_file(root, "data.bin", len(binary)) == binary


def test_read_source_rejects_hardlinks_when_supported(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    source = root / "source.py"
    source.write_bytes(b"content")
    hardlink = root / "hardlink.py"
    try:
        os.link(source, hardlink)
    except OSError as error:
        pytest.skip(f"Filesystem refused hard-link creation: {error}")

    with pytest.raises(SourceReadError) as read_error:
        read_source_file(root, "hardlink.py", 100)
    assert read_error.value.reason == "unsafe_path"


@pytest.mark.skipif(sys.platform != "linux", reason="FIFO test requires Linux")
def test_read_source_rejects_fifo(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    fifo = root / "pipe.py"
    os.mkfifo(fifo)
    with pytest.raises(SourceReadError) as read_error:
        read_source_file(root, "pipe.py", 100)
    assert read_error.value.reason == "not_regular"


@pytest.mark.skipif(
    sys.platform != "linux", reason="Race-resistant dir_fd read requires Linux"
)
def test_read_source_symlink_swap_never_returns_outside_contents(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    source = root / "race.py"
    hidden = root / "race-hidden.py"
    outside = tmp_path / "outside.py"
    source.write_bytes(b"inside")
    outside.write_bytes(b"outside")
    stop = threading.Event()

    def swap_path() -> None:
        while not stop.is_set():
            try:
                os.replace(source, hidden)
                os.symlink(outside, source)
                source.unlink()
                os.replace(hidden, source)
            except OSError:
                if source.is_symlink():
                    source.unlink()
                if hidden.exists() and not source.exists():
                    os.replace(hidden, source)

    worker = threading.Thread(target=swap_path)
    worker.start()
    observed: list[bytes | str] = []
    try:
        for _ in range(250):
            try:
                observed.append(read_source_file(root, "race.py", 100))
            except SourceReadError as error:
                observed.append(error.reason)
    finally:
        stop.set()
        worker.join(timeout=5)
        if hidden.exists() and not source.exists():
            os.replace(hidden, source)

    assert not worker.is_alive()
    assert observed
    assert b"outside" not in observed
    assert all(
        value == b"inside" or value in {"unsafe_path", "unreadable"}
        for value in observed
    )


def test_decode_source_bytes_strips_bom_and_replaces_invalid_utf8() -> None:
    assert decode_source_bytes(b"\xef\xbb\xbfhello") == "hello"
    assert decode_source_bytes(b"bad:\xff") == "bad:\ufffd"
