param(
    [string]$Distro = "Ubuntu-24.04",
    [string]$LinuxUser = "haku",
    [string]$ProjectRepo = "https://github.com/sult12138/isce2.git"
)

$ErrorActionPreference = "Stop"

function Invoke-WslRoot {
    param([Parameter(Mandatory)][string]$Command)
    & wsl.exe -d $Distro -u root -- bash -lc $Command
    if ($LASTEXITCODE -ne 0) {
        throw "WSL root command failed with exit code $LASTEXITCODE"
    }
}

function Invoke-WslUser {
    param([Parameter(Mandatory)][string]$Command)
    & wsl.exe -d $Distro -u $LinuxUser -- bash -lc $Command
    if ($LASTEXITCODE -ne 0) {
        throw "WSL user command failed with exit code $LASTEXITCODE"
    }
}

Write-Host "Installing $Distro if it is not already present..."
$installed = (& wsl.exe --list --quiet) -replace "`0", ""
if ($installed -notcontains $Distro) {
    & wsl.exe --install $Distro --no-launch
    if ($LASTEXITCODE -ne 0) {
        throw "WSL distribution installation failed."
    }
}

Write-Host "Creating Linux user $LinuxUser..."
Invoke-WslRoot @"
id '$LinuxUser' >/dev/null 2>&1 || useradd -m -s /bin/bash '$LinuxUser'
printf '[user]\ndefault=$LinuxUser\n' > /etc/wsl.conf
chown -R '${LinuxUser}:${LinuxUser}' '/home/$LinuxUser'
"@

& wsl.exe --terminate $Distro

Write-Host "Installing Ubuntu build dependencies..."
Invoke-WslRoot @"
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  git wget ca-certificates build-essential gfortran cmake libmotif-dev
"@

Write-Host "Installing Miniforge..."
Invoke-WslUser @"
set -e
if [ ! -x '/home/$LinuxUser/miniforge3/bin/conda' ]; then
  wget -q -O /tmp/Miniforge3.sh \
    https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
  bash /tmp/Miniforge3.sh -b -p '/home/$LinuxUser/miniforge3'
fi
'/home/$LinuxUser/miniforge3/bin/conda' config --set auto_activate_base false
"@

Write-Host "Downloading the official ISCE2 source..."
Invoke-WslUser @"
set -e
if [ ! -d '/home/$LinuxUser/isce2/.git' ]; then
  git clone https://github.com/isce-framework/isce2.git '/home/$LinuxUser/isce2'
fi
"@

Write-Host "Creating the ISCE2 conda environment..."
Invoke-WslUser @"
set -e
'/home/$LinuxUser/miniforge3/bin/mamba' create -y \
  -n isce2_env -c conda-forge python=3.11 isce2
"@

Write-Host "Adding compatibility paths used by this project..."
Invoke-WslUser @"
set -e
env_root='/home/$LinuxUser/miniforge3/envs/isce2_env'
site_root=`$env_root/lib/python3.11/site-packages
mkdir -p '/home/$LinuxUser/isce_install'
ln -sfn "`$site_root/isce" '/home/$LinuxUser/isce_install/isce'
ln -sfn "`$env_root/share/isce2/topsStack" "`$site_root/topsStack"
grep -Fq 'conda activate isce2_env' '/home/$LinuxUser/.bashrc' || {
  printf '\nsource /home/$LinuxUser/miniforge3/etc/profile.d/conda.sh\nconda activate isce2_env\n' \
    >> '/home/$LinuxUser/.bashrc'
}
"@

Write-Host "Downloading this SAR helper project inside WSL..."
Invoke-WslUser @"
set -e
if [ ! -d '/home/$LinuxUser/sar_project/.git' ]; then
  git clone '$ProjectRepo' '/home/$LinuxUser/sar_project'
fi
"@

Write-Host "Verifying ISCE2 and topsStack..."
Invoke-WslUser @"
set -e
python_bin='/home/$LinuxUser/miniforge3/envs/isce2_env/bin/python'
"`$python_bin" -c 'import isce; print("ISCE import OK:", isce.__file__)'
"`$python_bin" '/home/$LinuxUser/isce2/contrib/stack/topsStack/stackSentinel.py' --help \
  >/tmp/stackSentinel-help.txt
head -n 5 /tmp/stackSentinel-help.txt
"@

Write-Host ""
Write-Host "ISCE2 installation completed."
Write-Host "Open it with: wsl -d $Distro"
Write-Host "Project path: /home/$LinuxUser/sar_project"
