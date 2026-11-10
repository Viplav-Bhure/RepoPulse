"""Verify clone workspace behavior from inside the backend container."""

from __future__ import annotations

import json
import os
import re
import signal
import stat
import subprocess
import sys
import threading
import time
import urllib.request
from collections import Counter
from pathlib import Path

from app.github.clone import (
    CLONE_DISK_FACTOR,
    MAX_TREE_DEPTH,
    MAX_TREE_ENTRIES,
    SUPPORTED_EXTENSIONS,
    CloneTarget,
    CloneTimedOutError,
    RepositoryTooLargeError,
    clone_repository,
    count_supported_files,
    is_link_or_reparse,
)
from app.github.workspace import (
    SourceReadError,
    cleanup_run_dir,
    create_run_dir,
    prepare_temp_root,
    read_source_file,
    sweep_orphaned_runs,
)

TEMP_ROOT = Path("/tmp/repopulse-clones")
OUTSIDE_ROOT = Path("/tmp/s3c-outside")
MAX_REPOSITORY_SIZE_KB = 40_000
SOURCE_FILE_LIMIT_BYTES = 1_048_576
GITHUB_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
_failed = False
_checks = 0


def report(name: str, passed: bool, details: str) -> None:
    global _checks, _failed
    _checks += 1
    if not passed:
        _failed = True
    result = "PASS" if passed else "FAIL"
    print(f"{result} {name} {details}", flush=True)


def exception_type(error: BaseException) -> str:
    return type(error).__name__


def used_bytes(root: Path) -> int:
    filesystem = os.statvfs(root)
    return (filesystem.f_blocks - filesystem.f_bfree) * filesystem.f_frsize


def mount_for(path: Path) -> tuple[str, str] | None:
    with Path("/proc/mounts").open(encoding="utf-8") as mounts:
        for line in mounts:
            fields = line.split()
            if len(fields) >= 4 and fields[1] == str(path):
                return fields[2], fields[3]
    return None


