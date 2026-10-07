param(
    [ValidateSet("doctor","setup","build","guest","sm64","start","all")]
    [string]$Action = "start"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Tools = Join-Path $Root ".tools"
$LocalJdkRoot = Join-Path $Tools "jdk25"
$BuildStamp = Join-Path $Root ".crossmod-build-head"
$script:GuestStartTime = $null
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

function Get-JavaMajorFrom([string]$JavaExe) {
    if (-not (Test-Path $JavaExe)) { return 0 }
    $command = '"{0}" -version 2>&1' -f $JavaExe
    $output = & cmd.exe /d /c $command
    $line = $output | Select-Object -First 1
    if ($line -match 'version\s+"?(\d+)') { return [int]$Matches[1] }
    if ($line -match 'openjdk\s+(\d+)') { return [int]$Matches[1] }
    return 0
}

function Use-JavaHome([string]$Home) {
    $env:JAVA_HOME = $Home
    $env:Path = "$Home\bin;$env:Path"
}

function Find-LocalJava25 {
    if (-not (Test-Path $LocalJdkRoot)) { return $null }
    $java = Get-ChildItem $LocalJdkRoot -Filter java.exe -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match '\\bin\\java\.exe$' } |
        Select-Object -First 1
    if ($java -and (Get-JavaMajorFrom $java.FullName) -eq 25) {
        return Split-Path -Parent (Split-Path -Parent $java.FullName)
    }
    return $null
}

function Ensure-Java25 {
    if ($env:JAVA_HOME) {
        $candidate = Join-Path $env:JAVA_HOME "bin\java.exe"
        if ((Get-JavaMajorFrom $candidate) -eq 25) {
            Use-JavaHome $env:JAVA_HOME
            Write-Host "Java 25: OK ($candidate)" -ForegroundColor Green
            return
        }
    }

    $system = Get-Command java -ErrorAction SilentlyContinue
    if ($system -and (Get-JavaMajorFrom $system.Source) -eq 25) {
        $home = Split-Path -Parent (Split-Path -Parent $system.Source)
        Use-JavaHome $home
        Write-Host "Java 25: OK ($($system.Source))" -ForegroundColor Green
        return
    }

    $local = Find-LocalJava25
    if ($local) {
        Use-JavaHome $local
        Write-Host "Java 25: OK (local $local)" -ForegroundColor Green
        return
    }

    Write-Host "Java 25 not found. Downloading local Temurin JDK 25..." -ForegroundColor Cyan
    New-Item -ItemType Directory -Force -Path $Tools | Out-Null
    if (Test-Path $LocalJdkRoot) { Remove-Item $LocalJdkRoot -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $LocalJdkRoot | Out-Null

    try {
        $api = "https://api.adoptium.net/v3/assets/latest/25/hotspot?architecture=x64&heap_size=normal&image_type=jdk&jvm_impl=hotspot&os=windows&vendor=eclipse"
        $assets = Invoke-RestMethod -Uri $api -UseBasicParsing
        $asset = $assets | Where-Object { $_.binary.package.link } | Select-Object -First 1
        if (-not $asset) { throw "Adoptium returned no Windows x64 JDK 25 package." }
        $zip = Join-Path $Tools "jdk25.zip"
        Invoke-WebRequest -Uri $asset.binary.package.link -OutFile $zip -UseBasicParsing
        Expand-Archive -Path $zip -DestinationPath $LocalJdkRoot -Force
        Remove-Item $zip -Force
    } catch {
        Fail "Could not download JDK 25 automatically: $($_.Exception.Message)"
    }

    $local = Find-LocalJava25
    if (-not $local) { Fail "JDK 25 download finished, but java.exe was not found." }
    Use-JavaHome $local
    Write-Host "Java 25 installed locally: $local" -ForegroundColor Green
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

function Wait-Guest([int]$Seconds = 180) {
    Write-Host "Waiting for real Minecraft on 127.0.0.1:25599 ..." -ForegroundColor Cyan
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Port25599) {
            Write-Host "Minecraft passthrough is ready." -ForegroundColor Green
            return
        }
        Start-Sleep -Milliseconds 750
    }
    Fail "Minecraft did not open port 25599 within $Seconds seconds. Check generated\minecraft-guest\run\logs\latest.log."
}

function Invoke-Python([string[]]$PythonArgs) {
    & python @PythonArgs
    if ($LASTEXITCODE -ne 0) {
        Fail "Python command failed: python $($PythonArgs -join ' ')"
    }
}

function Ensure-WindowApi {
    if ("CrossmodWindow" -as [type]) { return }
    Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class CrossmodWindow {
    [DllImport("user32.dll", SetLastError=true)]
    public static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll", SetLastError=true)]
    public static extern bool GetClientRect(IntPtr hWnd, out RECT lpRect);
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left, Top, Right, Bottom; }
}
"@
}

