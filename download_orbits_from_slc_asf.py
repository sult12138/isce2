#!/usr/bin/env python3
"""Download Sentinel-1 precise orbit files from ASF for local SLC zips."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import urlopen


ASF_POEORB_URL = "https://s1qc.asf.alaska.edu/aux_poeorb/"
DEFAULT_COOKIE_JAR = Path.home() / ".bulk_download_cookiejar.txt"
SLC_TIME_RE = re.compile(
    r"^(S1[A-Z])_.*?_(\d{8}T\d{6})_(\d{8}T\d{6})_.*\.zip$",
)
ORBIT_RE = re.compile(
    r'href="(?P<name>(?P<mission>S1[A-Z])_OPER_AUX_POEORB_[^"]+_'
    r"V(?P<start>\d{8}T\d{6})_(?P<stop>\d{8}T\d{6})\.EOF)",
)
DATEFMT = "%Y%m%dT%H%M%S"


@dataclass(frozen=True)
class Slc:
    path: Path
    mission: str
    start: datetime
    stop: datetime


@dataclass(frozen=True)
class Orbit:
    name: str
    mission: str
    start: datetime
    stop: datetime


def parse_slc_name(path: Path) -> Slc:
    match = SLC_TIME_RE.match(path.name)
    if not match:
        raise ValueError(f"Could not parse Sentinel-1 SLC name: {path.name}")
    mission, start, stop = match.groups()
    return Slc(path, mission, datetime.strptime(start, DATEFMT), datetime.strptime(stop, DATEFMT))


def read_slcs(slc_dir: Path) -> list[Slc]:
    slcs = [parse_slc_name(path) for path in sorted(slc_dir.glob("*.zip"))]
    if not slcs:
        raise FileNotFoundError(f"No .zip files found in {slc_dir}")
    return slcs


def fetch_orbit_index(url: str) -> list[Orbit]:
    with urlopen(url) as response:
        html = response.read().decode("utf-8", errors="replace")

    orbits = []
    for match in ORBIT_RE.finditer(html):
        orbits.append(
            Orbit(
                name=match.group("name"),
                mission=match.group("mission"),
                start=datetime.strptime(match.group("start"), DATEFMT),
                stop=datetime.strptime(match.group("stop"), DATEFMT),
            ),
        )
    if not orbits:
        raise RuntimeError(f"No AUX_POEORB files found at {url}")
    return orbits


def match_orbit(slc: Slc, orbits: list[Orbit]) -> Orbit:
    candidates = [
        orbit
        for orbit in orbits
        if orbit.mission == slc.mission and orbit.start <= slc.start and orbit.stop >= slc.stop
    ]
    if not candidates:
        raise RuntimeError(f"No orbit file covers {slc.path.name}")

    # Prefer the shortest covering interval, then the latest generation in duplicate cases.
    return sorted(candidates, key=lambda orbit: (orbit.stop - orbit.start, orbit.name))[-1]


def download_orbit(orbit: Orbit, base_url: str, out_dir: Path, cookie_jar: Path | None) -> Path:
    out_path = out_dir / orbit.name
    if out_path.exists() and out_path.stat().st_size > 0:
        print(f"exists: {out_path}")
        return out_path

    url = urljoin(base_url, orbit.name)
    tmp_path = out_path.with_suffix(out_path.suffix + ".part")
    print(f"download: {url}")
    cmd = [
        "curl",
        "-L",
        "-f",
        "--retry",
        "3",
        "--connect-timeout",
        "30",
        "--max-time",
        "180",
        "-o",
        str(tmp_path),
        url,
    ]
    if cookie_jar and cookie_jar.exists():
        cmd[1:1] = ["-b", str(cookie_jar), "-c", str(cookie_jar)]
    else:
        cmd[1:1] = ["-n"]
    subprocess.run(cmd, check=True)
    tmp_path.replace(out_path)
    return out_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download ASF Sentinel-1 AUX_POEORB files covering SLC zip acquisition times.",
    )
    parser.add_argument("--slc-dir", type=Path, default=Path("SLC"))
    parser.add_argument("--orbit-dir", type=Path, default=Path("ORBITS"))
    parser.add_argument("--url", default=ASF_POEORB_URL)
    parser.add_argument("--cookie-jar", type=Path, default=DEFAULT_COOKIE_JAR)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.slc_dir = args.slc_dir.resolve()
    args.orbit_dir = args.orbit_dir.resolve()
    args.orbit_dir.mkdir(parents=True, exist_ok=True)

    slcs = read_slcs(args.slc_dir)
    print(f"SLC files: {len(slcs)}")
    print(f"Orbit index: {args.url}")
    orbits = fetch_orbit_index(args.url)

    matches = [(slc, match_orbit(slc, orbits)) for slc in slcs]
    unique_orbits = list(dict.fromkeys(orbit for _slc, orbit in matches))
    print(f"Matched orbit files: {len(unique_orbits)}")

    for slc, orbit in matches:
        print(f"{slc.path.name} -> {orbit.name}")

    if args.dry_run:
        return 0

    for orbit in unique_orbits:
        download_orbit(orbit, args.url, args.orbit_dir, args.cookie_jar)

    return 0


if __name__ == "__main__":
    sys.exit(main())
