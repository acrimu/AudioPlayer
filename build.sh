#!/usr/bin/env bash
# Build AudioPlayer using the provided spec file.
# This ensures the macOS bundle and version info are kept in sync.

set -euo pipefail

pyinstaller --clean --noconfirm AudioPlayer.spec
