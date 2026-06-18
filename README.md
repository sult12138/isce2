# SAR Project Helper Scripts

This repository contains helper scripts for preparing and running a Sentinel-1
ISCE2/topsStack workflow.

Large SAR data products are intentionally not tracked by Git. The local data
directories are ignored by `.gitignore`.

## Directory Layout

```text
SLC/      Sentinel-1 SLC zip files
DEM/      downloaded and stitched DEM files
ORBITS/   Sentinel-1 orbit EOF files
AUX/      ISCE auxiliary directory
WORK/     ISCE topsStack working directory and outputs
```

## 1. Download SLC Files

The ASF bulk download script is included:

```bash
python download-all-2026-06-17_08-48-14.py
```

The downloaded Sentinel-1 zip files should be placed under:

```text
SLC/
```

## 2. Download DEM From SLC Footprints

The DEM helper reads `manifest.safe` from the SLC zip files, computes the full
bounding box, and runs ISCE `dem.py`.

Preview the computed DEM command:

```bash
python download_dem_from_slc.py --dry-run \
  --python /home/haku/miniforge3/envs/isce2_env/bin/python \
  --dem-py /home/haku/isce_install/isce/applications/dem.py
```

Run the DEM download and stitch step:

```bash
env LD_LIBRARY_PATH=/home/haku/miniforge3/envs/isce2_env/lib \
/home/haku/miniforge3/envs/isce2_env/bin/python download_dem_from_slc.py \
  --python /home/haku/miniforge3/envs/isce2_env/bin/python \
  --dem-py /home/haku/isce_install/isce/applications/dem.py
```

Expected DEM output:

```text
DEM/demLat_N35_N38_Lon_E136_E140.dem
DEM/demLat_N35_N38_Lon_E136_E140.dem.wgs84
DEM/demLat_N35_N38_Lon_E136_E140.dem.vrt
DEM/demLat_N35_N38_Lon_E136_E140.dem.wgs84.vrt
```

## 3. Download Orbit EOF Files

Download all matching Sentinel-1 precise orbit files from ASF s1qc:

```bash
python download_orbits_from_slc_asf.py
```

Preview the matched orbit files without downloading:

```bash
python download_orbits_from_slc_asf.py --dry-run
```

Download the orbit for a single SLC:

```bash
python fetchOrbit_asf.py \
  -i SLC/S1A_IW_SLC__1SDV_20240130T205150_20240130T205218_052341_06543B_E88F.zip \
  -o ORBITS \
  --prefer precise
```

Notes:

- Orbit files are downloaded from `https://s1qc.asf.alaska.edu/aux_poeorb/`.
- The EOF download requires an Earthdata/ASF authentication cookie.
- By default, the scripts use `/home/haku/.bulk_download_cookiejar.txt` if it
  exists.
- If the cookie expires, refresh it by logging in again with the ASF download
  workflow.

Verify the orbit files:

```bash
find ORBITS -maxdepth 1 -type f -name '*.EOF' | wc -l
ls -lh ORBITS
```

## 4. Create ISCE topsStack Run Files

Once `SLC/`, `DEM/`, and `ORBITS/` are ready, create the ISCE topsStack
configuration and run files.

```bash
env LD_LIBRARY_PATH=/home/haku/miniforge3/envs/isce2_env/lib \
/home/haku/miniforge3/envs/isce2_env/bin/python \
/home/haku/isce2/contrib/stack/topsStack/stackSentinel.py \
  -s SLC \
  -o ORBITS \
  -a AUX \
  -w WORK \
  -d DEM/demLat_N35_N38_Lon_E136_E140.dem.wgs84 \
  -p vv \
  -W interferogram \
  -C NESD \
  -m 20240505 \
  -c 1 \
  -z 3 \
  -r 9 \
  --num_proc 1 \
  --num_proc4topo 1
```

Check the generated run files:

```bash
ls WORK/run_files
```

## 5. Run ISCE Run Files With Logs

Run every `WORK/run_files/run_*` file in numeric order:

```bash
python run_work_run_files.py
```

Preview the commands without executing them:

```bash
python run_work_run_files.py --dry-run
```

Resume after a failed or interrupted run:

```bash
python run_work_run_files.py --resume
```

Run only part of the workflow:

```bash
python run_work_run_files.py \
  --start run_01_unpack_topo_reference \
  --stop run_03_average_baseline
```

Logs are written under:

```text
WORK/run_logs/run_all.log
WORK/run_logs/run_status.json
WORK/run_logs/run_01_unpack_topo_reference.log
WORK/run_logs/run_02_unpack_secondary_slc.log
...
```

The runner stops immediately if any command fails.

## Git Notes

The following directories are ignored because they contain large data or
generated products:

```text
SLC/
DEM/
ORBITS/
AUX/
WORK/
```

Only scripts, notes, and lightweight metadata should be committed to Git.
