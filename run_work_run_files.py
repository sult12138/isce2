#!/usr/bin/env python3
"""Run ISCE topsStack run files in order and keep per-step logs."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_RUN_DIR = PROJECT_DIR / "WORK" / "run_files"
DEFAULT_LOG_DIR = PROJECT_DIR / "WORK" / "run_logs"
ISCE2_DIR = Path("/home/haku/isce2")
ISCE2_ENV = Path("/home/haku/miniforge3/envs/isce2_env")


def timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def run_file_sort_key(path: Path) -> tuple[int, str]:
    name = path.name
    if name.startswith("run_"):
        parts = name.split("_", maxsplit=2)
        if len(parts) >= 2 and parts[1].isdigit():
            return int(parts[1]), name
    return 9999, name


def discover_run_files(run_dir: Path) -> list[Path]:
    if not run_dir.exists():
        raise FileNotFoundError(f"run directory not found: {run_dir}")
    run_files = sorted(
        [path for path in run_dir.iterdir() if path.is_file() and path.name.startswith("run_")],
        key=run_file_sort_key,
    )
    if not run_files:
        raise FileNotFoundError(f"no run_* files found in: {run_dir}")
    return run_files


def build_env() -> dict[str, str]:
    env = os.environ.copy()
    path_parts = [
        str(ISCE2_ENV / "bin"),
        str(ISCE2_DIR / "contrib" / "stack" / "topsStack"),
        str(ISCE2_DIR / "applications"),
        env.get("PATH", ""),
    ]
    pythonpath_parts = [
        str(ISCE2_DIR / "components"),
        str(ISCE2_DIR / "contrib" / "stack" / "topsStack"),
        env.get("PYTHONPATH", ""),
    ]
    ld_parts = [
        str(ISCE2_ENV / "lib"),
        env.get("LD_LIBRARY_PATH", ""),
    ]
    env["PATH"] = ":".join(part for part in path_parts if part)
    env["PYTHONPATH"] = ":".join(part for part in pythonpath_parts if part)
    env["LD_LIBRARY_PATH"] = ":".join(part for part in ld_parts if part)
    return env


def read_commands(run_file: Path) -> list[str]:
    commands = []
    for line in run_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            commands.append(stripped)
    return commands


def load_status(status_file: Path) -> dict[str, object]:
    if not status_file.exists():
        return {"completed": []}
    return json.loads(status_file.read_text(encoding="utf-8"))


def save_status(status_file: Path, status: dict[str, object]) -> None:
    status_file.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_master(master_log: Path, message: str) -> None:
    line = f"[{timestamp()}] {message}"
    print(line, flush=True)
    with master_log.open("a", encoding="utf-8") as log:
        log.write(line + "\n")


def run_command(command: str, log_file: Path, env: dict[str, str], cwd: Path) -> int:
    with log_file.open("a", encoding="utf-8") as log:
        log.write(f"\n[{timestamp()}] $ {command}\n")
        log.flush()
        proc = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=env,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            print(line, end="", flush=True)
            log.write(line)
            log.flush()
        return proc.wait()


def run_one_file(
    run_file: Path,
    args: argparse.Namespace,
    env: dict[str, str],
    master_log: Path,
) -> bool:
    commands = read_commands(run_file)
    log_file = args.log_dir / f"{run_file.name}.log"
    append_master(master_log, f"START {run_file.name} ({len(commands)} commands)")

    if args.dry_run:
        for command in commands:
            append_master(master_log, f"DRY-RUN {run_file.name}: {command}")
        append_master(master_log, f"DONE {run_file.name} (dry-run)")
        return True

    for index, command in enumerate(commands, start=1):
        append_master(master_log, f"{run_file.name} [{index}/{len(commands)}]")
        code = run_command(command, log_file, env, PROJECT_DIR)
        if code != 0:
            append_master(master_log, f"FAILED {run_file.name} command {index} exit={code}")
            append_master(master_log, f"See log: {log_file}")
            return False

    append_master(master_log, f"DONE {run_file.name}")
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run all files listed by ls WORK/run_files and write logs.",
    )
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    parser.add_argument("--start", help="First run file name to execute, e.g. run_04_extract_burst_overlaps.")
    parser.add_argument("--stop", help="Last run file name to execute, e.g. run_08_timeseries_misreg.")
    parser.add_argument("--resume", action="store_true", help="Skip run files already marked completed.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would run without executing commands.")
    return parser.parse_args()


def select_range(run_files: list[Path], start: str | None, stop: str | None) -> list[Path]:
    selected = run_files
    if start:
        selected = selected[[path.name for path in selected].index(start) :]
    if stop:
        names = [path.name for path in selected]
        selected = selected[: names.index(stop) + 1]
    return selected


def main() -> int:
    args = parse_args()
    args.run_dir = args.run_dir.resolve()
    args.log_dir = args.log_dir.resolve()
    args.log_dir.mkdir(parents=True, exist_ok=True)

    run_files = discover_run_files(args.run_dir)
    try:
        run_files = select_range(run_files, args.start, args.stop)
    except ValueError as exc:
        print(f"Invalid --start/--stop name: {exc}", file=sys.stderr)
        return 2

    status_file = args.log_dir / "run_status.json"
    master_log = args.log_dir / "run_all.log"
    status = load_status(status_file)
    completed = set(status.get("completed", []))
    env = build_env()

    append_master(master_log, f"Run directory: {args.run_dir}")
    append_master(master_log, f"Log directory: {args.log_dir}")
    append_master(master_log, f"Run files selected: {len(run_files)}")

    for run_file in run_files:
        if args.resume and run_file.name in completed:
            append_master(master_log, f"SKIP completed {run_file.name}")
            continue

        ok = run_one_file(run_file, args, env, master_log)
        if not ok:
            status["last_failed"] = run_file.name
            status["updated_at"] = timestamp()
            save_status(status_file, status)
            return 1

        if not args.dry_run:
            completed.add(run_file.name)
            status["completed"] = sorted(completed, key=lambda name: run_file_sort_key(Path(name)))
            status["last_completed"] = run_file.name
            status["updated_at"] = timestamp()
            save_status(status_file, status)

    append_master(master_log, "ALL DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
