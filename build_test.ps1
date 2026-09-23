# Build TestPixelPomoArtKit.exe — the pre-release build, for trying a version
# before it is pushed and released. See run_art_kit_test.py for what it does
# differently (inert updater, its own data folder, "[TEST]" in the title).
#
# The try/finally is the point of this script existing at all. Setting
# ARTKIT_TEST_BUILD by hand and forgetting to clear it leaves the variable in
# the shell, and the NEXT `pyinstaller PixelPomoArtKit.spec` in that window
# quietly produces a test binary instead of a release one — with no error and
# nothing in the output to notice. Here it cannot outlive the build.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$exe = Join-Path $PSScriptRoot 'dist\TestPixelPomoArtKit.exe'

# A running copy holds the .exe open, PyInstaller cannot overwrite it, and the
# only sign is a PermissionError buried in a thousand INFO lines - the script
# then found the OLD file and reported a successful build. Testing a stale
# binary is the most expensive failure this script can have, so it refuses to
# start instead.
$running = Get-Process -Name 'TestPixelPomoArtKit' -ErrorAction SilentlyContinue
if ($running) {
    Write-Error "TestPixelPomoArtKit.exe is running (PID $($running.Id -join ', ')). Close it first - the build cannot overwrite a running .exe."
}
$before = if (Test-Path $exe) { (Get-Item $exe).LastWriteTime } else { [datetime]::MinValue }

$env:ARTKIT_TEST_BUILD = '1'
try {
    # --clean: with nothing changed since the last build, PyInstaller decides
    # the .exe is up to date and never writes it - which the check below
    # cannot tell from a file held open, and reported as one. A clean build
    # always writes it, so "built" always means "built just now".
    python -m PyInstaller PixelPomoArtKit.spec --noconfirm --clean
} finally {
    Remove-Item Env:\ARTKIT_TEST_BUILD -ErrorAction SilentlyContinue
}

if ((Test-Path $exe) -and (Get-Item $exe).LastWriteTime -le $before) {
    Write-Error "$exe was not rewritten - it is still the build from $before. Something held the file open."
}
if (Test-Path $exe) {
    $version = (python -c "import sys; sys.path.insert(0, r'$PSScriptRoot'); from art_kit.version import VERSION; print(VERSION)")
    $size = [math]::Round((Get-Item $exe).Length / 1MB, 1)
    Write-Host ""
    Write-Host "  built v$version  ->  $exe  ($size MB)" -ForegroundColor Green
    Write-Host "  drawings: %LOCALAPPDATA%\PixelPomoArtKit-Test\  (a copy; the real library is not touched)"
} else {
    Write-Error "the build reported success but $exe is not there"
}
