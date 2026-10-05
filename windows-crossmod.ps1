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

function Get-JavaMajor {
    $line = (& java -version 2>&1 | Select-Object -First 1)
    if ($line -match 'version\s+"?(\d+)') { return [int]$Matches[1] }
    if ($line -match 'openjdk\s+(\d+)') { return [int]$Matches[1] }
    return 0
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

function Test-Port25599 {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $client.BeginConnect("127.0.0.1",25599,$null,$null)
        if (-not $iar.AsyncWaitHandle.WaitOne(250)) { return $false }
        $client.EndConnect($iar)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Wait-Guest([int]$Seconds = 120) {
    Write-Host "Waiting for Minecraft guest on 127.0.0.1:25599 ..."
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Port25599) {
            Write-Host "Minecraft guest is ready." -ForegroundColor Green
            return
        }
        Start-Sleep -Milliseconds 750
    }
    Fail "Minecraft did not open port 25599 within $Seconds seconds. Check the Minecraft Guest window."
}

function Invoke-Python([string[]]$Args) {
    & python @Args
    if ($LASTEXITCODE -ne 0) { Fail "Python command failed: python $($Args -join ' ')" }
}

function Doctor([switch]$RequireRom, [switch]$RequireBuild) {
    Write-Host "=== Windows doctor ===" -ForegroundColor Cyan
    Require-Command "git" "Install Git for Windows."
    Require-Command "python" "Install Python 3 and add it to PATH."
    Require-Command "java" "Install JDK 25 and add it to PATH."

    $major = Get-JavaMajor
    if ($major -ne 25) { Fail "JDK 25 is required. Detected Java major version: $major" }
    Write-Host "Java 25: OK"

    $bash = Get-MsysBash
    if (-not $bash) { Fail "MSYS2 was not found. Expected C:\msys64\usr\bin\bash.exe" }
    Write-Host "MSYS2: OK ($bash)"

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
        if (-not $exe) { Fail "SM64 is not built. Run .\build-sm64.bat first." }
        Write-Host "SM64 host EXE: OK"
    }
}

function Setup {
    Doctor
    $bash = Get-MsysBash

    Write-Host ""
    Write-Host "Ensuring MSYS2 build packages..." -ForegroundColor Cyan
    & $bash -lc "pacman -S --needed --noconfirm make git python mingw-w64-x86_64-gcc mingw-w64-x86_64-SDL2 mingw-w64-x86_64-glew"
    if ($LASTEXITCODE -ne 0) { Fail "MSYS2 package setup failed." }

    Write-Host ""
    Write-Host "Refreshing Universal Modder + clean sm64-port..." -ForegroundColor Cyan
    Invoke-Python @("tools\bootstrap_um.py")
    Invoke-Python @("tools\sync_um_reference.py")
    Invoke-Python @("tools\generate_sm64_host.py")
    Invoke-Python @("tools\patch_sm64_toolchain.py")

    Write-Host ""
    Write-Host "Validating the Universal Modder Minecraft guest..." -ForegroundColor Cyan
    Push-Location (Join-Path $Root "generated\minecraft-guest")
    try {
        & .\gradlew.bat build --no-daemon
        if ($LASTEXITCODE -ne 0) { Fail "Minecraft guest build failed." }
    } finally {
        Pop-Location
    }

    Write-Host ""
    Write-Host "Setup complete." -ForegroundColor Green
}

function Build {
    Doctor -RequireRom
    Write-Host ""
    Write-Host "Building a pristine generated SM64 host..." -ForegroundColor Cyan
    Invoke-Python @("tools\build_sm64.py")
    Write-Host "SM64 build complete." -ForegroundColor Green
}

function Start-Guest {
    $gradle = Join-Path $Root "generated\minecraft-guest\gradlew.bat"
    if (-not (Test-Path $gradle)) { Fail "Minecraft guest is missing. Run .\setup-windows.bat first." }

    if (Test-Port25599) {
        Write-Host "Minecraft guest is already running."
        return
    }

    $guestDir = Join-Path $Root "generated\minecraft-guest"
    $cmd = 'cd /d "{0}" && gradlew.bat runClient' -f $guestDir
    Start-Process -FilePath "cmd.exe" -ArgumentList "/k",$cmd -WorkingDirectory $guestDir
}

function Start-Sm64 {
    Doctor -RequireBuild
    $buildDir = Join-Path $Root "vendor\sm64-port\build\us_pc"
    $exe = Get-ChildItem $buildDir -Filter *.exe | Select-Object -First 1
    Write-Host "Starting $($exe.FullName)"
    Start-Process -FilePath $exe.FullName -WorkingDirectory $exe.DirectoryName
}

function Start-Crossmod {
    Start-Guest
    Wait-Guest
    Start-Sm64
    Write-Host ""
    Write-Host "Crossmod started: Minecraft guest + SM64 host." -ForegroundColor Green
}

switch ($Action) {
    "doctor" { Doctor -RequireRom }
    "setup"  { Setup }
    "build"  { Build }
    "guest"  { Start-Guest }
    "sm64"   { Start-Sm64 }
    "start"  { Start-Crossmod }
    "all"    { Setup; Build; Start-Crossmod }
}