function Get-NewJavaWindows {
    if (-not $script:GuestStartTime) { return @() }
    return @(Get-Process java,javaw -ErrorAction SilentlyContinue |
        Where-Object {
            $_.MainWindowHandle -ne 0 -and
            $_.StartTime -ge $script:GuestStartTime.AddSeconds(-5)
        })
}

function Move-MinecraftOffscreen {
    Ensure-WindowApi
    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        foreach ($p in (Get-NewJavaWindows)) {
            if ($p.MainWindowHandle -ne 0) {
                [CrossmodWindow]::ShowWindow($p.MainWindowHandle, 9) | Out-Null
                [CrossmodWindow]::SetWindowPos($p.MainWindowHandle,[IntPtr]::Zero,-32000,0,1280,720,0x0010) | Out-Null
                Write-Host "Minecraft render window moved offscreen (still rendering)." -ForegroundColor DarkGray
                return
            }
        }
        Start-Sleep -Milliseconds 500
    }
    Write-Host "Minecraft window was not found for offscreen placement; passthrough can still run." -ForegroundColor Yellow
}

function Stop-GuestProcesses {
    if (-not $script:GuestStartTime) { return }
    Get-Process java,javaw -ErrorAction SilentlyContinue |
        Where-Object { $_.StartTime -ge $script:GuestStartTime.AddSeconds(-5) } |
        ForEach-Object {
            try { Stop-Process -Id $_.Id -Force -ErrorAction Stop } catch {}
        }
}

function Doctor([switch]$RequireRom, [switch]$RequireBuild) {
    Write-Host "=== SM64 x real Minecraft doctor ===" -ForegroundColor Cyan
    Require-Command "git" "Install Git for Windows."
    Require-Command "python" "Install Python 3 and add it to PATH."
    Ensure-Java25

    $bash = Get-MsysBash
    if (-not $bash) {
        Fail "MSYS2 was not found. Install MSYS2 to C:\msys64 once; after that windows-all.bat handles the rest."
    }
    Write-Host "MSYS2: OK ($bash)" -ForegroundColor Green

    if ($RequireRom) {
        $romA = Join-Path $Root "rom\baserom.us.z64"
        $romB = Join-Path $Root "baserom.us.z64"
        if (-not (Test-Path $romA) -and -not (Test-Path $romB)) {
            Fail "Put your own clean USA baserom.us.z64 in rom\baserom.us.z64 or the repo root."
        }
        Write-Host "SM64 ROM: OK" -ForegroundColor Green
    }

    if ($RequireBuild) {
        $buildDir = Join-Path $Root "vendor\sm64coopdx\build\us_pc"
        $exe = Get-ChildItem $buildDir -Filter *.exe -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $exe) { Fail "SM64 is not built. Run windows-all.bat once." }
        Write-Host "SM64CoopDX host EXE: OK" -ForegroundColor Green
    }
}

function Setup {
    Doctor
    if (Test-Port25599) { Fail "A passthrough Minecraft client is already running. Close it before setup/build." }

    $bash = Get-MsysBash
    Write-Host ""
    Write-Host "Ensuring MSYS2 build packages..." -ForegroundColor Cyan
    & $bash -lc "pacman -S --needed --noconfirm make git python mingw-w64-x86_64-gcc mingw-w64-x86_64-SDL2 mingw-w64-x86_64-glew"
    if ($LASTEXITCODE -ne 0) { Fail "MSYS2 package setup failed." }

    Write-Host ""
    Write-Host "Refreshing Universal Modder and real Minecraft guest..." -ForegroundColor Cyan
    Invoke-Python @("tools\bootstrap_um.py")
    Invoke-Python @("tools\sync_um_reference.py")
    Invoke-Python @("tools\patch_guest_for_sm64.py")
    Invoke-Python @("tools\generate_sm64_host.py")

    Write-Host ""
    Write-Host "Building the real Universal Modder Minecraft guest..." -ForegroundColor Cyan
    Push-Location (Join-Path $Root "generated\minecraft-guest")
    try {
        & .\gradlew.bat build --no-daemon
        if ($LASTEXITCODE -ne 0) { Fail "Minecraft guest build failed." }
    } finally {
        Pop-Location
    }
    Write-Host "Setup complete." -ForegroundColor Green
}

function Get-CurrentRepoHead {
    try {
        $head = (& git rev-parse HEAD 2>$null | Select-Object -First 1)
        if ($LASTEXITCODE -eq 0 -and $head) { return $head.Trim() }
    } catch {}
    return $null
}

function Write-BuildStamp {
    $head = Get-CurrentRepoHead
    if ($head) {
        Set-Content -Path $BuildStamp -Value $head -Encoding ASCII
    }
}

