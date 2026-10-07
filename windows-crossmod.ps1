param(
    [ValidateSet("doctor","setup","build","guest","sm64","start","all")]
    [string]$Action = "start"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "ERROR: $Message" -ForegroundColor Red
    exit 1
}

function Require-Command([string]$Name, [string]$Hint) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        Fail "$Name was not found. $Hint"
    }
}

function Get-MsysBash {
    $candidates = @()
    if ($env:MSYS2_ROOT) { $candidates += (Join-Path $env:MSYS2_ROOT "usr\bin\bash.exe") }
    $candidates += "C:\msys64\usr\bin\bash.exe"
    $candidates += "C:\tools\msys64\usr\bin\bash.exe"
    foreach ($p in $candidates) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

function Invoke-Python([string[]]$PythonArgs) {
    & python @PythonArgs
    if ($LASTEXITCODE -ne 0) {
        Fail "Python command failed: python $($PythonArgs -join ' ')"
    }
}

function Doctor([switch]$RequireRom, [switch]$RequireBuild) {
    Write-Host "=== Native Minecraft fusion doctor ===" -ForegroundColor Cyan
    Require-Command "git" "Install Git for Windows."
    Require-Command "python" "Install Python 3 and add it to PATH."

    $bash = Get-MsysBash
    if (-not $bash) { Fail "MSYS2 was not found. Expected C:\msys64\usr\bin\bash.exe" }
    Write-Host "MSYS2: OK ($bash)"
    Write-Host "Java/Fabric: not used in this branch" -ForegroundColor DarkGray

    if ($RequireRom) {
        $romA = Join-Path $Root "rom\baserom.us.z64"
        $romB = Join-Path $Root "baserom.us.z64"
        if (-not (Test-Path $romA) -and -not (Test-Path $romB)) {
            Fail "Put your own clean USA baserom.us.z64 in rom\baserom.us.z64 or the repo root."
        }
        Write-Host "SM64 ROM: OK"
    }

    if ($RequireBuild) {
        $buildDir = Join-Path $Root "vendor\sm64-port\build\us_pc"
        $exe = Get-ChildItem $buildDir -Filter *.exe -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $exe) { Fail "Native SM64 fusion is not built. Run .\build-sm64.bat first." }
        Write-Host "Native fusion EXE: OK"
    }
}

function Setup {
    Doctor
    $bash = Get-MsysBash

    Write-Host ""
    Write-Host "Ensuring MSYS2 native build packages..." -ForegroundColor Cyan
    & $bash -lc "pacman -S --needed --noconfirm make git python mingw-w64-x86_64-gcc mingw-w64-x86_64-SDL2 mingw-w64-x86_64-glew"
    if ($LASTEXITCODE -ne 0) { Fail "MSYS2 package setup failed." }

    Write-Host ""
    Write-Host "Refreshing Universal Modder reference + clean sm64-port..." -ForegroundColor Cyan
    Invoke-Python @("tools\bootstrap_um.py")
    Invoke-Python @("tools\generate_native_minecraft.py")
    Invoke-Python @("tools\patch_sm64_toolchain.py")

    Write-Host ""
    Write-Host "Native setup complete. No Minecraft guest process is required." -ForegroundColor Green
}

function Build {
    Doctor -RequireRom
    Write-Host ""
    Write-Host "Building one-process SM64 + Native Minecraft fusion..." -ForegroundColor Cyan
    Invoke-Python @("tools\build_sm64.py")
    Write-Host "Native fusion build complete." -ForegroundColor Green
}

function Start-Sm64 {
    Doctor -RequireBuild
    $buildDir = Join-Path $Root "vendor\sm64-port\build\us_pc"
    $exe = Get-ChildItem $buildDir -Filter *.exe | Select-Object -First 1
    Write-Host "Starting one-process fusion: $($exe.FullName)"
    Start-Process -FilePath $exe.FullName -WorkingDirectory $exe.DirectoryName
}

function Start-Crossmod {
    Start-Sm64
    Write-Host ""
    Write-Host "Started one process only: SM64 + Native Minecraft runtime." -ForegroundColor Green
}

switch ($Action) {
    "doctor" { Doctor -RequireRom }
    "setup"  { Setup }
    "build"  { Build }
    "guest"  { Fail "There is no Fabric/Minecraft guest anymore on native-minecraft-fusion. Use start-crossmod.bat." }
    "sm64"   { Start-Sm64 }
    "start"  { Start-Crossmod }
    "all"    { Setup; Build; Start-Crossmod }
}
