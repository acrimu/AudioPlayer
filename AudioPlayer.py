#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
 Project:   Audio Player (Cross-Platform Python Audio Player)
 File:      AudioPlayer.py
 Author:    Adrian Crimu
 GitHub:    https://github.com/acrimu/AudioPlayer
 License:   MIT License
 Created:   2026-03-03
===============================================================================

 Description:
    A full-featured, cross-platform desktop audio player built with
    Tkinter (TkinterDnD) and VLC. Supports modern playlist management,
    drag & drop, metadata extraction, and persistent user settings.

    Designed to run on macOS, Windows, and Linux.

-------------------------------------------------------------------------------

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

-------------------------------------------------------------------------------

 Requirements:

    Python 3.8+

    Required modules:
        - python-vlc
        - mutagen
        - tkinter (standard library)
        - tkinterdnd2
        - json, os, sys, subprocess, platform, pathlib (standard)

-------------------------------------------------------------------------------

 Run:

    $ python3 AudioPlayer.py

-------------------------------------------------------------------------------

 Build Executable:

    $ pyinstaller --clean --windowed \
      --name AudioPlayer \
      --icon resources/icon.icns \
      --add-data "resources:resources" \
      AudioPlayer.py

-------------------------------------------------------------------------------

 Notes:

    • Designed for clean packaging into macOS / Windows executable builds.
    • Safe error handling around VLC and metadata parsing.
    • Playlist integrity maintained during reordering and deletion.
    • Cross-platform drag & drop parsing implemented manually for reliability.

