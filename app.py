#!/usr/bin/env python3
"""
MP3 Studio - Metadata editor, album art fetcher, lyrics fetcher, and EQ processor
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import requests
import os
import threading
from pathlib import Path
import yt_dlp
from mutagen.mp3 import MP3
from mutagen.id3 import (
    ID3, TIT2, TPE1, TALB, TYER, TCON,
    USLT, APIC, ID3NoHeaderError
)
from PIL import Image
import io
import numpy as np
from scipy import signal as scipy_signal
from pydub import AudioSegment

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class MP3Studio(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("MP3 Studio")
        self.geometry("1200x820")
        self.minsize(1000, 700)

        self.files: list[str] = []
        self.current_file: str | None = None
        self.album_art_data: bytes | None = None

        self._build_ui()

    # ─────────────────────────── UI BUILD ────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.left = ctk.CTkFrame(self, width=240, corner_radius=0)
        self.left.grid(row=0, column=0, sticky="nsew")
        self.left.grid_propagate(False)

        self.right = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.right.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        self.right.grid_rowconfigure(1, weight=1)
        self.right.grid_columnconfigure(0, weight=1)

        self._build_sidebar()
        self._build_toolbar()
        self._build_tabs()

    def _build_sidebar(self):
        ctk.CTkLabel(
            self.left, text="MP3 Studio",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(20, 10))

        ctk.CTkButton(
            self.left, text="＋  Add MP3 Files",
            command=self.add_files, height=38
        ).pack(fill="x", padx=12, pady=(0, 8))

        ctk.CTkLabel(
            self.left, text="Queue",
            font=ctk.CTkFont(size=11), text_color="gray"
        ).pack(anchor="w", padx=14)

        self.listbox = tk.Listbox(
            self.left,
            bg="#1e1e1e", fg="#e0e0e0",
            selectbackground="#1f538d",
            relief="flat", borderwidth=0,
            font=("SF Pro Display", 11) if os.path.exists("/System/Library/Fonts/SFNSDisplay.ttf")
            else ("Arial", 11),
            activestyle="none",
        )
        self.listbox.pack(fill="both", expand=True, padx=10, pady=6)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        ctk.CTkButton(
            self.left, text="Remove Selected",
            command=self.remove_file,
            fg_color="#3a3a3a", hover_color="#c0392b",
            height=32
        ).pack(fill="x", padx=12, pady=(0, 14))

    def _build_toolbar(self):
        bar = ctk.CTkFrame(self.right, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        bar.grid_columnconfigure(0, weight=1)

        self.file_label = ctk.CTkLabel(
            bar, text="No file selected",
            font=ctk.CTkFont(size=15, weight="bold")
        )
        self.file_label.grid(row=0, column=0, sticky="w")

        btns = ctk.CTkFrame(bar, fg_color="transparent")
        btns.grid(row=0, column=1, sticky="e")

        ctk.CTkButton(
            btns, text="Auto Fetch All", command=self.auto_fetch,
            width=130, height=34
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            btns, text="Save Metadata", command=self.save_metadata,
            width=120, height=34, fg_color="#27ae60", hover_color="#2ecc71"
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            btns, text="Export MP3", command=self.export_mp3,
            width=110, height=34, fg_color="#8e44ad", hover_color="#9b59b6"
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            btns, text="Bulk Export", command=self.bulk_export,
            width=110, height=34, fg_color="#6d4c41", hover_color="#8d6e63"
        ).pack(side="left", padx=4)

    def _build_tabs(self):
        self.tabs = ctk.CTkTabview(self.right)
        self.tabs.grid(row=1, column=0, sticky="nsew")

        self.tabs.add("Metadata")
        self.tabs.add("Lyrics")
        self.tabs.add("Audio EQ")
        self.tabs.add("Download")

        self._build_metadata_tab()
        self._build_lyrics_tab()
        self._build_eq_tab()
        self._build_download_tab()

    def _build_metadata_tab(self):
        tab = self.tabs.tab("Metadata")
        tab.grid_columnconfigure(1, weight=1)

        # ── Album art column ──
        art_col = ctk.CTkFrame(tab)
        art_col.grid(row=0, column=0, rowspan=7, padx=(10, 20), pady=10, sticky="n")

        self.art_label = ctk.CTkLabel(art_col, text="", width=190, height=190)
        self.art_label.pack(padx=10, pady=(10, 6))
        self._show_default_art()

        ctk.CTkButton(
            art_col, text="Upload Art", command=self.upload_art,
            width=170, height=32
        ).pack(pady=3)
        ctk.CTkButton(
            art_col, text="Fetch from iTunes", command=self.fetch_art_only,
            width=170, height=32, fg_color="#2c3e50", hover_color="#34495e"
        ).pack(pady=(3, 12))

        # ── Fields ──
        fields_cfg = [
            ("Title",  "title"),
            ("Artist", "artist"),
            ("Album",  "album"),
            ("Year",   "year"),
            ("Genre",  "genre"),
        ]
        self.fields: dict[str, ctk.CTkEntry] = {}
        for i, (lbl, key) in enumerate(fields_cfg):
            ctk.CTkLabel(tab, text=lbl, font=ctk.CTkFont(weight="bold"), width=60).grid(
                row=i, column=1, sticky="w", padx=(0, 8), pady=8
            )
            entry = ctk.CTkEntry(tab, placeholder_text=f"Enter {lbl.lower()}…", height=36)
            entry.grid(row=i, column=2, sticky="ew", padx=(0, 12), pady=8)
            self.fields[key] = entry

        tab.grid_columnconfigure(2, weight=1)

    def _build_lyrics_tab(self):
        tab = self.tabs.tab("Lyrics")
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        bar = ctk.CTkFrame(tab, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=10, pady=10)

        ctk.CTkButton(
            bar, text="Fetch Lyrics", command=self.fetch_lyrics_only,
            width=130, height=34
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            bar, text="Clear",
            command=lambda: self.lyrics_box.delete("1.0", "end"),
            width=80, height=34, fg_color="#555", hover_color="#7f8c8d"
        ).pack(side="left")

        self.lyrics_box = ctk.CTkTextbox(
            tab, font=ctk.CTkFont(size=13), wrap="word"
        )
        self.lyrics_box.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

    # 5-band EQ presets: (bass, low_mid, mid, high_mid, treble) gains in dB.
    # "Flat" zeroes everything; keys must match self.eq_vars / band_ranges.
    EQ_PRESETS: dict[str, dict[str, float]] = {
        "Flat":         {"bass": 0,    "low_mid": 0,    "mid": 0,    "high_mid": 0,   "treble": 0},
        "Bass Boost":   {"bass": 7.0,  "low_mid": 3.5,  "mid": 0,    "high_mid": 0,   "treble": 1.0},
        "Treble Boost": {"bass": 0,    "low_mid": 0,    "mid": 0,    "high_mid": 4.0, "treble": 7.0},
        "Vocal Boost":  {"bass": -2.0, "low_mid": 1.0,  "mid": 5.0,  "high_mid": 3.0, "treble": 0},
        "Loudness":     {"bass": 6.0,  "low_mid": 1.5,  "mid": -1.0, "high_mid": 2.0, "treble": 5.0},
        "Podcast":      {"bass": -4.0, "low_mid": 1.0,  "mid": 4.0,  "high_mid": 2.5, "treble": -1.0},
        "Acoustic":     {"bass": 3.0,  "low_mid": 1.0,  "mid": 1.5,  "high_mid": 2.5, "treble": 3.5},
    }

    def _build_eq_tab(self):
        tab = self.tabs.tab("Audio EQ")
        tab.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            tab, text="5-Band Equalizer",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=(14, 2))
        ctk.CTkLabel(
            tab, text="Applied on Export MP3 — does not modify the source file",
            text_color="gray", font=ctk.CTkFont(size=11)
        ).pack()

        # ── Preset selector ──
        preset_row = ctk.CTkFrame(tab, fg_color="transparent")
        preset_row.pack(pady=(8, 0))
        ctk.CTkLabel(
            preset_row, text="Preset:", font=ctk.CTkFont(size=12, weight="bold")
        ).pack(side="left", padx=(0, 8))
        self.eq_preset_menu = ctk.CTkOptionMenu(
            preset_row,
            values=list(self.EQ_PRESETS.keys()),
            command=self._apply_eq_preset,
            width=160,
        )
        self.eq_preset_menu.set("Flat")
        self.eq_preset_menu.pack(side="left")

        bands_frame = ctk.CTkFrame(tab)
        bands_frame.pack(fill="x", padx=20, pady=16)

        bands = [
            ("Bass",     "bass",     80,   200),
            ("Low Mid",  "low_mid",  200,  800),
            ("Mid",      "mid",      800,  3000),
            ("High Mid", "high_mid", 3000, 6000),
            ("Treble",   "treble",   6000, 16000),
        ]

        self.eq_vars: dict[str, tk.DoubleVar] = {}
        self.eq_value_labels: dict[str, ctk.CTkLabel] = {}

        for i, (label, key, lo, hi) in enumerate(bands):
            col = ctk.CTkFrame(bands_frame, fg_color="transparent")
            col.grid(row=0, column=i, padx=18, pady=14)
            bands_frame.grid_columnconfigure(i, weight=1)

            ctk.CTkLabel(
                col, text=label,
                font=ctk.CTkFont(size=12, weight="bold")
            ).pack()

            var = tk.DoubleVar(value=0.0)
            self.eq_vars[key] = var

            val_lbl = ctk.CTkLabel(col, text=" 0.0 dB", width=60, font=ctk.CTkFont(size=11))
            val_lbl.pack()
            self.eq_value_labels[key] = val_lbl

            def _make_cb(lbl):
                def cb(v):
                    lbl.configure(text=f"{float(v):+.1f} dB")
                return cb

            ctk.CTkSlider(
                col, from_=-12, to=12, variable=var,
                orientation="vertical", height=160,
                command=_make_cb(val_lbl)
            ).pack(pady=6)

            ctk.CTkLabel(
                col, text=f"{lo}–{hi} Hz",
                text_color="gray", font=ctk.CTkFont(size=10)
            ).pack()

        # Effects row
        fx = ctk.CTkFrame(tab)
        fx.pack(fill="x", padx=20, pady=8)

        ctk.CTkLabel(
            fx, text="Extra Effects",
            font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w", padx=14, pady=(10, 6))

        row = ctk.CTkFrame(fx, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(0, 8))

        self.normalize_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(row, text="Normalize Volume", variable=self.normalize_var).pack(side="left", padx=12)

        self.stereo_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(row, text="Stereo Enhance", variable=self.stereo_var).pack(side="left", padx=12)

        speed_row = ctk.CTkFrame(fx, fg_color="transparent")
        speed_row.pack(fill="x", padx=14, pady=(0, 12))

        ctk.CTkLabel(speed_row, text="Playback Speed:").pack(side="left")
        self.speed_lbl = ctk.CTkLabel(speed_row, text="1.0×", width=42)
        self.speed_lbl.pack(side="left", padx=6)

        self.speed_var = tk.DoubleVar(value=1.0)
        ctk.CTkSlider(
            speed_row, from_=0.5, to=2.0, variable=self.speed_var,
            width=200,
            command=lambda v: self.speed_lbl.configure(text=f"{float(v):.1f}×")
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            tab, text="Reset All EQ & Effects",
            command=self._reset_eq,
            fg_color="#555", hover_color="#7f8c8d", width=180
        ).pack(pady=12)

    def _build_download_tab(self):
        tab = self.tabs.tab("Download")
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(4, weight=1)   # treeview expands

        # ── Header ──
        hdr = ctk.CTkFrame(tab, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=20, pady=(14, 4))
        hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hdr, text="Bulk Music Downloader",
                     font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(hdr,
                     text="YouTube • SoundCloud • 1000+ sites  |  One URL per line  |  Playlist URLs auto-expanded",
                     text_color="gray", font=ctk.CTkFont(size=11)).grid(row=1, column=0, sticky="w")

        # ── URL input area ──
        url_area = ctk.CTkFrame(tab)
        url_area.grid(row=1, column=0, sticky="ew", padx=20, pady=(6, 6))
        url_area.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(url_area, text="URLs  (one per line, playlist links OK):",
                     font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", padx=10, pady=(8, 2))

        self.dl_url_box = ctk.CTkTextbox(url_area, height=88, font=ctk.CTkFont(size=12))
        self.dl_url_box.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))

        btn_col = ctk.CTkFrame(url_area, fg_color="transparent")
        btn_col.grid(row=1, column=1, padx=(4, 10), pady=(0, 8), sticky="n")
        ctk.CTkButton(btn_col, text="Paste", width=76, height=32,
                      fg_color="#3a3a3a", hover_color="#555",
                      command=self._paste_url).pack(pady=(0, 4))
        ctk.CTkButton(btn_col, text="Clear", width=76, height=32,
                      fg_color="#3a3a3a", hover_color="#c0392b",
                      command=lambda: self.dl_url_box.delete("1.0", "end")).pack()

        # ── Options row ──
        opts = ctk.CTkFrame(tab)
        opts.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 6))

        ctk.CTkLabel(opts, text="Save to:", font=ctk.CTkFont(weight="bold")).pack(
            side="left", padx=(12, 4), pady=8)
        self.dl_dir_var = tk.StringVar(value=str(Path.home() / "Downloads"))
        ctk.CTkLabel(opts, textvariable=self.dl_dir_var,
                     text_color="#aaa", font=ctk.CTkFont(size=11)).pack(
            side="left", padx=(0, 4), pady=8)
        ctk.CTkButton(opts, text="Browse", width=70, height=30,
                      fg_color="#3a3a3a", hover_color="#555",
                      command=self._browse_dl_dir).pack(side="left", padx=(0, 14), pady=8)

        self.dl_auto_tag_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(opts, text="Auto-tag metadata + art + lyrics",
                        variable=self.dl_auto_tag_var).pack(side="left", padx=8, pady=8)

        self.dl_add_queue_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(opts, text="Add to queue",
                        variable=self.dl_add_queue_var).pack(side="left", padx=8, pady=8)

        self.dl_button = ctk.CTkButton(
            opts, text="⬇  Download All", height=34,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#1f538d", hover_color="#2563a8",
            command=self._start_download, width=160)
        self.dl_button.pack(side="right", padx=12, pady=8)

        # ── Progress + status ──
        prog_frame = ctk.CTkFrame(tab, fg_color="transparent")
        prog_frame.grid(row=3, column=0, sticky="ew", padx=20, pady=(2, 2))
        prog_frame.grid_columnconfigure(0, weight=1)

        self.dl_progress = ctk.CTkProgressBar(prog_frame, height=8)
        self.dl_progress.grid(row=0, column=0, sticky="ew", pady=(0, 2))
        self.dl_progress.set(0)

        self.dl_status_label = ctk.CTkLabel(prog_frame, text="Ready", text_color="gray",
                                            font=ctk.CTkFont(size=11))
        self.dl_status_label.grid(row=1, column=0, sticky="w")

        # ── Download queue treeview ──
        tree_frame = ctk.CTkFrame(tab)
        tree_frame.grid(row=4, column=0, sticky="nsew", padx=20, pady=(4, 4))
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("DL.Treeview",
                        background="#1e1e1e", foreground="#e0e0e0",
                        fieldbackground="#1e1e1e", rowheight=24,
                        borderwidth=0, relief="flat")
        style.configure("DL.Treeview.Heading",
                        background="#2a2a2a", foreground="#aaaaaa",
                        relief="flat", borderwidth=0)
        style.map("DL.Treeview",
                  background=[("selected", "#1f538d")],
                  foreground=[("selected", "#ffffff")])
        style.configure("DL.Treeview.Item", padding=(4, 0))

        self.dl_tree = ttk.Treeview(
            tree_frame,
            columns=("title", "source", "status"),
            show="headings",
            style="DL.Treeview",
            selectmode="extended",
        )
        self.dl_tree.heading("title",  text="Title")
        self.dl_tree.heading("source", text="Source")
        self.dl_tree.heading("status", text="Status")
        self.dl_tree.column("title",  width=380, stretch=True)
        self.dl_tree.column("source", width=120, stretch=False)
        self.dl_tree.column("status", width=180, stretch=False)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical",   command=self.dl_tree.yview)
        self.dl_tree.configure(yscrollcommand=vsb.set)
        self.dl_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        # tag colours for status
        self.dl_tree.tag_configure("done",       foreground="#2ecc71")
        self.dl_tree.tag_configure("error",      foreground="#e74c3c")
        self.dl_tree.tag_configure("tagging",    foreground="#f39c12")
        self.dl_tree.tag_configure("active",     foreground="#3498db")
        self.dl_tree.tag_configure("queued",     foreground="#888888")

        # Log
        ctk.CTkLabel(tab, text="Log", font=ctk.CTkFont(weight="bold")).grid(
            row=5, column=0, sticky="w", padx=22, pady=(4, 0))
        self.dl_log = ctk.CTkTextbox(tab, height=90, font=ctk.CTkFont(size=11))
        self.dl_log.grid(row=6, column=0, sticky="ew", padx=20, pady=(2, 12))

    # ─────────────────────────── ART HELPERS ────────────────────────────

    def _show_default_art(self):
        img = Image.new("RGB", (190, 190), (30, 30, 40))
        cimg = ctk.CTkImage(img, size=(190, 190))
        self.art_label.configure(image=cimg, text="No Art")
        self.art_label._image = cimg

    def _show_art(self, data: bytes):
        try:
            img = Image.open(io.BytesIO(data)).convert("RGB").resize((190, 190), Image.LANCZOS)
            cimg = ctk.CTkImage(img, size=(190, 190))
            self.art_label.configure(image=cimg, text="")
            self.art_label._image = cimg
        except Exception:
            self._show_default_art()

    # ─────────────────────────── FILE OPS ────────────────────────────

    def add_files(self):
        paths = filedialog.askopenfilenames(
            title="Select MP3 files",
            filetypes=[("MP3", "*.mp3"), ("All files", "*.*")]
        )
        for p in paths:
            if p not in self.files:
                self.files.append(p)
                self.listbox.insert("end", Path(p).name)

    def remove_file(self):
        sel = self.listbox.curselection()
        if sel:
            idx = sel[0]
            self.files.pop(idx)
            self.listbox.delete(idx)
            self.current_file = None
            self.file_label.configure(text="No file selected")

    def _on_select(self, _event=None):
        sel = self.listbox.curselection()
        if sel:
            self.current_file = self.files[sel[0]]
            self._load_metadata()

    def _load_metadata(self):
        if not self.current_file:
            return

        self.file_label.configure(text=Path(self.current_file).name)

        try:
            audio = MP3(self.current_file, ID3=ID3)
            tags = audio.tags or {}
        except Exception:
            tags = {}

        def tag_text(tag_id, fallback=""):
            t = tags.get(tag_id)
            return str(t.text[0]) if t and hasattr(t, "text") else fallback

        stem = Path(self.current_file).stem
        parts = stem.split(" - ", 1)
        default_title = parts[1] if len(parts) > 1 else stem
        default_artist = parts[0] if len(parts) > 1 else ""

        for e in self.fields.values():
            e.delete(0, "end")

        self.fields["title"].insert(0, tag_text("TIT2", default_title))
        self.fields["artist"].insert(0, tag_text("TPE1", default_artist))
        self.fields["album"].insert(0, tag_text("TALB"))
        self.fields["year"].insert(0, tag_text("TYER"))
        self.fields["genre"].insert(0, tag_text("TCON"))

        self.lyrics_box.delete("1.0", "end")
        for key in ("USLT::eng", "USLT::'eng'", "USLT::"):
            if key in tags:
                self.lyrics_box.insert("1.0", tags[key].text)
                break

        apic = tags.get("APIC:") or next(
            (v for k, v in tags.items() if k.startswith("APIC")), None
        )
        if apic:
            self.album_art_data = apic.data
            self._show_art(apic.data)
        else:
            self.album_art_data = None
            self._show_default_art()

    # ─────────────────────────── FETCH ────────────────────────────

    def auto_fetch(self):
        if not self.current_file:
            messagebox.showwarning("No file", "Select a file first.")
            return
        artist = self.fields["artist"].get().strip()
        title = self.fields["title"].get().strip()
        if not (artist and title):
            messagebox.showwarning("Missing info", "Fill in Artist and Title first.")
            return
        threading.Thread(target=self._fetch_all, args=(artist, title), daemon=True).start()

    def _fetch_all(self, artist: str, title: str):
        self._fetch_itunes(artist, title)
        self._fetch_lyrics(artist, title)

    def _fetch_itunes(self, artist: str, title: str):
        try:
            q = requests.utils.quote(f"{artist} {title}")
            r = requests.get(
                f"https://itunes.apple.com/search?term={q}&media=music&limit=1",
                timeout=10
            )
            data = r.json()
            if not data.get("resultCount"):
                return
            res = data["results"][0]

            self.after(0, lambda: self._set_field("album", res.get("collectionName", "")))
            self.after(0, lambda: self._set_field("year", res.get("releaseDate", "")[:4]))
            self.after(0, lambda: self._set_field("genre", res.get("primaryGenreName", "")))

            art_url = res.get("artworkUrl100", "").replace("100x100bb", "600x600bb")
            if art_url:
                art_data = requests.get(art_url, timeout=10).content
                self.album_art_data = art_data
                self.after(0, lambda: self._show_art(art_data))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("iTunes Error", str(e)))

    def _fetch_lyrics(self, artist: str, title: str):
        try:
            a = requests.utils.quote(artist)
            t = requests.utils.quote(title)
            r = requests.get(f"https://api.lyrics.ovh/v1/{a}/{t}", timeout=12)
            if r.status_code == 200:
                lyrics = r.json().get("lyrics", "").strip()
                if lyrics:
                    self.after(0, lambda: (
                        self.lyrics_box.delete("1.0", "end"),
                        self.lyrics_box.insert("1.0", lyrics)
                    ))
        except Exception:
            pass

    def fetch_art_only(self):
        artist = self.fields["artist"].get().strip()
        title = self.fields["title"].get().strip()
        if artist and title:
            threading.Thread(target=self._fetch_itunes, args=(artist, title), daemon=True).start()
        else:
            messagebox.showwarning("Missing info", "Enter Artist and Title first.")

    def fetch_lyrics_only(self):
        artist = self.fields["artist"].get().strip()
        title = self.fields["title"].get().strip()
        if artist and title:
            threading.Thread(target=self._fetch_lyrics, args=(artist, title), daemon=True).start()
        else:
            messagebox.showwarning("Missing info", "Enter Artist and Title first.")

    def upload_art(self):
        path = filedialog.askopenfilename(
            title="Select album art",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.webp")]
        )
        if path:
            with open(path, "rb") as f:
                self.album_art_data = f.read()
            self._show_art(self.album_art_data)

    # ─────────────────────────── SAVE / EXPORT ────────────────────────────

    def save_metadata(self):
        if not self.current_file:
            messagebox.showwarning("No file", "Select a file first.")
            return
        self._write_tags(self.current_file)
        messagebox.showinfo("Saved", "Metadata saved to file.")

    def _write_tags(self, path: str):
        try:
            try:
                tags = ID3(path)
            except ID3NoHeaderError:
                tags = ID3()

            tags["TIT2"] = TIT2(encoding=3, text=self.fields["title"].get())
            tags["TPE1"] = TPE1(encoding=3, text=self.fields["artist"].get())
            tags["TALB"] = TALB(encoding=3, text=self.fields["album"].get())
            tags["TYER"] = TYER(encoding=3, text=self.fields["year"].get())
            tags["TCON"] = TCON(encoding=3, text=self.fields["genre"].get())

            lyrics = self.lyrics_box.get("1.0", "end").strip()
            if lyrics:
                tags["USLT::eng"] = USLT(encoding=3, lang="eng", desc="", text=lyrics)

            if self.album_art_data:
                mime = "image/png" if self.album_art_data[:4] == b"\x89PNG" else "image/jpeg"
                tags["APIC:"] = APIC(
                    encoding=3, mime=mime, type=3,
                    desc="Cover", data=self.album_art_data
                )

            tags.save(path, v2_version=3)
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    def export_mp3(self):
        if not self.current_file:
            messagebox.showwarning("No file", "Select a file first.")
            return
        out = filedialog.asksaveasfilename(
            defaultextension=".mp3",
            filetypes=[("MP3", "*.mp3")],
            initialfile=f"export_{Path(self.current_file).name}"
        )
        if out:
            threading.Thread(target=self._do_export, args=(out,), daemon=True).start()

    def bulk_export(self):
        if not self.files:
            messagebox.showwarning("No files", "Add files to the queue first.")
            return
        out_dir = filedialog.askdirectory(title="Select folder for bulk export")
        if not out_dir:
            return
        threading.Thread(target=self._do_bulk_export, args=(out_dir,), daemon=True).start()

    def _do_bulk_export(self, out_dir: str):
        total = len(self.files)
        errors = []
        for i, src in enumerate(self.files):
            name = f"export_{Path(src).name}"
            out_path = str(Path(out_dir) / name)
            self.after(0, lambda i=i, name=name: self.file_label.configure(
                text=f"⏳ Exporting {i+1}/{total}: {name}"))
            try:
                self._do_export_path(src, out_path)
            except Exception as e:
                errors.append(f"{Path(src).name}: {e}")
        self.after(0, lambda: self.file_label.configure(
            text=Path(self.current_file).name if self.current_file else "No file selected"))
        if errors:
            self.after(0, lambda: messagebox.showerror(
                "Bulk Export Errors", "\n".join(errors)))
        else:
            self.after(0, lambda: messagebox.showinfo(
                "Bulk Export Done", f"Exported {total} file(s) to:\n{out_dir}"))

    def _do_export(self, out_path: str):
        self.after(0, lambda: self.file_label.configure(text="⏳ Processing…"))
        try:
            self._do_export_path(self.current_file, out_path)
            self.after(0, lambda: [
                self.file_label.configure(text=Path(self.current_file).name),
                messagebox.showinfo("Exported", f"Saved to:\n{out_path}")
            ])
        except Exception as e:
            self.after(0, lambda: [
                self.file_label.configure(text=Path(self.current_file).name),
                messagebox.showerror("Export Error", str(e))
            ])

    def _do_export_path(self, src: str, out_path: str):
        """Process EQ/effects and write to out_path. Raises on error."""
        audio = AudioSegment.from_mp3(src)
        sr = audio.frame_rate
        ch = audio.channels

        samples = np.array(audio.get_array_of_samples(), dtype=np.float32) / 32768.0
        if ch == 2:
            samples = samples.reshape(-1, 2)

        nyq = sr / 2
        band_ranges = {
            "bass":     (80,   200),
            "low_mid":  (200,  800),
            "mid":      (800,  3000),
            "high_mid": (3000, 6000),
            "treble":   (6000, 16000),
        }
        processed = samples.copy()
        for key, (lo, hi) in band_ranges.items():
            gain_db = self.eq_vars[key].get()
            if abs(gain_db) < 0.1:
                continue
            lo_n = max(lo / nyq, 0.001)
            hi_n = min(hi / nyq, 0.999)
            if lo_n >= hi_n:
                continue
            b, a = scipy_signal.butter(2, [lo_n, hi_n], btype="band")
            gain_delta = 10 ** (gain_db / 20) - 1.0
            if ch == 2:
                filtered = np.column_stack([
                    scipy_signal.filtfilt(b, a, samples[:, 0]),
                    scipy_signal.filtfilt(b, a, samples[:, 1]),
                ])
            else:
                filtered = scipy_signal.filtfilt(b, a, samples)
            processed += filtered * gain_delta

        if self.stereo_var.get() and ch == 2:
            mid  = (processed[:, 0] + processed[:, 1]) / 2
            side = (processed[:, 0] - processed[:, 1]) / 2 * 1.6
            processed[:, 0] = mid + side
            processed[:, 1] = mid - side

        if self.normalize_var.get():
            peak = np.max(np.abs(processed))
            if peak > 0:
                processed = processed * (0.95 / peak)

        processed = np.clip(processed, -1.0, 1.0)
        pcm = (processed * 32767).astype(np.int16)

        out_audio = AudioSegment(pcm.tobytes(), frame_rate=sr, sample_width=2, channels=ch)

        speed = self.speed_var.get()
        if abs(speed - 1.0) > 0.01:
            out_audio = out_audio._spawn(
                out_audio.raw_data,
                overrides={"frame_rate": int(sr * speed)}
            ).set_frame_rate(sr)

        out_audio.export(out_path, format="mp3", bitrate="320k")
        self._write_tags(out_path)

    # ─────────────────────────── DOWNLOAD ────────────────────────────

    def _paste_url(self):
        try:
            text = self.clipboard_get().strip()
            self.dl_url_box.insert("end", text + "\n")
        except Exception:
            pass

    def _browse_dl_dir(self):
        d = filedialog.askdirectory(title="Select download folder")
        if d:
            self.dl_dir_var.set(d)

    def _dl_log(self, msg: str):
        self.after(0, lambda: (
            self.dl_log.insert("end", msg + "\n"),
            self.dl_log.see("end"),
        ))

    def _dl_set_status(self, msg: str, progress: float | None = None):
        self.after(0, lambda: self.dl_status_label.configure(text=msg))
        if progress is not None:
            self.after(0, lambda: self.dl_progress.set(min(max(progress, 0.0), 1.0)))

    def _tree_set(self, row_id: str, col: str, value: str, tag: str = ""):
        def _do():
            try:
                self.dl_tree.set(row_id, col, value)
                if tag:
                    self.dl_tree.item(row_id, tags=(tag,))
            except Exception:
                pass
        self.after(0, _do)

    def _start_download(self):
        raw = self.dl_url_box.get("1.0", "end")
        urls = [u.strip() for u in raw.splitlines() if u.strip() and not u.strip().startswith("#")]
        if not urls:
            messagebox.showwarning("No URLs", "Enter at least one URL.")
            return

        # Clear old rows
        for row in self.dl_tree.get_children():
            self.dl_tree.delete(row)
        self.dl_log.delete("1.0", "end")
        self.dl_progress.set(0)
        self.dl_button.configure(state="disabled", text="Downloading…")

        threading.Thread(target=self._do_download_all, args=(urls,), daemon=True).start()

    def _do_download_all(self, urls: list[str]):
        out_dir = self.dl_dir_var.get()
        auto_tag = self.dl_auto_tag_var.get()

        # ── Step 1: expand each URL (flat) to get titles / playlist tracks ──
        row_map: dict[str, dict] = {}   # row_id → {url, title, source}

        self._dl_set_status("Resolving URLs…", 0.02)
        flat_opts = {
            "quiet": True, "no_warnings": True,
            "extract_flat": "in_playlist",
            "skip_download": True,
        }

        all_tasks: list[dict] = []   # {url, title, source, row_id}

        for url in urls:
            try:
                with yt_dlp.YoutubeDL(flat_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                if info is None:
                    raise ValueError("Could not resolve URL")

                if info.get("_type") == "playlist" or "entries" in info:
                    entries = list(info.get("entries") or [])
                    playlist_title = info.get("title", "Playlist")
                    self._dl_log(f"Playlist '{playlist_title}': {len(entries)} tracks")
                    for entry in entries:
                        if not entry:
                            continue
                        e_url   = entry.get("url") or entry.get("webpage_url") or f"https://www.youtube.com/watch?v={entry.get('id','')}"
                        e_title = entry.get("title", e_url[:60])
                        e_src   = info.get("extractor_key", "Web")
                        row_id  = self.after(0, lambda et=e_title, es=e_src: None)  # placeholder
                        row_id  = self.dl_tree.insert("", "end",
                                                      values=(e_title, es, "Queued"),
                                                      tags=("queued",))
                        all_tasks.append({"url": e_url, "title": e_title,
                                          "source": e_src, "row_id": row_id})
                else:
                    title  = info.get("title", url[:60])
                    source = info.get("extractor_key", "Web")
                    row_id = self.dl_tree.insert("", "end",
                                                 values=(title, source, "Queued"),
                                                 tags=("queued",))
                    all_tasks.append({"url": url, "title": title,
                                      "source": source, "row_id": row_id})
            except Exception as e:
                row_id = self.dl_tree.insert("", "end",
                                             values=(url[:60], "?", f"Error: {e}"),
                                             tags=("error",))
                self._dl_log(f"Resolve error [{url[:60]}]: {e}")

        total = len(all_tasks)
        if total == 0:
            self.after(0, lambda: self.dl_button.configure(state="normal", text="⬇  Download All"))
            return

        # ── Step 2: download each track ──
        for i, task in enumerate(all_tasks):
            self._dl_set_status(f"Downloading {i+1}/{total}: {task['title'][:50]}", i / total)
            self._tree_set(task["row_id"], "status", "Downloading…", "active")
            self.after(0, lambda rid=task["row_id"]: self.dl_tree.see(rid))

            path, info = self._download_one_track(task["url"], task["row_id"], out_dir)

            if path:
                if auto_tag:
                    self._tree_set(task["row_id"], "status", "Tagging…", "tagging")
                    self._auto_tag_file(path, info or {})

                self._tree_set(task["row_id"], "status", "Done ✓", "done")
                self._dl_log(f"✓ {task['title']}")

                if self.dl_add_queue_var.get():
                    p = path
                    self.after(0, lambda p=p: self._add_to_queue(p))
            else:
                self._tree_set(task["row_id"], "status", "Error ✗", "error")

        self._dl_set_status(f"All done — {total} track(s) downloaded", 1.0)
        self.after(0, lambda: self.dl_button.configure(state="normal", text="⬇  Download All"))

    def _download_one_track(self, url: str, row_id: str, out_dir: str) -> tuple[str | None, dict | None]:
        result_path: list[str]  = []
        result_info: list[dict] = []

        def progress_hook(d):
            if d["status"] == "downloading":
                pct = d.get("_percent_str", "").strip()
                spd = d.get("_speed_str", "")
                self._tree_set(row_id, "status", f"Downloading {pct} {spd}", "active")
            elif d["status"] == "finished":
                self._tree_set(row_id, "status", "Converting…", "active")

        def pp_hook(d):
            if d["status"] == "finished":
                info_dict = d.get("info_dict", {})
                result_info.append(info_dict)
                # Resolve mp3 path
                fp = info_dict.get("filepath", "")
                if not fp or not Path(fp).exists():
                    try:
                        with yt_dlp.YoutubeDL({"quiet": True}) as ydl_tmp:
                            base = ydl_tmp.prepare_filename(info_dict)
                        fp = str(Path(base).with_suffix(".mp3"))
                    except Exception:
                        fp = ""
                if fp and Path(fp).exists():
                    result_path.append(fp)

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": str(Path(out_dir) / "%(title)s.%(ext)s"),
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "320"},
                {"key": "FFmpegMetadata"},
            ],
            "progress_hooks": [progress_hook],
            "postprocessor_hooks": [pp_hook],
            "quiet": True,
            "no_warnings": True,
            "writethumbnail": False,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            # Fallback path resolution
            if not result_path and result_info:
                try:
                    with yt_dlp.YoutubeDL({"quiet": True}) as ydl_tmp:
                        base = ydl_tmp.prepare_filename(result_info[0])
                    fp = str(Path(base).with_suffix(".mp3"))
                    if Path(fp).exists():
                        result_path.append(fp)
                except Exception:
                    pass

            if not result_path:
                mp3s = sorted(Path(out_dir).glob("*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True)
                if mp3s:
                    result_path.append(str(mp3s[0]))

            info = result_info[0] if result_info else None
            return (result_path[0] if result_path else None), info

        except Exception as e:
            self._dl_log(f"Download error: {e}")
            return None, None

    def _auto_tag_file(self, path: str, info: dict):
        title  = info.get("title", "") or Path(path).stem
        artist = (info.get("artist") or info.get("uploader") or
                  info.get("channel") or info.get("creator") or "")
        album  = info.get("album") or info.get("playlist_title") or info.get("playlist") or ""
        year   = ""
        if info.get("release_year"):
            year = str(info["release_year"])
        elif info.get("upload_date"):
            year = str(info["upload_date"])[:4]
        genre  = info.get("genre") or ""

        # Try iTunes for better metadata + HD art
        try:
            q = requests.utils.quote(f"{artist} {title}")
            r = requests.get(f"https://itunes.apple.com/search?term={q}&media=music&limit=1", timeout=8)
            if r.status_code == 200:
                data = r.json()
                if data.get("resultCount"):
                    res = data["results"][0]
                    if not album:
                        album = res.get("collectionName", "")
                    if not year:
                        year = res.get("releaseDate", "")[:4]
                    if not genre:
                        genre = res.get("primaryGenreName", "")
                    art_url = res.get("artworkUrl100", "").replace("100x100bb", "600x600bb")
                    if art_url:
                        art_data = requests.get(art_url, timeout=8).content
                        self._write_tags_direct(path, title, artist, album, year, genre, art_data)
                        self._fetch_and_embed_lyrics(path, artist, title)
                        return
        except Exception:
            pass

        self._write_tags_direct(path, title, artist, album, year, genre, None)
        self._fetch_and_embed_lyrics(path, artist, title)

    def _write_tags_direct(self, path: str, title: str, artist: str, album: str,
                            year: str, genre: str, art_data: bytes | None):
        try:
            try:
                tags = ID3(path)
            except ID3NoHeaderError:
                tags = ID3()
            if title:  tags["TIT2"] = TIT2(encoding=3, text=title)
            if artist: tags["TPE1"] = TPE1(encoding=3, text=artist)
            if album:  tags["TALB"] = TALB(encoding=3, text=album)
            if year:   tags["TYER"] = TYER(encoding=3, text=year)
            if genre:  tags["TCON"] = TCON(encoding=3, text=genre)
            if art_data:
                mime = "image/png" if art_data[:4] == b"\x89PNG" else "image/jpeg"
                tags["APIC:"] = APIC(encoding=3, mime=mime, type=3, desc="Cover", data=art_data)
            tags.save(path, v2_version=3)
        except Exception as e:
            self._dl_log(f"Tag write error: {e}")

    def _fetch_and_embed_lyrics(self, path: str, artist: str, title: str):
        if not artist or not title:
            return
        try:
            a = requests.utils.quote(artist)
            t = requests.utils.quote(title)
            r = requests.get(f"https://api.lyrics.ovh/v1/{a}/{t}", timeout=10)
            if r.status_code == 200:
                lyrics = r.json().get("lyrics", "").strip()
                if lyrics:
                    try:
                        tags = ID3(path)
                    except ID3NoHeaderError:
                        tags = ID3()
                    tags["USLT::eng"] = USLT(encoding=3, lang="eng", desc="", text=lyrics)
                    tags.save(path, v2_version=3)
        except Exception:
            pass

    def _add_to_queue(self, path: str):
        if path not in self.files:
            self.files.append(path)
            self.listbox.insert("end", Path(path).name)
        idx = self.files.index(path)
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(idx)
        self.listbox.see(idx)
        self._on_select()

    # ─────────────────────────── MISC ────────────────────────────

    def _set_field(self, key: str, value: str):
        if value:
            self.fields[key].delete(0, "end")
            self.fields[key].insert(0, value)

    def _apply_eq_preset(self, name: str):
        """Set the 5 EQ sliders to a named preset and refresh their value labels."""
        preset = self.EQ_PRESETS.get(name)
        if not preset:
            return
        for key, gain in preset.items():
            if key in self.eq_vars:
                self.eq_vars[key].set(float(gain))
            lbl = self.eq_value_labels.get(key)
            if lbl is not None:
                lbl.configure(text=f"{float(gain):+.1f} dB")

    def _reset_eq(self):
        for key, var in self.eq_vars.items():
            var.set(0.0)
            lbl = self.eq_value_labels.get(key)
            if lbl is not None:
                lbl.configure(text="+0.0 dB")
        self.eq_preset_menu.set("Flat")
        self.speed_var.set(1.0)
        self.speed_lbl.configure(text="1.0×")
        self.normalize_var.set(False)
        self.stereo_var.set(False)


if __name__ == "__main__":
    app = MP3Studio()
    app.mainloop()
