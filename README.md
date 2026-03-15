 Audio Player (Cross-Platform Python Audio Player)
 
 Author:    Adrian Crimu
 
 License:   MIT License
 
 Created:   2026-03-03

 Description:
    A full-featured, cross-platform desktop audio player built with
    Tkinter (TkinterDnD) and VLC. Supports modern playlist management,
    drag & drop, metadata extraction, and persistent user settings.

    Designed to run on macOS, Windows, and Linux.

 Core Features:

    • Play / Pause / Stop / Next / Previous
    • Visual playback indicators inside playlist:
        ▶ Playing
        ⏸ Paused
        ■ Stopped
    • Auto-play next track when current song ends
    • Resume playback when unpausing
    • Skip wrapping (circular navigation)

 Playlist Management:

    • Add individual songs
    • Add entire folders (recursive scan)
    • Drag & drop files and folders (Windows/macOS/Linux compatible parsing)
    • Delete selected tracks (multi-selection supported)
    • Clear entire playlist
    • Move tracks up/down (buttons + Ctrl+U / Ctrl+D shortcuts)
    • Playlist auto-renumbering
    • Save playlist as JSON
    • Load playlist from JSON
    • Automatic last-playlist persistence
    • Recent playlists menu (max 10 entries, persistent)
    • Clear recent list option

 Audio & Metadata:

    • VLC-based playback engine (python-vlc)
    • Duration detection via VLC (fallback to mutagen)
    • MP3 metadata via EasyID3
    • Metadata extraction for multiple formats via mutagen
    • Supported formats:
        .mp3, .wav, .flac, .ogg, .aac, .m4a, .wma
    • Format label shown for non-MP3 files
    • Volume control (0–150%)
    • Click-to-seek progress bar
    • Real-time elapsed / total time display

 User Interface:

    • Tkinter Treeview-based playlist
    • Highlight currently playing track
    • Context menu (right-click / two-finger click / Ctrl+Click)
    • Responsive progress bar with custom height
    • Now Playing label with dynamic state text
    • Cross-platform user data storage:
        macOS: ~/Library/Application Support/AudioPlayer
        Windows: ~/AppData/Local/AudioPlayer
        Linux: ~/.audioplayer

 Persistence:

    • Stores:
        - Last playlist
        - Recent playlists
    • Automatically creates user data directory if missing

 Requirements:

    Python 3.8+

    Required modules:
        - python-vlc
        - mutagen
        - tkinter (standard library)
        - tkinterdnd2
        - json, os, sys, subprocess, platform, pathlib (standard)

 Run:

    $ python3 AudioPlayer.py

 Build:

    pyinstaller --clean --windowed \
      --name AudioPlayer \
      --icon resources/icon.icns \
      --add-data "resources:resources" \
      AudioPlayer.py

 Notes:

    • Designed for clean packaging into macOS / Windows executable builds.
    • Safe error handling around VLC and metadata parsing.
    • Playlist integrity maintained during reordering and deletion.
    • Cross-platform drag & drop parsing implemented manually for reliability.
