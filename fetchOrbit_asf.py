#!/usr/bin/env python3
"""Fetch Sentinel-1 orbit EOF files from ASF s1qc for one SLC package."""

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


ASF_URLS = {
    "precise": "https://s1qc.asf.alaska.edu/aux_poeorb/",
    "restituted": "https://s1qc.asf.alaska.edu/aux_resorb/",
}
ORBIT_TYPES = {
    "precise": "AUX_POEORB",
    "restituted": "AUX_RESORB",
}
DATEFMT = "%Y%m%dT%H%M%S"
DEFAULT_COOKIE_JAR = Path.home() / ".bulk_download_cookiejar.txt"
SLC_TIME_RE = re.compile(
    r"^(S1[A-Z])_.*?_(\d{8}T\d{6})_(\d{8}T\d{6})_.*(?:\.zip|\.SAFE)?$",
)


@dataclass(frozen=True)
class SlcTime:
    mission: str
    start: datetime
    stop: datetime


@dataclass(frozen=True)
class Orbit:
    name: str
    mission: str
    start: datetime
    stop: datetime


def parse_slc_time(path: Path) -> SlcTime:
    match = SLC_TIME_RE.match(path.name)
    if not match:
        raise ValueError(f"Could not parse Sentinel-1 SLC name: {path.name}")
    mission, start, stop = match.groups()
    return SlcTime(mission, datetime.strptime(start, DATEFMT), datetime.strptime(stop, DATEFMT))


def orbit_regex(orbit_type: str) -> re.Pattern[str]:
    marker = ORBIT_TYPES[orbit_type]
    return re.compile(
        r'href="(?P<name>(?P<mission>S1[A-Z])_OPER_'
        + marker
        + r'_[^"]+_V(?P<start>\d{8}T\d{6})_(?P<stop>\d{8}T\d{6})\.EOF)"',
    )


def fetch_index(url: str, orbit_type: str) -> list[Orbit]:
    with urlopen(url) as response:
        html = response.read().decode("utf-8", errors="replace")

    orbits = []
    for match in orbit_regex(orbit_type).finditer(html):
        orbits.append(
            Orbit(
                name=match.group("name"),
                mission=match.group("mission"),
                start=datetime.strptime(match.group("start"), DATEFMT),
                stop=datetime.strptime(match.group("stop"), DATEFMT),
            ),
        )
    return orbits


def find_covering_orbit(slc: SlcTime, orbit_type: str) -> tuple[str, Orbit] | None:
    base_url = ASF_URLS[orbit_type]
    candidates = [
        orbit
        for orbit in fetch_index(base_url, orbit_type)
        if orbit.mission == slc.mission and orbit.start <= slc.start and orbit.stop >= slc.stop
    ]
    if not candidates:
        return None

    orbit = sorted(candidates, key=lambda item: (item.stop - item.start, item.name))[-1]
    return base_url, orbit


def download_with_curl(url: str, out_path: Path, cookie_jar: Path | None) -> None:
    if out_path.exists() and out_path.stat().st_size > 0:
        print(f"exists: {out_path}")
        return

    tmp_path = out_path.with_suffix(out_path.suffix + ".part")
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
    print("download:", url)
    subprocess.run(cmd, check=True)
    tmp_path.replace(out_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download a Sentinel-1 orbit EOF from ASF s1qc for one SLC zip/SAFE.",
    )
    parser.add_argument("-i", "--input", required=True, type=Path)
    parser.add_argument("-o", "--output", default=Path("."), type=Path)
    parser.add_argument("--prefer", choices=("precise", "restituted"), default="precise")
    parser.add_argument("--cookie-jar", type=Path, default=DEFAULT_COOKIE_JAR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    slc = parse_slc_time(args.input)
    order = [args.prefer, "restituted" if args.prefer == "precise" else "precise"]
    match = None
    for orbit_type in order:
        match = find_covering_orbit(slc, orbit_type)
        if match is not None:
            break

    if match is None:
        print(f"No ASF orbit found for {args.input.name}", file=sys.stderr)
        return 1

    base_url, orbit = match
    out_path = args.output / orbit.name
    print(f"{args.input.name} -> {orbit.name}")
    download_with_curl(urljoin(base_url, orbit.name), out_path, args.cookie_jar)
    return 0


if __name__ == "__main__":
    sys.exit(main())