function Test-BuildFresh {
    $head = Get-CurrentRepoHead
    if (-not $head -or -not (Test-Path $BuildStamp)) { return $false }
    $built = (Get-Content $BuildStamp -ErrorAction SilentlyContinue | Select-Object -First 1)
    return $built -and $built.Trim() -eq $head
}

function Ensure-FreshBuild {
    if (Test-BuildFresh) { return }

    Write-Host ""
    Write-Host "Crossmod sources changed since the last build." -ForegroundColor Yellow
    Write-Host "Rebuilding the real Minecraft + SM64 integration so an old build cannot start..." -ForegroundColor Cyan
    Setup
    Build
}

function Build {
    Doctor -RequireRom
    Write-Host ""
    Write-Host "Building SM64CoopDX host with Universal Modder passthrough..." -ForegroundColor Cyan
    Invoke-Python @("tools\build_sm64.py")
    Write-BuildStamp
    Write-Host "SM64CoopDX host build complete." -ForegroundColor Green
}

function Start-Guest {
    Ensure-Java25
    $gradle = Join-Path $Root "generated\minecraft-guest\gradlew.bat"
    if (-not (Test-Path $gradle)) { Fail "Minecraft guest is missing. Run windows-all.bat once." }
    if (Test-Port25599) {
        Write-Host "Minecraft passthrough is already running."
        return
    }

    $guestDir = Join-Path $Root "generated\minecraft-guest"
    $script:GuestStartTime = Get-Date
    $cmd = 'set "JAVA_HOME={0}" && set "PATH={0}\bin;%PATH%" && cd /d "{1}" && gradlew.bat runClient --no-daemon' -f $env:JAVA_HOME,$guestDir
    Start-Process -FilePath "cmd.exe" -ArgumentList "/d","/c",$cmd -WorkingDirectory $guestDir -WindowStyle Hidden | Out-Null
}

function Start-Sm64 {
    Doctor -RequireBuild
    $buildDir = Join-Path $Root "vendor\sm64coopdx\build\us_pc"
    $exe = Get-ChildItem $buildDir -Filter *.exe | Select-Object -First 1
    Write-Host "Starting SM64CoopDX host: $($exe.Name)" -ForegroundColor Cyan
    return Start-Process -FilePath $exe.FullName -WorkingDirectory $exe.DirectoryName -PassThru
}

function Resize-Sm64Widescreen([System.Diagnostics.Process]$Process) {
    Ensure-WindowApi
    $deadline = (Get-Date).AddSeconds(20)
    while ((Get-Date) -lt $deadline) {
        $Process.Refresh()
        if ($Process.MainWindowHandle -ne 0) {
            # Target a 1280x720 CLIENT area. Add normal window chrome margin.
            # Windows will clamp to the desktop if needed.
            [CrossmodWindow]::SetWindowPos(
                $Process.MainWindowHandle,
                [IntPtr]::Zero,
                80, 80,
                1296, 759,
                0x0004
            ) | Out-Null
            Start-Sleep -Milliseconds 300
            Write-Host "SM64 viewport forced to widescreen (~1280x720 client)." -ForegroundColor DarkGray
            return
        }
        Start-Sleep -Milliseconds 250
    }
}

function Focus-Sm64([System.Diagnostics.Process]$Process) {
    Ensure-WindowApi
    $deadline = (Get-Date).AddSeconds(20)
    while ((Get-Date) -lt $deadline) {
        $Process.Refresh()
        if ($Process.MainWindowHandle -ne 0) {
            [CrossmodWindow]::SetForegroundWindow($Process.MainWindowHandle) | Out-Null
            return
        }
        Start-Sleep -Milliseconds 250
    }
}

function Start-Crossmod {
    Ensure-FreshBuild
    Start-Guest
    Wait-Guest
    Move-MinecraftOffscreen

    $sm64 = Start-Sm64
    Resize-Sm64Widescreen $sm64
    Focus-Sm64 $sm64

    Write-Host ""
    Write-Host "READY: use only the SM64 window. Minecraft runs automatically behind it." -ForegroundColor Green
    Write-Host "WASD / mouse / Space / Ctrl / Shift / LMB / RMB / E / Q / F / 1-9 / F5" -ForegroundColor Green

    try {
        Wait-Process -Id $sm64.Id
    } finally {
        Stop-GuestProcesses
    }
}

switch ($Action) {
    "doctor" { Doctor -RequireRom }
    "setup"  { Setup }
    "build"  { Build }
    "guest"  { Start-Guest; Wait-Guest; Move-MinecraftOffscreen }
    "sm64"   { $p = Start-Sm64; Focus-Sm64 $p }
    "start"  { Start-Crossmod }
    "all"    { Setup; Build; Start-Crossmod }
}
