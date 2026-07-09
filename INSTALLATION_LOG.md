# ISCE2 Installation Log

Installation date: 2026-07-09

Platform: Windows with WSL 2

Linux distribution: Ubuntu 24.04 LTS

Linux user: `haku`

## Initial state

- Windows did not initially have Git installed.
- No WSL Linux distribution was registered.
- Therefore, no old Linux ISCE2, Conda, or `/home/haku` installation remained
  to delete.
- The repository contains SAR workflow helpers and notes; it is not the
  official ISCE2 source repository.

## Installed components

- Git for Windows 2.55.0.2
- Ubuntu 24.04 LTS under WSL
- Build tools: GCC/G++, GFortran, CMake, Make, and OpenMotif headers
- Miniforge at `/home/haku/miniforge3`
- Conda environment at `/home/haku/miniforge3/envs/isce2_env`
- Python 3.11
- ISCE2 2.6.5 from conda-forge
- Official ISCE2 source at `/home/haku/isce2`
- This helper repository at `/home/haku/sar_project`

## Compatibility paths

The existing scripts and README use paths from the previously successful
installation. The following links preserve those paths:

```text
/home/haku/isce_install/isce
  -> /home/haku/miniforge3/envs/isce2_env/lib/python3.11/site-packages/isce

/home/haku/miniforge3/envs/isce2_env/lib/python3.11/site-packages/topsStack
  -> /home/haku/miniforge3/envs/isce2_env/share/isce2/topsStack
```

The `isce2_env` environment is activated automatically from
`/home/haku/.bashrc`.

## Problems encountered and resolutions

1. SSH cloning initially failed with `Host key verification failed`.
   HTTPS was used to clone this repository.
2. ISCE2 cannot be used as a native Windows Python package for this workflow.
   A clean Ubuntu WSL environment was installed.
3. The conda-forge package does not place `topsApp.py` or `dem.py` directly in
   the environment's `bin` directory. They are available under
   `site-packages/isce/applications`.
4. Running the official source copy of `stackSentinel.py` initially produced
   `ModuleNotFoundError: No module named 'topsStack'`. The compatibility link
   shown above fixed the module search path.

## Verification results

Python import:

```text
Using default ISCE Path:
/home/haku/miniforge3/envs/isce2_env/lib/python3.11/site-packages/isce
```

`topsApp.py --help --steps` reported:

```text
ISCE VERSION = 2.6.5
The currently supported sensors are: ['SENTINEL1']
```

`stackSentinel.py --help` completed successfully and displayed the expected
TOPS stack command-line arguments.

## Reproduction

Open an elevated PowerShell in the repository directory and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install_isce2_wsl.ps1
```

After installation:

```powershell
wsl -d Ubuntu-24.04
```

Then inside Ubuntu:

```bash
cd ~/sar_project
python -c "import isce; print(isce.__file__)"
python ~/isce2/contrib/stack/topsStack/stackSentinel.py --help
```
