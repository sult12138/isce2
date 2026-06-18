#!/usr/bin/env python3
"""Download DEM tiles for the bounding box covered by Sentinel-1 SLC zips."""

from __future__ import annotations

import argparse
import math
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


DEFAULT_DEM_URL = "https://step.esa.int/auxdata/dem/SRTMGL1/"


def iter_slc_zips(slc_dir: Path) -> list[Path]:
    zips = sorted(slc_dir.glob("*.zip"))
    if not zips:
        raise FileNotFoundError(f"No .zip files found in {slc_dir}")
    return zips


def find_manifest_name(zip_file: zipfile.ZipFile) -> str:
    for name in zip_file.namelist():
        if name.endswith("/manifest.safe") or name == "manifest.safe":
            return name
    raise FileNotFoundError("manifest.safe was not found in the zip")


def parse_footprint_coordinates(manifest_xml: bytes) -> list[tuple[float, float]]:
    root = ET.fromstring(manifest_xml)

    for elem in root.iter():
        tag = elem.tag.rsplit("}", 1)[-1]
        if tag == "coordinates" and elem.text:
            coords = []
            for pair in elem.text.split():
                lat_text, lon_text = pair.split(",", maxsplit=1)
                coords.append((float(lat_text), float(lon_text)))
            if coords:
                return coords

        if tag == "posList" and elem.text:
            values = [float(value) for value in elem.text.split()]
            if len(values) >= 4 and len(values) % 2 == 0:
                return list(zip(values[0::2], values[1::2]))

    raise ValueError("No footprint coordinates found in manifest.safe")


def read_slc_bbox(slc_zip: Path) -> tuple[float, float, float, float]:
    with zipfile.ZipFile(slc_zip) as zip_file:
        manifest_name = find_manifest_name(zip_file)
        coords = parse_footprint_coordinates(zip_file.read(manifest_name))

    lats = [lat for lat, _lon in coords]
    lons = [lon for _lat, lon in coords]
    return min(lats), max(lats), min(lons), max(lons)


def merged_bbox(slc_zips: list[Path]) -> tuple[float, float, float, float]:
    boxes = [read_slc_bbox(slc_zip) for slc_zip in slc_zips]
    return (
        min(box[0] for box in boxes),
        max(box[1] for box in boxes),
        min(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def rounded_dem_bbox(
    bbox: tuple[float, float, float, float],
    padding_degrees: int,
) -> tuple[int, int, int, int]:
    min_lat, max_lat, min_lon, max_lon = bbox
    return (
        math.floor(min_lat) - padding_degrees,
        math.ceil(max_lat) + padding_degrees,
        math.floor(min_lon) - padding_degrees,
        math.ceil(max_lon) + padding_degrees,
    )


def build_dem_command(args: argparse.Namespace, bbox: tuple[int, int, int, int]) -> list[str]:
    min_lat, max_lat, min_lon, max_lon = bbox
    cmd = [
        args.dem_py,
        "-a",
        "stitch",
        "-b",
        str(min_lat),
        str(max_lat),
        str(min_lon),
        str(max_lon),
        "-r",
        "-s",
        "1",
        "-c",
        "-f",
        "-d",
        str(args.dem_dir),
        "-u",
        args.dem_url,
    ]
    if args.python:
        cmd.insert(0, args.python)
    return cmd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read Sentinel-1 SLC zip footprints and download the matching DEM with dem.py.",
    )
    parser.add_argument("--slc-dir", type=Path, default=Path("SLC"))
    parser.add_argument("--dem-dir", type=Path, default=Path("DEM"))
    parser.add_argument("--dem-url", default=DEFAULT_DEM_URL)
    parser.add_argument("--dem-py", default="dem.py")
    parser.add_argument("--python", help="Python interpreter used to run dem.py.")
    parser.add_argument("--padding-degrees", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true", help="Print the dem.py command without running it.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.slc_dir = args.slc_dir.resolve()
    args.dem_dir = args.dem_dir.resolve()
    args.dem_dir.mkdir(parents=True, exist_ok=True)

    slc_zips = iter_slc_zips(args.slc_dir)
    bbox = merged_bbox(slc_zips)
    dem_bbox = rounded_dem_bbox(bbox, args.padding_degrees)
    cmd = build_dem_command(args, dem_bbox)

    print(f"SLC files: {len(slc_zips)}")
    print(
        "SLC bbox: "
        f"min_lat={bbox[0]:.6f}, max_lat={bbox[1]:.6f}, "
        f"min_lon={bbox[2]:.6f}, max_lon={bbox[3]:.6f}",
    )
    print(f"dem.py bbox S N W E: {dem_bbox[0]} {dem_bbox[1]} {dem_bbox[2]} {dem_bbox[3]}")
    print("Command:")
    print(" ".join(cmd))

    if args.dry_run:
        return 0

    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError:
        print(f"Could not find {args.dem_py}. Pass it with --dem-py /path/to/dem.py.", file=sys.stderr)
        return 127
    except subprocess.CalledProcessError as exc:
        return exc.returncode

    return 0


if __name__ == "__main__":
    sys.exit(main())