===============================================================================
"""


import vlc
import os
import json
import time
import queue
import platform
import pathlib
from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3
from mutagen import File as MutagenFile

import tkinter as tk

from tkinter import ttk, filedialog, messagebox, font

from tkinterdnd2 import DND_FILES, TkinterDnD
import sys
import subprocess

# Application version
VERSION = "1.0.0"

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

class App(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()

        # Supported audio extensions (used by dialogs and folder scanning)
        self.SUPPORTED_EXTS = (".mp3", ".wav", ".flac", ".ogg", ".aac", ".m4a", ".wma")

        # === Logic ===
        self.current_index_playing, self.index_to_play = -1, -1
        self.current_index_playing = -1
        self.index_to_play = -1

        self.PLAYLIST_FILE = str(self.get_user_data_dir() / "last_playlist.json")
        # store recent playlists separately (max 10)
        self.RECENT_FILE = str(self.get_user_data_dir() / "recent_playlists.json")
        self.playlist = []
        self.recent_playlists = []  # will hold file paths, most-recent-first
        self.paused = False
        self.player = None
        self.current_song_length = 0
        
        self.current_index = 0
        self.index_to_play = 0
        self.current_index_playing = 0
        
        self.last_opened_folder = os.path.expanduser("~")  # Default to home folder

        # === Setup GUI ===
        icon = tk.PhotoImage(file=resource_path("resources/icon.png"))
        self.iconphoto(True, icon)
        self.title(f"🎵 Audio Player v{VERSION}")
        self.geometry("750x580")
        self.minsize(750, 500)
        
        # === Treeview ===
        self.tree_frame = ttk.Frame(self)
        self.tree_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(10, 5))

        columns = ("No.", "Title", "Artist", "Duration")
        self.tree = ttk.Treeview(self.tree_frame, columns=columns, show="headings", selectmode="extended")
        for col in columns:
            self.tree.heading(col, text=col)
        self.tree.column("No.", width=40)
        self.tree.column("Title", width=300)
        self.tree.column("Artist", width=180)
        self.tree.column("Duration", width=100, anchor='center')

        # configure a tag style for the playing item (change foreground to desired color)
        # foreground = text color, background = row background
        self.tree.tag_configure("playing", background="#6A6153", foreground="#8dff96")

        self.scroll = ttk.Scrollbar(self.tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=self.scroll.set)
        self.tree.bind("<Double-1>", lambda e: self.play_selected())
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.scroll.grid(row=0, column=1, sticky='ns')
        self.tree_frame.grid_rowconfigure(0, weight=1)
        self.tree_frame.grid_columnconfigure(0, weight=1)

        # === Register tree for drag and drop ===
        self.tree.drop_target_register(DND_FILES)
        self.tree.dnd_bind("<<Drop>>", self.handle_drop1)

        # === Now Playing Label ===
        self.label_var = tk.StringVar()
        ttk.Label(self, textvariable=self.label_var).pack(pady=(5, 5))

        # === Progress + Time ===
        # 1. Create a container frame with your exact desired height (e.g., 6 pixels)
        self.progress_frame = ttk.Frame(self, height=10, width=600)
        self.progress_frame.pack(pady=4)

        # 2. IMPORTANT: Prevent the frame from resizing to fit the progress bar's default height
        self.progress_frame.pack_propagate(False)

        # 3. Create the progress bar inside this frame
        self.progress_bar = ttk.Progressbar(
            self.progress_frame, 
            orient="horizontal", 
            mode="determinate"
        )

        # 4. Use place to make the bar fill the entire height/width of the 6-pixel frame
        self.progress_bar.place(relx=0, rely=0, relwidth=1, relheight=1)
        
        #self.progress_bar = ttk.Progressbar(self, orient="horizontal", length=600, mode="determinate")
        #self.progress_bar.pack(pady=4)
        self.progress_bar.bind("<Button-1>", lambda e: self.seek_progress(e))

        self.time_label = ttk.Label(self, text="")
        self.time_label.pack()

        
        # Get the default font used by ttk buttons
        default_font = font.nametofont("TkDefaultFont")
        zero_width = default_font.measure("0")

        # === Buttons ===
        self.btn_frame = ttk.Frame(self)
        self.btn_frame.pack(pady=12)

        # Get the list of all button labels
        button_texts1 = [
            "Prev", "Play", "Pause", "Stop", "Next"
        ]

        # Calculate max width in characters
        # We use the font to measure the longest string in pixels, 
        # then convert it back to character units or use a small buffer.
        max_pixel_width1 = max(default_font.measure(text) for text in button_texts1)
        

        # Determine the width in character units (rounding up) + padding (+1 on each side = +2)
        BTN1_WIDTH = int(max_pixel_width1 / zero_width) + 2

        def add_btn(txt, cmd, col): 
            ttk.Button(self.btn_frame, text=txt, command=cmd, width=BTN1_WIDTH)\
                .grid(row=0, column=col, padx=6)

        add_btn("Prev", lambda: self.skip(-1), 0)
        add_btn("Play", self.play_selected, 1)
        add_btn("Pause", self.pause_song, 2)
        add_btn("Stop", self.stop_song, 3)
        add_btn("Next", lambda: self.skip(1), 4)

        # === Volume Slider with 0–150% and % Display ===
        self.vol_frame = ttk.Frame(self)
        self.vol_frame.pack(pady=5)

        ttk.Label(self.vol_frame, text="Volume").pack(side=tk.LEFT)

        self.volume_percent = tk.StringVar(value="100%")  # Default: 100%

        def on_volume_change(val):
            percent = int(float(val))
            self.volume_percent.set(f"{percent}%")
            if self.player:
                self.player.audio_set_volume(min(percent, 150))  # VLC max = 150

        self.volume_slider = tk.Scale(self.vol_frame, from_=0, to=150, orient=tk.HORIZONTAL, resolution=1,
                                command=on_volume_change,
                                troughcolor="#555", highlightthickness=0, sliderlength=15, width=10,
                                showvalue=0, length=150)
        self.volume_slider.set(100)  # Default value
        self.volume_slider.pack(side=tk.LEFT, padx=8)

        ttk.Label(self.vol_frame, textvariable=self.volume_percent).pack(side=tk.LEFT, padx=6)

        # === Buttons ===
        self.btn2_frame = ttk.Frame(self)
        self.btn2_frame.pack(pady=12)

        # Get the list of all button labels
        button_texts2 = [
            "Add folder", "Add songs", "Delete", "Clear",
            "Save playlist as...", "Load playlist...", "Move up", "Move down"
        ]

        # Calculate max width in characters
        # We use the font to measure the longest string in pixels, 
        # then convert it back to character units or use a small buffer.
        max_pixel_width = max(default_font.measure(text) for text in button_texts2)
        

        # Determine the width in character units (rounding up) + padding (+1 on each side = +2)
        BTN2_WIDTH = int(max_pixel_width / zero_width) + 2

        # === Load Folder Button ===
        ttk.Button(self.btn2_frame, text="Add folder", command=lambda: self.add_folder(), width=BTN2_WIDTH
                ).grid(row=0, column=0, padx=2)

        # === Add Songs Button ===
        ttk.Button(self.btn2_frame, text="Add songs", command=lambda: self.add_songs(), width=BTN2_WIDTH
                ).grid(row=0, column=1, padx=2)

        # === Clear Button ===
        ttk.Button(self.btn2_frame, text="Delete", command=lambda: self.delete_current_song(), width=BTN2_WIDTH
                ).grid(row=0, column=2, padx=2)

        # === Clear Button ===
        ttk.Button(self.btn2_frame, text="Clear", command=lambda: self.clear_songs_list(), width=BTN2_WIDTH
                ).grid(row=0, column=3, padx=2)

        # === Save Playlist Button ===
        ttk.Button(self.btn2_frame, text="Save playlist as...", command=self.save_playlist_as, width=BTN2_WIDTH
                ).grid(row=1, column=0, padx=2)

        # === Load Playlist Button ===
        ttk.Button(self.btn2_frame, text="Load playlist...", command=self.load_playlist_from_file, width=BTN2_WIDTH
                ).grid(row=1, column=1, padx=2)

        # === Move Up / Move Down Buttons ===
        ttk.Button(self.btn2_frame, text="Move up", command=lambda: self.move_selected_up(), width=BTN2_WIDTH
                ).grid(row=1, column=2, padx=2)
        ttk.Button(self.btn2_frame, text="Move down", command=lambda: self.move_selected_down(), width=BTN2_WIDTH
                ).grid(row=1, column=3, padx=2)


        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="Delete from list", command=lambda: self.delete_current_song())
        self.context_menu.add_command(label="Move up", command=lambda: self.move_selected_up())
        self.context_menu.add_command(label="Move down", command=lambda: self.move_selected_down())

        # === menu bar (for recent playlists, file operations) ===
        self.menu_bar = tk.Menu(self)
        self.config(menu=self.menu_bar)
        file_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Load playlist...", command=self.load_playlist_from_file)
        file_menu.add_command(label="Save playlist as...", command=self.save_playlist_as)
        file_menu.add_separator()
        self.recent_menu = tk.Menu(file_menu, tearoff=0)
        file_menu.add_cascade(label="Recent playlists", menu=self.recent_menu)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit)

        # Add Help menu with About
        help_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self.show_about)

        # populate recent list now that menu exists
        self.load_recent_playlists()

        self.tree.bind("<Button-2>", self.show_context_menu)  # Two finger click on Mac
        self.tree.bind("<Button-3>", self.show_context_menu)  # Right-click on Windows/Linux
        self.tree.bind("<Control-Button-1>", self.show_context_menu)  # Ctrl+Click on Mac

        # keyoard shortcuts for quick reordering
        self.bind_all("<Control-u>", lambda e: self.move_selected_up())
        self.bind_all("<Control-d>", lambda e: self.move_selected_down())
        # macOS sleep listener support removed

        # === Start ===
        self.load_saved_playlist()
        # ensure recent menu entries are up‑to‑date after startup
        self.refresh_recent_menu()

    def handle_drop(self, event):
        """Handle drag and drop of files onto the treeview."""
        # Some events (e.g. stray virtual events) may not include a ``data`` field.
        # Ensure we don't crash in that case.
        # event.data is the dropped files string
        paths = self.split_dnd_files(event.data)
        
        for path in paths:
            if path.lower().endswith(self.SUPPORTED_EXTS):
                self.add_song_to_list(path)

        return event.action  # Return action to complete the drop
    
    def get_user_data_dir(self):
        """Get the appropriate user data directory for storing application data."""
        if platform.system() == "Darwin":  # macOS
            data_dir = pathlib.Path.home() / "Library" / "Application Support" / "AudioPlayer"
        elif platform.system() == "Windows":
            data_dir = pathlib.Path.home() / "AppData" / "Local" / "AudioPlayer"
        else:  # Linux and others
            data_dir = pathlib.Path.home() / ".audioplayer"
        
        # Ensure the directory exists
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir



    def get_audio_duration(self, filepath):
        """Try VLC first (works for most formats). Fall back to mutagen if VLC fails."""
        try:
            instance = vlc.Instance()
            media = instance.media_new(filepath)
            # blocking parse to ensure duration available
            media.parse()
            dur_ms = media.get_duration()
            if dur_ms and dur_ms > 0:
                return int(dur_ms / 1000)
        except Exception:
            pass

        # Fallback to mutagen (gives length in seconds if supported)
        try:
            audio = MutagenFile(filepath)
            if audio and hasattr(audio, "info") and getattr(audio.info, "length", None):
                return int(audio.info.length)
        except Exception:
            pass

        return 0

    def renumber_tree(self):
        """Update the 'No.' column to reflect the current order in the tree."""
        for idx, item in enumerate(self.tree.get_children(), start=1):
            values = list(self.tree.item(item, "values"))
            values[0] = str(idx)
            self.tree.item(item, values=values)

    # --- play marker helpers ---
    def clear_playing_mark(self):
        """Remove playing marker (▶) and tags from all rows."""
        for item in self.tree.get_children():
            vals = list(self.tree.item(item, "values"))
            if vals and len(vals) > 1 and isinstance(vals[1], str) and vals[1].startswith("▶ "):
                vals[1] = vals[1][2:]
                self.tree.item(item, values=vals)
            # clear tags for safety
            self.tree.item(item, tags=())

    # --- play marker helpers ---
    def clear_stop_mark(self):
        """Remove playing marker (▶) and tags from all rows."""
        for item in self.tree.get_children():
            vals = list(self.tree.item(item, "values"))
            if vals and len(vals) > 1 and isinstance(vals[1], str) and vals[1].startswith("■ "):
                vals[1] = vals[1][2:]
                self.tree.item(item, values=vals)
            # clear tags for safety
            self.tree.item(item, tags=())

    def mark_pause_item(self, index):
        """Mark the row at `index` as pause (add ⏸ prefix + 'playing' tag) and clear others."""
        children = self.tree.get_children()
        if not children:
            return
        for i, item in enumerate(children):
            vals = list(self.tree.item(item, "values"))
            # ensure there's a title column
            if not vals or len(vals) < 2:
                continue
            if i == index:
                # remove stop marker if present
                if vals[1].startswith("▶ ") or vals[1].startswith("⏸ ") or vals[1].startswith("■ "):
                    vals[1] = vals[1][2:]
                if not vals[1].startswith("⏸ "):
                    vals[1] = "⏸ " + vals[1]
                    self.tree.item(item, values=vals)
                self.tree.item(item, tags=("playing",))
            else:
                if vals[1].startswith("▶ ") or vals[1].startswith("⏸ ") or vals[1].startswith("■ "):
                    vals[1] = vals[1][2:]
                    self.tree.item(item, values=vals)
                self.tree.item(item, tags=())

    def mark_playing_item(self, index):
        """Mark the row at `index` as pause (add ⏸ prefix + 'playing' tag) and clear others."""
        children = self.tree.get_children()
        if not children:
            return
        for i, item in enumerate(children):
            vals = list(self.tree.item(item, "values"))
            # ensure there's a title column
            if not vals or len(vals) < 2:
                continue
            if i == index:
                # remove stop marker if present
                if vals[1].startswith("▶ ") or vals[1].startswith("⏸ ") or vals[1].startswith("■ "):
                    vals[1] = vals[1][2:]
                if not vals[1].startswith("▶ "):
                    vals[1] = "▶ " + vals[1]
                    self.tree.item(item, values=vals)
                self.tree.item(item, tags=("playing",))
            else:
                if vals[1].startswith("▶ ") or vals[1].startswith("⏸ ") or vals[1].startswith("■ "):
                    vals[1] = vals[1][2:]
                    self.tree.item(item, values=vals)
                self.tree.item(item, tags=())

    def add_song_to_list(self, path):
        """Add a file to playlist and populate sensible title/artist for many formats."""
        if not os.path.isfile(path):
            return

        ext = os.path.splitext(path)[1].lower()
        basename = os.path.basename(path)
        title = basename
        artist = "Unknown"

        # MP3: prefer EasyID3
        if ext == ".mp3":
            try:
                tags = EasyID3(path)
                title = tags.get("title", [basename])[0]
                artist = tags.get("artist", ["Unknown"])[0]
            except Exception:
                pass
        else:
            # Other formats: use mutagen generic File and try common tag keys
            try:
                audio = MutagenFile(path)
                if audio and audio.tags:
                    # try common keys (many formats provide lists)
                    def first_tag(tags, *keys):
                        for k in keys:
                            if k in tags:
                                v = tags[k]
                                try:
                                    return v[0] if isinstance(v, (list, tuple)) else str(v)
                                except Exception:
                                    return str(v)
                        return None

                    t = first_tag(audio.tags, "title", "TITLE", "TIT2", "\xa9nam")
                    a = first_tag(audio.tags, "artist", "ARTIST", "TPE1", "\xa9ART")
                    if t:
                        title = t
                    if a:
                        artist = a
            except Exception:
                pass

        # Append extension label for non-mp3 files (optional UI hint)
        if ext != ".mp3" and ext:
            title = f"{title} [{ext[1:].upper()}]"

        dur = self.get_audio_duration(path)

        self.playlist.append(path)
        number_of_songs = len(self.tree.get_children())
        self.tree.insert("", "end", values=(str(number_of_songs + 1), title, artist, f"{dur//60:02}:{dur%60:02}"))
        self.renumber_tree()

    def add_folder(self):
        folder = filedialog.askdirectory(initialdir=self.last_opened_folder)
        if not folder:
            return

        #playlist.clear()
        #tree.delete(*tree.get_children())

        # Walk folder recursively and add supported files in a stable order
        for root_dir, dirs, files in os.walk(folder):
            dirs.sort()
            for file in sorted(files):
                if file.lower().endswith(self.SUPPORTED_EXTS):
                    path = os.path.join(root_dir, file)
                    self.add_song_to_list(path)

        # remember last opened folder
        self.last_opened_folder = folder

        # update numbers and persist playlist
        self.renumber_tree()
        with open(self.PLAYLIST_FILE, "w") as f:
            json.dump({"playlist": self.playlist}, f)

        if self.player:
            self.stop_song()

        # Select the first song if available
        if self.tree.get_children():
            first_item = self.tree.get_children()[0]
            self.tree.selection_set(first_item)
            self.tree.focus(first_item)
            self.tree.see(first_item)

    def add_songs(self):
        song_tmp = filedialog.askopenfilenames(
            title="Select Audio Files",
            initialdir=self.last_opened_folder,
            filetypes=[("Audio Files", "*.mp3 *.wav *.flac *.ogg *.aac *.m4a *.wma"),
                    ("All Files", "*.*")]
        )
        if not song_tmp:
            return
        # Remember the folder of the first selected file
        last_opened_folder = os.path.dirname(song_tmp[0])
        for file in sorted(song_tmp):
            if file.lower().endswith(self.SUPPORTED_EXTS):
                self.add_song_to_list(file)
        self.renumber_tree()
        json.dump({"playlist": self.playlist}, open(self.PLAYLIST_FILE, "w"))

    def clear_songs_list(self):
        if self.player:
            self.stop_song()
        self.playlist.clear(); self.tree.delete(*self.tree.get_children())
        json.dump({"playlist": self.playlist}, open(self.PLAYLIST_FILE, "w"))

    def load_saved_playlist(self):
        if not os.path.exists(self.PLAYLIST_FILE):
            return
        try:
            data = json.load(open(self.PLAYLIST_FILE))
            for path in data.get("playlist", []):
                if os.path.exists(path):
                    self.add_song_to_list(path)
        except Exception:
            pass

        json.dump({"playlist": self.playlist}, open(self.PLAYLIST_FILE, "w"))

        # 👇 Select the first song if available
        if self.tree.get_children():
            first_item = self.tree.get_children()[0]
            self.tree.selection_set(first_item)
            self.tree.focus(first_item)
            self.tree.see(first_item)

    def play_selected(self):
        sel = self.tree.selection()
        if sel:
            self.current_index = self.tree.index(sel[0])
            
        if self.paused and self.current_index_playing == self.current_index:
            self.pause_song()
            self.wait_for_playing_and_update()
            return
        
        if sel:
            self.index_to_play = self.current_index
            self.play_song()
            
    def play_song(self):
        try:
            if self.player and self.player.get_state() == vlc.State.Playing and self.current_index_playing == self.index_to_play:
                return
        except Exception:
            pass
        
        self.stop_song()
        self.clear_stop_mark()
        if self.index_to_play < 0:
            self.index_to_play = self.current_index
        self.current_index_playing = self.index_to_play
        song = self.playlist[self.current_index_playing]
        
        try:
            self.player = vlc.MediaPlayer(song)
            self.player.audio_set_volume(int(self.volume_slider.get()))
            self.player.play()
        except Exception as e:
            print(f"Error creating/playing media: {e}")
            self.player = None
            return
        
        try:
            audio = MP3(song)
        except Exception:
            pass

        self.current_song_length = self.get_audio_duration(song)
        self.progress_bar["maximum"] = self.current_song_length

        self.label_var.set(f"▶ Playing: {os.path.basename(song)}")
        self.wait_for_playing_and_update()
        self.check_song_end()
        self.mark_playing_item(self.current_index_playing)

    def pause_song(self):
        if self.player:
            try:
                (self.player.play() if self.paused else self.player.pause())
                self.paused = not self.paused

                if self.paused:
                    self.mark_pause_item(self.current_index_playing)
                    # Update label to show paused state
                    if 0 <= self.current_index_playing < len(self.playlist):
                        song = self.playlist[self.current_index_playing]
                        self.label_var.set(f"⏸ Paused: {os.path.basename(song)}")
                else:
                    self.mark_playing_item(self.current_index_playing)
                    # Update label to show playing state
                    if 0 <= self.current_index_playing < len(self.playlist):
                        song = self.playlist[self.current_index_playing]
                        self.label_var.set(f"▶ Playing: {os.path.basename(song)}")
                    self.wait_for_playing_and_update()
            except Exception as e:
                print(f"Error in pause_song: {e}")

    def mark_stopped_item(self, index):
        """Mark the row at `index` as stopped (■ prefix) but keep the same tag/colors."""
        children = self.tree.get_children()
        if not children:
            return
        for i, item in enumerate(children):
            vals = list(self.tree.item(item, "values"))
            if not vals or len(vals) < 2:
                continue
            if i == index:
                # remove playing marker if present
                if vals[1].startswith("▶ ") or vals[1].startswith("⏸ ") or vals[1].startswith("■ "):
                    vals[1] = vals[1][2:]
                # add stopped marker if not present
                if not vals[1].startswith("■ "):
                    vals[1] = "■ " + vals[1]
                    self.tree.item(item, values=vals)
                # keep the same visual tag so colors remain
                self.tree.item(item, tags=("playing",))
            else:
                # remove stopped marker from other rows
                if vals[1].startswith("▶ ") or vals[1].startswith("⏸ ") or vals[1].startswith("■ "):
                    vals[1] = vals[1][2:]
                    self.tree.item(item, values=vals)
                self.tree.item(item, tags=())

    def stop_song(self):
        self.paused = False
        if self.player:
            try:
                self.player.stop()
            except Exception as e:
                print(f"Error stopping player: {e}")
        self.progress_bar['value'] = 0
        # Show which song was stopped
        if 0 <= self.current_index_playing < len(self.playlist):
            song = self.playlist[self.current_index_playing]
            self.label_var.set(f"⏹ Stopped: {os.path.basename(song)}")
        else:
            self.label_var.set("⏹ Stopped")
        self.time_label.config(text="")
        # keep the same background/foreground for the last played item
        self.clear_playing_mark()
        if 0 <= self.current_index_playing < len(self.playlist):
            self.mark_stopped_item(self.current_index_playing)

    def skip(self, step):
        self.index_to_play = (self.index_to_play + step) % len(self.playlist)
        self.play_song()

    def update_progress(self):
        if self.player is not None and self.player.get_state() == vlc.State.Playing:
            pos = int(self.player.get_time() / 1000)
            self.progress_bar['value'] = pos
            #print("progress_bar value set to ", pos)

            minutes = pos // 60
            seconds = pos % 60
            total = self.current_song_length
            total_minutes = total // 60
            total_seconds = total % 60

            self.time_label.config(text=f"{minutes:02}:{seconds:02} / {total_minutes:02}:{total_seconds:02}")

            if pos < total:
                self.after(1000, self.update_progress)
        elif self.player and self.player.get_state() == vlc.State.Ended:
            self.progress_bar['value'] = 0
            self.time_label.config(text="")
            if not self.paused and self.current_index_playing < len(self.playlist) - 1:
                self.skip(1)

    def seek_progress(self,e):
        if self.player:
            # Click on the progressbar will get e.x that is the x coordinate inside progressbar graphic control
            # This is why we have to calcupate as percentage
            #print("seek_progress click at ", e.x)
            percent = e.x / self.progress_bar.winfo_width()
            #print("percent is ", percent)
            set_time = int(self.current_song_length * percent) * 1000
            #print("Set song time to ", set_time)
            self.player.set_time(set_time)
            self.update_progress()

    def wait_for_playing_and_update(self):
        if self.player is not None and self.player.get_state() == vlc.State.Playing:
            self.update_progress()
        else:
            self.after(200, self.wait_for_playing_and_update)  # Retry in 200 ms

    def check_song_end(self):
        if self.player is not None:
            state = self.player.get_state()
            if state == vlc.State.Ended:
                self.progress_bar['value'] = 0
                self.time_label.config(text="")
                if not self.paused:
                    if self.current_index_playing < len(self.playlist) - 1:
                        self.skip(1)
                    else:
                        # Last track finished — stop playback and mark item stopped.
                        try:
                            self.stop_song()
                        except Exception:
                            pass
                        if 0 <= self.current_index_playing < len(self.playlist):
                            try:
                                self.mark_stopped_item(self.current_index_playing)
                            except Exception:
                                pass
                return
        self.after(1000, self.check_song_end)

    def delete_current_song(self):
        sel = self.tree.selection()
        if not sel:
            return
        
        # Create a mapping of indices to tree items
        index_to_item = {self.tree.index(item): item for item in sel}
        
        # Get indices for all selected items, sorted in descending order
        indices = sorted(index_to_item.keys(), reverse=True)
        
        # Check if any of the deleted songs is currently playing
        was_playing_deleted = False
        if self.player is not None and self.current_index_playing in indices:
            was_playing_deleted = True
            self.stop_song()
            self.player = None
        
        # Delete from highest index to lowest (to avoid index shifting issues)
        for idx in indices:
            if 0 <= idx < len(self.playlist):
                del self.playlist[idx]
                self.tree.delete(index_to_item[idx])  # Delete the corresponding item
        
        self.renumber_tree()
        
        # Adjust playing index for any deleted items that were before current_index_playing
        if self.player is not None:
            num_deleted_before = sum(1 for idx in indices if idx < self.current_index_playing)
            self.current_index_playing -= num_deleted_before
        
        if self.playlist:
            # Select next item: same index as lowest deleted if it exists, otherwise the new last item
            new_index = indices[-1] if indices[-1] < len(self.playlist) else len(self.playlist) - 1
            self.current_index = new_index
            if was_playing_deleted:
                self.current_index_playing = self.current_index
            item = self.tree.get_children()[self.current_index]
            self.tree.selection_set(item)
            self.tree.focus(item)
            self.tree.see(item)
        else:
            self.current_index = 0
            self.current_index_playing = 0

        json.dump({"playlist": self.playlist}, open(self.PLAYLIST_FILE, "w"))

    def save_playlist_as(self):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON Playlist", "*.json"), ("All Files", "*.*")],
            title="Save Playlist As"
        )
        if file_path:
            with open(file_path, "w") as f:
                json.dump({"playlist": self.playlist}, f)
            # remember this file in recent list
            self.add_to_recent(file_path)

    def load_playlist_from_file(self):
        file_path = filedialog.askopenfilename(
            defaultextension=".json",
            filetypes=[("JSON Playlist", "*.json"), ("All Files", "*.*")],
            title="Load Playlist"
        )
        if file_path:
            # stop any currently playing audio before we wipe the list
            if self.player:
                self.stop_song()
            # clear the now-playing label since no track is active yet
            self.label_var.set("")
            try:
                with open(file_path, "r") as f:
                    data = json.load(f)
                    self.playlist.clear()
                    self.tree.delete(*self.tree.get_children())
                    for path in data.get("playlist", []):
                        self.add_song_to_list(path)
            except Exception as e:
                ttk.messagebox.showerror("Error", f"Failed to load playlist:\n{e}")

            # Select the first song if available
            if self.tree.get_children():
                first_item = self.tree.get_children()[0]
                self.tree.selection_set(first_item)
                self.tree.focus(first_item)
                self.tree.see(first_item)
                # update label with selected file name (not playing yet)
                #idx = 0
                #if 0 <= idx < len(self.playlist):
                #    self.label_var.set(f"▶ {os.path.basename(self.playlist[idx])}")
            # remember file in recent
            self.add_to_recent(file_path)

    # --- recent playlist helpers ---
    def load_recent_playlists(self):
        """Load list of recent playlist paths from disk and refresh menu."""
        try:
            if os.path.exists(self.RECENT_FILE):
                data = json.load(open(self.RECENT_FILE))
                self.recent_playlists = [p for p in data.get("recent", [])]
        except Exception:
            self.recent_playlists = []
        self.refresh_recent_menu()

    def save_recent_playlists(self):
        """Persist current recent list to disk."""
        try:
            with open(self.RECENT_FILE, "w") as f:
                json.dump({"recent": self.recent_playlists}, f)
        except Exception:
            pass

    def add_to_recent(self, path):
        """Add a file path to recent list (move to front, dedupe, cap length).
        Automatically saves and refreshes menu."""
        if not path:
            return
        path = os.path.abspath(path)
        if path in self.recent_playlists:
            self.recent_playlists.remove(path)
        self.recent_playlists.insert(0, path)
        if len(self.recent_playlists) > 10:
            self.recent_playlists = self.recent_playlists[:10]
        self.save_recent_playlists()
        self.refresh_recent_menu()

    def refresh_recent_menu(self):
        """Rebuild the recent-playlists submenu according to current list."""
        # menu may not exist during early init
        try:
            self.recent_menu.delete(0, tk.END)
        except Exception:
            return
        if not self.recent_playlists:
            self.recent_menu.add_command(label="(empty)", state="disabled")
        else:
            for p in self.recent_playlists:
                display = os.path.basename(p) or p
                self.recent_menu.add_command(label=display, command=lambda p=p: self.load_recent(p))
        # always allow clearing (even when empty)
        self.recent_menu.add_separator()
        self.recent_menu.add_command(label="Clear recent", command=self.clear_recent)

    def load_recent(self, path):
        """Load a playlist from path (called by recent menu)."""
        if not os.path.exists(path):
            messagebox.showerror("Error", f"Playlist not found:\n{path}")
            # remove from list
            try:
                self.recent_playlists.remove(path)
                self.save_recent_playlists()
                self.refresh_recent_menu()
            except ValueError:
                pass
            return
        # make sure playback stops before clearing
        if self.player:
            self.stop_song()
        # clear label as well
        self.label_var.set("")
        try:
            with open(path, "r") as f:
                data = json.load(f)
                self.playlist.clear()
                self.tree.delete(*self.tree.get_children())
                for item in data.get("playlist", []):
                    self.add_song_to_list(item)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load playlist:\n{e}")
            return
        if self.tree.get_children():
            first_item = self.tree.get_children()[0]
            self.tree.selection_set(first_item)
            self.tree.focus(first_item)
            self.tree.see(first_item)
            # display name of first track in label
            #if self.playlist:
            #    self.label_var.set(f"▶ {os.path.basename(self.playlist[0])}")
        self.add_to_recent(path)

    def clear_recent(self):
        """Remove all entries from the recent list and update storage/menu."""
        self.recent_playlists = []
        try:
            os.remove(self.RECENT_FILE)
        except Exception:
            pass
        self.refresh_recent_menu()

    def move_song(self, old_index, new_index):
        """Move song in playlist and reorder the Treeview. Keep selection/play indexes in sync."""
        print(f"move_song from {old_index} to {new_index}")
        if old_index == new_index:
            return
        if not (0 <= old_index < len(self.playlist)) or not (0 <= new_index < len(self.playlist)):
            return

        # move in playlist
        item = self.playlist.pop(old_index)
        self.playlist.insert(new_index, item)

        # capture current tree values and reorder
        values = [list(self.tree.item(c, "values")) for c in self.tree.get_children()]
        moved_vals = values.pop(old_index)
        values.insert(new_index, moved_vals)

        # rebuild tree from reordered values
        self.tree.delete(*self.tree.get_children())
        for i, vals in enumerate(values, start=1):
            vals[0] = str(i)
            self.tree.insert("", "end", values=vals)

        # adjust selection index
        if self.current_index == old_index:
            self.current_index = new_index
        elif old_index < self.current_index <= new_index:
            self.current_index -= 1
        elif new_index <= self.current_index < old_index:
            self.current_index += 1

        # adjust playing index similarly
        if self.current_index_playing == old_index:
            self.current_index_playing = new_index
        elif old_index < self.current_index_playing <= new_index:
            self.current_index_playing -= 1
        elif new_index <= self.current_index_playing < old_index:
            self.current_index_playing += 1

        self.renumber_tree()

        # restore selection and focus
        if self.tree.get_children():
            #sel_index = max(0, min(current_index, len(tree.get_children()) - 1))
            item_id = self.tree.get_children()[new_index]
            self.tree.selection_set(item_id)
            self.tree.focus(item_id)
            self.tree.see(item_id)

        # update visual markers
        if self.player is not None:
            # there's an active player; mark playing item
            if 0 <= self.current_index_playing < len(self.playlist):
                self.mark_playing_item(self.current_index_playing)
            else:
                self.clear_playing_mark()
        else:
            # no active player: keep stopped marker if applicable
            self.clear_stop_mark()
            if 0 <= self.current_index_playing < len(self.playlist):
                self.mark_stopped_item(self.current_index_playing)

        # persist playlist
        with open(self.PLAYLIST_FILE, "w") as f:
            json.dump({"playlist": self.playlist}, f)


    def move_selected_up(self):
        print("move_selected_up called")
        sel = self.tree.selection()
        if not sel:
            return
        children = list(self.tree.get_children())
        try:
            idx = children.index(sel[0])
        except ValueError:
            return
        if idx > 0:
            self.move_song(idx, idx - 1)

    def move_selected_down(self):
        print("move_selected_down called")
        sel = self.tree.selection()
        if not sel:
            return
        children = list(self.tree.get_children())
        try:
            idx = children.index(sel[0])
        except ValueError:
            return
        if idx < len(self.playlist) - 1:
            self.move_song(idx, idx + 1)

    # === Context Menu ===
    def show_context_menu(self, event):
        # Select the row under mouse
        row_id = self.tree.identify_row(event.y)
        if row_id:
            self.tree.selection_set(row_id)
            self.context_menu.tk_popup(event.x_root, event.y_root)

    def split_dnd_files(self, data: str) -> list[str]:
        """
        Windows/macOS/Linux: tkinterdnd2 gives a single string.
        Paths with spaces may be wrapped in { }.
        Example: "{/path/with space/a.mp3} /other/b.wav"
        """
        paths = []
        buf = ""
        in_brace = False

        for ch in data:
            if ch == "{":
                in_brace = True
                buf = ""
            elif ch == "}":
                in_brace = False
                if buf:
                    paths.append(buf)
                    buf = ""
            elif ch == " " and not in_brace:
                if buf:
                    paths.append(buf)
                    buf = ""
            else:
                buf += ch

        if buf:
            paths.append(buf)

        # normalize
        out = []
        for p in paths:
            p = p.strip()
            if not p:
                continue
            # On macOS, it may come as file:///... sometimes; handle that
            if p.startswith("file://"):
                # best-effort decode
                p = p.replace("file://", "", 1)
            out.append(p)
        return out

    def handle_drop1(self, event):
        """Handle drag and drop of files onto the treeview."""
        # Some events (e.g. stray virtual events) may not include a ``data`` field.
        # Ensure we don't crash in that case.
        # event.data is the dropped files string
        
        if not hasattr(event, "data") or event.data is None:
            return

        # Extract file paths from the drop data (Windows/Linux use curly braces, macOS may vary)
        files = event.data
        
        # Parse the dropped files - tkinterdnd2 returns paths either quoted or braced
        dropped_paths = []
        if isinstance(files, str):
            # Split by spaces and remove braces/quotes
            import re
            # Match paths - they can be quoted, braced, or plain
            # Pattern: matches {/path/to/file} or "/path/to/file" or /path/to/file
            paths = re.findall(r'\{([^}]+)\}|"([^"]+)"|(\S+)', files)
            for match in paths:
                path = match[0] or match[1] or match[2]
                if path:
                    dropped_paths.append(path.strip())
        
        added_count = 0
        for path in dropped_paths:
            path = path.strip()
            if not path:
                continue
            
            # Check if it's a file or directory
            if os.path.isfile(path):
                # Check if it's a supported audio file
                if path.lower().endswith(self.SUPPORTED_EXTS):
                    self.add_song_to_list(path)
                    added_count += 1
            elif os.path.isdir(path):
                # If it's a directory, walk it recursively like the add_folder function
                for root_dir, dirs, files_in_dir in os.walk(path):
                    dirs.sort()
                    for file in sorted(files_in_dir):
                        if file.lower().endswith(self.SUPPORTED_EXTS):
                            file_path = os.path.join(root_dir, file)
                            self.add_song_to_list(file_path)
                            added_count += 1
    
        # Update the display and save playlist if any files were added
        if added_count > 0:
            self.renumber_tree()

            with open(self.PLAYLIST_FILE, "w") as f:
                json.dump({"playlist": self.playlist}, f)
            
            # Ensure first item is selected if not already
            if self.tree.get_children() and not self.tree.selection():
                first_item = self.tree.get_children()[0]
                self.tree.selection_set(first_item)
                self.tree.focus(first_item)
                self.tree.see(first_item)
    
        return event.action  # Return action to complete the drop

    def show_about(self):
        """Show the About dialog with version information."""
        about_text = f"""🎵 Audio Player v{VERSION}

A full-featured, cross-platform desktop audio player
built with Tkinter and VLC.

Author: Adrian Crimu
License: MIT License
GitHub: https://github.com/acrimu/AudioPlayer

Supported formats: MP3, WAV, FLAC, OGG, AAC, M4A, WMA

Python: {sys.version.split()[0]}
Platform: {platform.system()} {platform.release()}"""

        messagebox.showinfo("About Audio Player", about_text)


if __name__ == "__main__":
    try:
        app = App()
        app.mainloop()
    except Exception as e:
        messagebox.showerror("Error", f"{e}\n\nPython: {sys.version}")
        raise