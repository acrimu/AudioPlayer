# Build script for Windows (PowerShell)
# Run this from the project root to build the AudioPlayer bundle (uses the spec file).
# This ensures version bundle metadata remains consistent.

Set-StrictMode -Version Latest

# Ensure PyInstaller is available
if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
    Write-Error "pyinstaller is not installed or not on PATH. Install it with: pip install pyinstaller"
    exit 1
}

# Run PyInstaller using the spec file (non-interactive)
pyinstaller --clean --noconfirm AudioPlayer.spec
