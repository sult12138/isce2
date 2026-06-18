# SAR Project Notes

## DEM download from SLC bbox

SLC zip内の`manifest.safe`からフットプリントを読み、DEM用bboxを自動計算する。

```bash
python download_dem_from_slc.py --dry-run \
  --python /home/haku/miniforge3/envs/isce2_env/bin/python \
  --dem-py /home/haku/isce_install/isce/applications/dem.py
```

今回のSLC 16個から読んだ範囲:

```text
SLC bbox:
  min_lat=35.065098
  max_lat=37.139133
  min_lon=136.209747
  max_lon=139.343201

dem.py bbox S N W E:
  35 38 136 140
```

DEMを実際にダウンロード・作成するコマンド:

```bash
env LD_LIBRARY_PATH=/home/haku/miniforge3/envs/isce2_env/lib \
/home/haku/miniforge3/envs/isce2_env/bin/python download_dem_from_slc.py \
  --python /home/haku/miniforge3/envs/isce2_env/bin/python \
  --dem-py /home/haku/isce_install/isce/applications/dem.py
```

出力先:

```text
DEM/demLat_N35_N38_Lon_E136_E140.dem
DEM/demLat_N35_N38_Lon_E136_E140.dem.vrt
DEM/demLat_N35_N38_Lon_E136_E140.dem.xml
DEM/demLat_N35_N38_Lon_E136_E140.dem.wgs84
DEM/demLat_N35_N38_Lon_E136_E140.dem.wgs84.vrt
DEM/demLat_N35_N38_Lon_E136_E140.dem.wgs84.xml
```

メモ:

- `SLC/*.zip`を展開する必要はない。スクリプトがzip内の`manifest.safe`だけ読む。
- `dem.py`は`libgdal.so.35`が必要なので、`LD_LIBRARY_PATH=/home/haku/miniforge3/envs/isce2_env/lib`を付ける。
- 通常の`python`だと`numpy`不足で止まることがあるため、`isce2_env`のPythonを使う。
- ネットワークが必要。サンドボックス内で`Could not resolve host: step.esa.int`が出たら、ネットワーク許可つきで再実行する。
- 生成済み確認:

```bash
ls -lh DEM
```

## Orbit EOF download from SLC

SLC zip名から取得日時を読み、ASF s1qcのSentinel-1 orbit EOFを探して`ORBITS/`へ保存する。

単体SLC用:

```bash
python fetchOrbit_asf.py \
  -i SLC/S1A_IW_SLC__1SDV_20240130T205150_20240130T205218_052341_06543B_E88F.zip \
  -o ORBITS \
  --prefer precise
```

全SLC一括:

```bash
python download_orbits_from_slc_asf.py
```

対応確認のみ:

```bash
python download_orbits_from_slc_asf.py --dry-run
```

出力先:

```text
ORBITS/*.EOF
```

今回の結果:

```text
SLC files: 16
Matched orbit files: 16
Orbit type: AUX_POEORB precise
Output: ORBITS/ に 16 EOF files
```

メモ:

- ASF s1qc URL: `https://s1qc.asf.alaska.edu/aux_poeorb/`
- EOF本体の取得にはEarthdata/ASF認証cookieが必要。
- この環境では`/home/haku/.bulk_download_cookiejar.txt`を使うとダウンロードできた。
- `fetchOrbit_asf.py`と`download_orbits_from_slc_asf.py`は、デフォルトで上記cookie jarが存在すれば使う。
- cookieが切れて401やredirect loopになる場合は、ASF SLC downloaderを再ログインしてcookie jarを更新する。

生成済み確認:

```bash
find ORBITS -maxdepth 1 -type f -name '*.EOF' | wc -l
ls -lh ORBITS
```

## Next step: create ISCE topsStack run files

SLC、DEM、Orbit EOFが揃った後の次工程。

現在の入力:

```text
SLC/     16 Sentinel-1 SLC zip files
ORBITS/  16 AUX_POEORB EOF files
DEM/     demLat_N35_N38_Lon_E136_E140.dem.wgs84
AUX/     empty ok
WORK/    output working directory
```

まず`stackSentinel.py`で`WORK/`内に処理ディレクトリとrun filesを作る。

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

設定の意味:

- `-p vv`: VV偏波を使用。
- `-W interferogram`: interferogram workflow。
- `-C NESD`: TOPS stackの標準的なNESD coregistration。
- `-m 20240505`: 基準日。16枚の中央付近なのでまずは無難。
- `-c 1`: 隣接ペア中心の干渉ペアを作る。
- `-z 3 -r 9`: azimuth 3 looks、range 9 looks。
- `--num_proc 1 --num_proc4topo 1`: まずは安全に1並列。

作成後の確認:

```bash
ls WORK/run_files
```

`WORK/run_files`ができたら、次はrun fileを番号順に実行する。

## Run ISCE run files automatically with logs

`WORK/run_files`内の`run_*`を番号順に実行するスクリプト:

```bash
python run_work_run_files.py
```

ログ出力先:

```text
WORK/run_logs/run_all.log
WORK/run_logs/run_status.json
WORK/run_logs/run_01_unpack_topo_reference.log
WORK/run_logs/run_02_unpack_secondary_slc.log
...
```

事前確認のみ:

```bash
python run_work_run_files.py --dry-run
```

途中で失敗した場合:

```bash
python run_work_run_files.py --resume
```

特定範囲だけ実行する例:

```bash
python run_work_run_files.py \
  --start run_01_unpack_topo_reference \
  --stop run_03_average_baseline
```

メモ:

- 実行順は`ls WORK/run_files`で見える`run_01`、`run_02`...の番号順。
- 各run file内の複数コマンドも上から順番に実行する。
- 1つでも失敗したらそこで停止する。
- `PATH`、`PYTHONPATH`、`LD_LIBRARY_PATH`はスクリプト内でISCE用に追加している。