def verify_environment() -> bool:
    environment_passed = False
    try:
        uid = os.getuid()
        git_version = subprocess.run(
            ["git", "--version"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        ).stdout.strip()
        version = git_version.removeprefix("git version ")
        environment_passed = uid == 10001 and bool(version)
        report(
            "container-environment",
            environment_passed,
            f"uid={uid} python={sys.version_info.major}.{sys.version_info.minor}."
            f"{sys.version_info.micro} git={version or 'unavailable'}",
        )
    except Exception as error:
        report("container-environment", False, f"error_type={exception_type(error)}")
        return False

    limits_match = (
        CLONE_DISK_FACTOR == 2 and MAX_TREE_DEPTH == 64 and MAX_TREE_ENTRIES == 100_000
    )
    report(
        "clone-limits",
        limits_match,
        f"repo_size_mb=50 source_files=1000 depth={MAX_TREE_DEPTH} "
        f"entries={MAX_TREE_ENTRIES} factor={CLONE_DISK_FACTOR}",
    )

    try:
        mount = mount_for(TEMP_ROOT)
        filesystem_stats = os.statvfs(TEMP_ROOT)
        capacity = filesystem_stats.f_blocks * filesystem_stats.f_frsize
        used = (filesystem_stats.f_blocks - filesystem_stats.f_bfree) * (
            filesystem_stats.f_frsize
        )
        filesystem, options = mount if mount else ("missing", "")
        option_map = dict(
            item.split("=", 1) for item in options.split(",") if "=" in item
        )
        capacity_mib = capacity / (1024 * 1024)
        mode = option_map.get("mode", "").lstrip("0") or "0"
        passed = (
            filesystem == "tmpfs"
            and 250 <= capacity_mib <= 260
            and option_map.get("uid") == "10001"
            and option_map.get("gid") == "10001"
            and mode == "700"
        )
        recognized = ",".join(
            f"{key}={option_map[key]}"
            for key in ("size", "uid", "gid", "mode")
            if key in option_map
        )
        report(
            "tmpfs-mount",
            passed,
            f"filesystem={filesystem} capacity_mib={capacity_mib:.1f} "
            f"used_bytes={used} options={recognized or 'missing'}",
        )
    except Exception as error:
        report("tmpfs-mount", False, f"error_type={exception_type(error)}")
        passed = False

    try:
        root = prepare_temp_root(TEMP_ROOT)
        root_stat = root.stat()
        mode = stat.S_IMODE(root_stat.st_mode)
        root_passed = root_stat.st_uid == 10001 and mode == 0o700
        report(
            "prepare-temp-root",
            root_passed,
            f"owner_uid={root_stat.st_uid} mode={mode:04o}",
        )
    except Exception as error:
        report("prepare-temp-root", False, f"error_type={exception_type(error)}")
        root_passed = False
    return environment_passed and limits_match and passed and root_passed


def fetch_target(specification: str) -> tuple[CloneTarget, str]:
    parts = specification.split("/")
    if (
        len(parts) != 2
        or not GITHUB_NAME_PATTERN.fullmatch(parts[0])
        or not GITHUB_NAME_PATTERN.fullmatch(parts[1])
        or parts[1] in {".", ".."}
    ):
        raise ValueError("invalid repository specification")

    request_url = f"https://api.github.com/repos/{parts[0]}/{parts[1]}"
    request = urllib.request.Request(
        request_url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "RepoPulse-S3c-container-check",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = response.read(1_048_577)
    if len(payload) > 1_048_576:
        raise ValueError("repository response too large")
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("invalid repository response")
    owner_data = data.get("owner")
    if not isinstance(owner_data, dict):
        raise ValueError("invalid repository owner")
    owner = owner_data.get("login")
    name = data.get("name")
    full_name = data.get("full_name")
    repository_id = data.get("id")
    size_kb = data.get("size")
    if (
        data.get("private") is not False
        or not isinstance(owner, str)
        or not GITHUB_NAME_PATTERN.fullmatch(owner)
        or not isinstance(name, str)
        or not GITHUB_NAME_PATTERN.fullmatch(name)
        or name in {".", ".."}
        or not isinstance(full_name, str)
        or not re.fullmatch(r"[A-Za-z0-9._-]{1,100}/[A-Za-z0-9._-]{1,100}", full_name)
        or isinstance(repository_id, bool)
        or not isinstance(repository_id, int)
        or isinstance(size_kb, bool)
        or not isinstance(size_kb, int)
        or size_kb < 0
    ):
        raise ValueError("repository is private or metadata is invalid")
    return CloneTarget(repository_id, owner, name, size_kb), full_name


def checkout_inventory(repository_dir: Path) -> tuple[list[str], list[int]]:
    source_paths: list[str] = []
    link_counts: list[int] = []
    pending: list[tuple[Path, Path, bool]] = [(repository_dir, Path(), True)]
    while pending:
        directory, relative_directory, is_root = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                if is_root and entry.name == ".git":
                    continue
                entry_stat = entry.stat(follow_symlinks=False)
                relative_path = relative_directory / entry.name
                if stat.S_ISDIR(entry_stat.st_mode):
                    pending.append((Path(entry.path), relative_path, False))
                    continue
                if stat.S_ISREG(entry_stat.st_mode) or is_link_or_reparse(entry_stat):
                    link_counts.append(entry_stat.st_nlink)
                if Path(entry.name).suffix.lower() in SUPPORTED_EXTENSIONS:
                    source_paths.append(relative_path.as_posix())
    return source_paths, link_counts


def strict_measure(repository_dir: Path, exclude_git: bool = False) -> tuple[int, int]:
    size_bytes = 0
    entries_count = 0
    pending: list[tuple[Path, bool]] = [(repository_dir, True)]
    while pending:
        directory, is_root = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                if exclude_git and is_root and entry.name == ".git":
                    continue
                entry_stat = entry.stat(follow_symlinks=False)
                entries_count += 1
                if is_link_or_reparse(entry_stat):
                    size_bytes += entry_stat.st_size
                elif stat.S_ISDIR(entry_stat.st_mode):
                    pending.append((Path(entry.path), False))
                elif stat.S_ISREG(entry_stat.st_mode):
                    size_bytes += entry_stat.st_size
                else:
                    raise ValueError("non-file entry in checkout")
    return size_bytes, entries_count


def sample_usage(
    root: Path, stop: threading.Event, peak: list[int], errors: list[bool]
) -> None:
    while not stop.wait(0.2):
        try:
            peak[0] = max(peak[0], used_bytes(root))
        except OSError:
            errors[0] = True


def cleanup_created_run(run_dir: Path, baseline: int | None = None) -> bool:
    warning = cleanup_run_dir(TEMP_ROOT, run_dir)
    try:
        missing = not run_dir.exists() and not run_dir.is_symlink()
        current = used_bytes(TEMP_ROOT) if baseline is not None else None
        usage_restored = baseline is None or current == baseline
        passed = warning is None and missing and usage_restored
        details = (
            f"warning={'none' if warning is None else warning.code} gone={missing}"
        )
        if baseline is not None:
            details += f" used_bytes={current} baseline_bytes={baseline}"
        report(f"cleanup-{run_dir.name}", passed, details)
        return passed
    except Exception as error:
        report(
            f"cleanup-{run_dir.name}",
            False,
            f"error_type={exception_type(error)}",
        )
        return False


def verify_repository(target: CloneTarget, run_id: int) -> None:
    baseline = used_bytes(TEMP_ROOT)
    run_dir = create_run_dir(TEMP_ROOT, run_id)
    repository_dir = run_dir / "repository"
    peak = [baseline]
    sample_errors = [False]
    stop = threading.Event()
    sampler = threading.Thread(
        target=sample_usage,
        args=(TEMP_ROOT, stop, peak, sample_errors),
        daemon=True,
    )
    started = time.monotonic()
    commit_sha: str | None = None
    clone_error: BaseException | None = None
    try:
        try:
            sampler.start()
            try:
                commit_sha = clone_repository(
                    target,
                    run_dir,
                    max_repo_size_mb=50,
                    max_source_files=1000,
                    deadline=time.monotonic() + 120,
                )
            except Exception as error:
                clone_error = error
        finally:
            stop.set()
            if sampler.ident is not None:
                sampler.join(timeout=3)

        peak[0] = max(peak[0], used_bytes(TEMP_ROOT))
        elapsed = time.monotonic() - started
        if clone_error is None:
            clone_passed = commit_sha is not None
            error_details = "none"
        elif isinstance(clone_error, RepositoryTooLargeError):
            clone_passed = True
            error_details = "RepositoryTooLargeError"
        else:
            clone_passed = False
            error_details = exception_type(clone_error)
        report(
            f"repo-{run_id}-clone",
            clone_passed and not sample_errors[0] and not sampler.is_alive(),
            f"elapsed_seconds={elapsed:.2f} commit_sha={commit_sha or 'none'} "
            f"error_type={error_details}",
        )

        if not repository_dir.is_dir():
            raise FileNotFoundError
        total_bytes, total_entries = strict_measure(repository_dir)
        checkout_bytes, _checkout_entries = strict_measure(
            repository_dir, exclude_git=True
        )
        supported_count = count_supported_files(repository_dir)
        source_paths, link_counts = checkout_inventory(repository_dir)
        read_errors: Counter[str] = Counter()
        readable = 0
        for relative_path in source_paths:
            try:
                read_source_file(repository_dir, relative_path, SOURCE_FILE_LIMIT_BYTES)
                readable += 1
            except SourceReadError as error:
                read_errors[error.reason] += 1
        ratio = (
            f"{total_bytes / (target.size_kb * 1024):.4f}" if target.size_kb else "n/a"
        )
        link_range = (
            f"{min(link_counts)}-{max(link_counts)}" if link_counts else "empty"
        )
        reasons = (
            ",".join(
                f"{reason}:{count}" for reason, count in sorted(read_errors.items())
            )
            or "none"
        )
        report(
            f"repo-{run_id}-inventory",
            bool(link_counts) and all(count == 1 for count in link_counts),
            f"total_bytes={total_bytes} entries={total_entries} "
            f"checkout_bytes={checkout_bytes} supported_files={supported_count} "
            f"ratio={ratio} peak_tmpfs_used_bytes={peak[0]} "
            f"nlink_min_max={link_range} source_reads={readable} "
            f"read_errors={reasons}",
        )
    except Exception as error:
        report(
            f"repo-{run_id}-verification",
            False,
            f"error_type={exception_type(error)} peak_tmpfs_used_bytes={peak[0]}",
        )
    finally:
        stop.set()
        if sampler.ident is not None and sampler.is_alive():
            sampler.join(timeout=3)
        cleanup_created_run(run_dir, baseline)


def git_process_count() -> int:
    count = 0
    for process_dir in Path("/proc").iterdir():
        if not process_dir.name.isdigit():
            continue
        try:
            command_line = (process_dir / "cmdline").read_bytes()
        except OSError:
            continue
        if b"git" in command_line.lower():
            count += 1
    return count


def wait_for_git_processes(timeout: float = 2.0) -> int:
    deadline = time.monotonic() + timeout
    count = git_process_count()
    while count and time.monotonic() < deadline:
        time.sleep(0.1)
        count = git_process_count()
    return count


def verify_tree_kill(target: CloneTarget) -> None:
    timed_out = False
    unexpected_success = False
    process_count = 0
    for attempt, timeout in enumerate((0.3, 0.05)):
        run_dir = create_run_dir(TEMP_ROOT, 9901 + attempt)
        try:
            try:
                clone_repository(
                    target,
                    run_dir,
                    max_repo_size_mb=50,
                    max_source_files=1000,
                    deadline=time.monotonic() + timeout,
                )
                unexpected_success = True
            except CloneTimedOutError:
                timed_out = True
                process_count = wait_for_git_processes()
                break
            except Exception as error:
                report(
                    "tree-kill",
                    False,
                    f"error_type={exception_type(error)} attempt={attempt + 1}",
                )
                return
        finally:
            warning = cleanup_run_dir(TEMP_ROOT, run_dir)
            gone = not run_dir.exists() and not run_dir.is_symlink()
            report(
                f"tree-kill-cleanup-{run_dir.name}",
                warning is None and gone,
                f"warning={'none' if warning is None else warning.code} gone={gone}",
            )
    if timed_out:
        report(
            "tree-kill", process_count == 0, f"remaining_git_processes={process_count}"
        )
    elif unexpected_success:
        report("tree-kill", False, "INCONCLUSIVE clone completed on both deadlines")
    else:
        report("tree-kill", False, "INCONCLUSIVE no timeout result")


def prepare_outside() -> tuple[Path, bool]:
    created_directory = False
    try:
        OUTSIDE_ROOT.lstat()
    except FileNotFoundError:
        OUTSIDE_ROOT.mkdir(mode=0o700)
        created_directory = True
    outside_stat = OUTSIDE_ROOT.lstat()
    if not stat.S_ISDIR(outside_stat.st_mode):
        raise RuntimeError("outside target is not a directory")
    marker = OUTSIDE_ROOT / f"marker-{os.getpid()}"
    try:
        with marker.open("xb") as marker_file:
            marker_file.write(b"s3c marker\n")
    except Exception:
        if created_directory:
            OUTSIDE_ROOT.rmdir()
        raise
    return marker, created_directory


def marker_is_intact(marker: Path) -> bool:
    try:
        return marker.read_bytes() == b"s3c marker\n"
    except OSError:
        return False


def verify_symlink_cleanup(marker: Path) -> None:
    run_dir = create_run_dir(TEMP_ROOT, 9701)
    warning = None
    try:
        (run_dir / "directory-link").symlink_to(OUTSIDE_ROOT, target_is_directory=True)
        (run_dir / "file-link").symlink_to(marker)
        warning = cleanup_run_dir(TEMP_ROOT, run_dir)
        passed = (
            warning is None
            and not run_dir.exists()
            and not run_dir.is_symlink()
            and marker_is_intact(marker)
        )
        outside_marker_intact = marker_is_intact(marker)
        report(
            "symlink-safe-cleanup",
            passed,
            f"warning={'none' if warning is None else warning.code} "
            f"run_gone={not run_dir.exists()} "
            f"outside_marker_intact={outside_marker_intact}",
        )
    except Exception as error:
        report("symlink-safe-cleanup", False, f"error_type={exception_type(error)}")
        warning = cleanup_run_dir(TEMP_ROOT, run_dir)
        gone = not run_dir.exists() and not run_dir.is_symlink()
        report(
            "symlink-cleanup-after-error",
            warning is None and gone,
            f"warning={'none' if warning is None else warning.code} gone={gone}",
        )


def expected_read_error(root: Path, relative_path: str, reason: str) -> bool:
    try:
        read_source_file(root, relative_path, SOURCE_FILE_LIMIT_BYTES)
    except SourceReadError as error:
        return error.reason == reason
    return False


def alarm_handler(_signum: int, _frame: object) -> None:
    raise TimeoutError


def read_fifo_with_alarm(root: Path, relative_path: str) -> str:
    previous_handler = signal.signal(signal.SIGALRM, alarm_handler)
    signal.alarm(5)
    try:
        try:
            read_source_file(root, relative_path, SOURCE_FILE_LIMIT_BYTES)
        except SourceReadError as error:
            return error.reason
        return "unexpected_read"
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)


def verify_unsafe_reads(marker: Path) -> None:
    run_dir = create_run_dir(TEMP_ROOT, 9702)
    try:
        repository_dir = run_dir / "repository"
        repository_dir.mkdir()
        local_marker = repository_dir / "hard-source.py"
        local_marker.write_bytes(b"safe\n")
        os.link(local_marker, repository_dir / "hard-link.py")
        (repository_dir / "A.py").write_bytes(b"upper\n")
        (repository_dir / "a.py").write_bytes(b"lower\n")
        fifo_path = repository_dir / "pipe.py"
        os.mkfifo(fifo_path)
        (repository_dir / "outside-link.py").symlink_to(marker)
        symlink_reason = (
            "unsafe_path"
            if expected_read_error(repository_dir, "outside-link.py", "unsafe_path")
            else "unexpected"
        )
        hardlink_reason = (
            "unsafe_path"
            if expected_read_error(repository_dir, "hard-link.py", "unsafe_path")
            else "unexpected"
        )
        fifo_reason = read_fifo_with_alarm(repository_dir, "pipe.py")
        case_distinct = (
            read_source_file(repository_dir, "A.py", SOURCE_FILE_LIMIT_BYTES)
            == b"upper\n"
            and read_source_file(repository_dir, "a.py", SOURCE_FILE_LIMIT_BYTES)
            == b"lower\n"
        )
        passed = (
            symlink_reason == "unsafe_path"
            and hardlink_reason == "unsafe_path"
            and fifo_reason == "not_regular"
            and case_distinct
        )
        report(
            "unsafe-reads",
            passed,
            f"symlink={symlink_reason} hardlink={hardlink_reason} "
            f"fifo={fifo_reason} case_distinct={case_distinct}",
        )
    except Exception as error:
        report("unsafe-reads", False, f"error_type={exception_type(error)}")
    finally:
        warning = cleanup_run_dir(TEMP_ROOT, run_dir)
        gone = not run_dir.exists() and not run_dir.is_symlink()
        report(
            "unsafe-reads-cleanup",
            warning is None and gone,
            f"warning={'none' if warning is None else warning.code} gone={gone}",
        )


def lstat_exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def verify_sweep(marker: Path) -> None:
    candidates = [
        TEMP_ROOT / "run-8001",
        TEMP_ROOT / "run-8002",
        TEMP_ROOT / "run-8003",
        TEMP_ROOT / "run-3",
        TEMP_ROOT / "odd",
    ]
    owned_runs: set[Path] = set()
    owned_paths: set[Path] = set()
    try:
        with os.scandir(TEMP_ROOT) as entries:
            existing_runs = [
                entry.name
                for entry in entries
                if re.fullmatch(r"run-[1-9][0-9]*", entry.name)
            ]
        if existing_runs:
            report(
                "orphan-sweep",
                False,
                f"preexisting_run_entries={len(existing_runs)} skipped=true",
            )
            return
        if any(lstat_exists(path) for path in candidates):
            report("orphan-sweep", False, "fixture_name_collision=true")
            return

        old_run = create_run_dir(TEMP_ROOT, 8001)
        owned_runs.add(old_run)
        (old_run / "read-only.txt").write_bytes(b"readonly\n")
        (old_run / "read-only.txt").chmod(0o400)
        active_run = create_run_dir(TEMP_ROOT, 8003)
        owned_runs.add(active_run)
        symlink_run = TEMP_ROOT / "run-8002"
        symlink_run.symlink_to(OUTSIDE_ROOT, target_is_directory=True)
        owned_paths.add(symlink_run)
        plain_file = TEMP_ROOT / "run-3"
        plain_file.write_bytes(b"not a run directory\n")
        owned_paths.add(plain_file)
        odd_directory = TEMP_ROOT / "odd"
        odd_directory.mkdir()
        owned_paths.add(odd_directory)

        result = sweep_orphaned_runs(TEMP_ROOT, active_run_ids={8003})
        preserved = (
            not lstat_exists(old_run)
            and active_run.is_dir()
            and symlink_run.is_symlink()
            and marker_is_intact(marker)
            and plain_file.is_file()
            and odd_directory.is_dir()
        )
        passed = result.removed_ids == (8001,) and not result.failed_ids and preserved
        if not lstat_exists(old_run):
            owned_runs.discard(old_run)
        report(
            "orphan-sweep",
            passed,
            f"removed_ids={result.removed_ids} failed_ids={result.failed_ids} "
            f"active_kept={active_run.is_dir()} "
            f"symlink_skipped={symlink_run.is_symlink()} "
            f"marker_intact={marker_is_intact(marker)} "
            f"file_untouched={plain_file.is_file()} "
            f"odd_untouched={odd_directory.is_dir()}",
        )
        if cleanup_created_run(active_run):
            owned_runs.discard(active_run)
        try:
            symlink_run.unlink()
            owned_paths.discard(symlink_run)
            plain_file.unlink()
            owned_paths.discard(plain_file)
            odd_directory.rmdir()
            owned_paths.discard(odd_directory)
        except OSError as error:
            report(
                "orphan-sweep-leftovers", False, f"error_type={exception_type(error)}"
            )
        else:
            report("orphan-sweep-leftovers", True, "removed=true")
    except Exception as error:
        report("orphan-sweep", False, f"error_type={exception_type(error)}")
    finally:
        for path in owned_runs:
            try:
                warning = cleanup_run_dir(TEMP_ROOT, path)
                gone = not path.exists() and not path.is_symlink()
                if warning is not None or not gone:
                    report("orphan-sweep-final-cleanup", False, "cleanup_failed=true")
            except OSError:
                report("orphan-sweep-final-cleanup", False, "cleanup_failed=true")
        for path in owned_paths:
            try:
                entry_stat = path.lstat()
                if stat.S_ISLNK(entry_stat.st_mode) or stat.S_ISREG(entry_stat.st_mode):
                    path.unlink()
                elif stat.S_ISDIR(entry_stat.st_mode):
                    path.rmdir()
            except FileNotFoundError:
                pass
            except OSError:
                report("orphan-sweep-final-cleanup", False, "cleanup_failed=true")


def main() -> int:
    marker: Path | None = None
    created_outside_directory = False
    try:
        environment_ready = verify_environment()
        if environment_ready:
            specifications = [
                item.strip()
                for item in os.environ.get("S3C_REPOS", "").split(",")
                if item.strip()
            ]
            if not specifications:
                report("repository-input", False, "S3C_REPOS is empty")
            else:
                report(
                    "repository-input", True, f"repository_count={len(specifications)}"
                )

        targets: list[CloneTarget] = []
        if environment_ready:
            for index, specification in enumerate(specifications):
                run_id = 9001 + index
                try:
                    target, full_name = fetch_target(specification)
                except Exception as error:
                    report(
                        f"repo-{run_id}-metadata",
                        False,
                        f"error_type={exception_type(error)}",
                    )
                    continue
                safe_size = target.size_kb <= MAX_REPOSITORY_SIZE_KB
                report(
                    f"repo-{run_id}-metadata",
                    True,
                    f"id={target.github_repo_id} full_name={full_name} "
                    f"size_kb={target.size_kb} "
                    f"clone_skipped={not safe_size}",
                )
                if not safe_size:
                    continue
                targets.append(target)
                try:
                    verify_repository(target, run_id)
                except Exception as error:
                    report(
                        f"repo-{run_id}-verification",
                        False,
                        f"error_type={exception_type(error)}",
                    )

            if targets:
                try:
                    verify_tree_kill(targets[0])
                except Exception as error:
                    report(
                        "tree-kill",
                        False,
                        f"error_type={exception_type(error)}",
                    )
            else:
                report("tree-kill", False, "no_valid_public_repository=true")

            try:
                marker, created_outside_directory = prepare_outside()
                verify_symlink_cleanup(marker)
                verify_unsafe_reads(marker)
                verify_sweep(marker)
            except Exception as error:
                report(
                    "filesystem-safety-checks",
                    False,
                    f"error_type={exception_type(error)}",
                )
    finally:
        if marker is not None:
            try:
                marker.unlink()
                report("outside-marker-cleanup", True, "removed=true")
            except FileNotFoundError:
                report("outside-marker-cleanup", True, "already_missing=true")
            except OSError:
                report("outside-marker-cleanup", False, "cleanup_failed=true")
        if created_outside_directory:
            try:
                OUTSIDE_ROOT.rmdir()
                report("outside-directory-cleanup", True, "removed=true")
            except OSError:
                report("outside-directory-cleanup", False, "cleanup_failed=true")
        report("summary", not _failed, f"checks={_checks} failures={int(_failed)}")
    return 1 if _failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
