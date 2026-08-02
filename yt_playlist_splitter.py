#!/usr/bin/env python3
import re
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

try:
    import yt_dlp
except ImportError:
    sys.exit("yt-dlp not installed. Run: pip install yt-dlp")

# Set UI Theme
ctk.set_appearance_mode("System")  # "System", "Dark", "Light"
ctk.set_default_color_theme("blue")  # "blue", "green", "dark-blue"


# --- Core Downloader Logic ---

_MODE_DIRS = {"audio": "mp3", "video": "video", "thumbnail": "thumbnails"}

def build_ydl_opts(output_dir: Path, mode: str, progress_hook=None) -> dict:
    # Handle filename template based on mode
    if mode == "thumbnail":
        out_template = str(output_dir / "%(title)s.webp")
    else:
        out_template = str(output_dir / "%(title)s.%(ext)s")

    common = {
        "outtmpl": {
            "default": out_template,
        },
        "restrictfilenames": False,
        "windowsfilenames": True,
        "ignoreerrors": True,
        "noplaylist": False,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [progress_hook] if progress_hook else [],
    }

    if mode == "audio":
        common.update({
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        })
    elif mode == "video":
        common.update({
            "format": "bestvideo[ext=mp4]/bestvideo",
            "postprocessors": [{
                "key": "FFmpegVideoConvertor",
                "preferedformat": "mp4",
            }],
        })
    elif mode == "thumbnail":
        common.update({
            "skip_download": True,       # Skip audio and video download
            "writethumbnail": True,      # Save raw thumbnail (default on YT is webp/jpg)
            # No FFmpeg postprocessor attached -> prevents conversion to JPG
        })

    return common


# --- GUI Application ---

class PlaylistSplitterGUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("YT Playlist Splitter")
        self.geometry("680x560")
        self.resizable(False, False)

        self._create_widgets()

    def _create_widgets(self):
        # Header
        self.header = ctk.CTkLabel(
            self, 
            text="YouTube Playlist Splitter", 
            font=ctk.CTkFont(size=22, weight="bold")
        )
        self.header.pack(padx=20, pady=(20, 10))

        # URL Frame
        self.url_frame = ctk.CTkFrame(self)
        self.url_frame.pack(padx=20, pady=10, fill="x")

        self.url_label = ctk.CTkLabel(self.url_frame, text="URL:", font=ctk.CTkFont(weight="bold"))
        self.url_label.pack(side="left", padx=10, pady=10)

        self.url_entry = ctk.CTkEntry(self.url_frame, placeholder_text="Paste YouTube Playlist or Video URL here...")
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 10), pady=10)

        # Output Path Frame
        self.path_frame = ctk.CTkFrame(self)
        self.path_frame.pack(padx=20, pady=10, fill="x")

        self.path_label = ctk.CTkLabel(self.path_frame, text="Save To:", font=ctk.CTkFont(weight="bold"))
        self.path_label.pack(side="left", padx=10, pady=10)

        default_path = str(Path.home() / "Downloads" / "yt_split")
        self.path_entry = ctk.CTkEntry(self.path_frame)
        self.path_entry.insert(0, default_path)
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 10), pady=10)

        self.browse_btn = ctk.CTkButton(self.path_frame, text="Browse", width=80, command=self._browse_folder)
        self.browse_btn.pack(side="right", padx=(0, 10), pady=10)

        # Download Options Frame
        self.opts_frame = ctk.CTkFrame(self)
        self.opts_frame.pack(padx=20, pady=10, fill="x")

        self.audio_switch = ctk.CTkSwitch(self.opts_frame, text="Audio (MP3)")
        self.audio_switch.select()
        self.audio_switch.pack(side="left", expand=True, pady=12)

        self.video_switch = ctk.CTkSwitch(self.opts_frame, text="Video Only (MP4)")
        self.video_switch.select()
        self.video_switch.pack(side="left", expand=True, pady=12)

        self.thumb_switch = ctk.CTkSwitch(self.opts_frame, text="Thumbnails (WEBP)")
        self.thumb_switch.pack(side="left", expand=True, pady=12)

        # Action Button & Progress
        self.download_btn = ctk.CTkButton(
            self, 
            text="Start Download", 
            font=ctk.CTkFont(size=15, weight="bold"),
            height=40,
            command=self._start_download_thread
        )
        self.download_btn.pack(padx=20, pady=(10, 5), fill="x")

        self.progress_bar = ctk.CTkProgressBar(self)
        self.progress_bar.set(0)
        self.progress_bar.pack(padx=20, pady=10, fill="x")

        # Log Window
        self.log_box = ctk.CTkTextbox(self, height=160, font=ctk.CTkFont(family="Consolas", size=12))
        self.log_box.pack(padx=20, pady=(0, 20), fill="both", expand=True)
        self.log_box.configure(state="disabled")

    def _browse_folder(self):
        selected = filedialog.askdirectory()
        if selected:
            self.path_entry.delete(0, tk.END)
            self.path_entry.insert(0, selected)

    def _log(self, text: str):
        self.log_box.configure(state="normal")
        self.log_box.insert(tk.END, text + "\n")
        self.log_box.see(tk.END)
        self.log_box.configure(state="disabled")

    def _yt_dlp_hook(self, d):
        if d['status'] == 'downloading':
            try:
                p = d.get('_percent_str', '0%').strip()
                clean_p = float(re.sub(r'\x1b\[[0-9;]*m', '', p).replace('%', '')) / 100.0
                self.progress_bar.set(clean_p)
            except ValueError:
                pass
        elif d['status'] == 'finished':
            self.progress_bar.set(1.0)

    def _start_download_thread(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("Input Error", "Please paste a valid YouTube URL.")
            return

        do_audio = bool(self.audio_switch.get())
        do_video = bool(self.video_switch.get())
        do_thumb = bool(self.thumb_switch.get())

        if not any([do_audio, do_video, do_thumb]):
            messagebox.showwarning("Selection Error", "Please select at least one format to download.")
            return

        # Disable UI elements during processing
        self.download_btn.configure(state="disabled", text="Downloading...")
        self.progress_bar.set(0)

        # Run in separate thread to prevent frozen UI
        threading.Thread(
            target=self._run_downloads, 
            args=(url, Path(self.path_entry.get()), do_audio, do_video, do_thumb),
            daemon=True
        ).start()

    def _run_downloads(self, url: str, base_dir: Path, do_audio: bool, do_video: bool, do_thumb: bool):
        modes = []
        if do_audio: modes.append("audio")
        if do_video: modes.append("video")
        if do_thumb: modes.append("thumbnail")

        base_dir.mkdir(parents=True, exist_ok=True)

        for mode in modes:
            target_dir = base_dir / _MODE_DIRS[mode]
            target_dir.mkdir(parents=True, exist_ok=True)
            
            self._log(f"=== Starting [{mode.upper()}] download -> {target_dir.name}/ ===")
            opts = build_ydl_opts(target_dir, mode, progress_hook=self._yt_dlp_hook)

            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])
                self._log(f"✓ [{mode.upper()}] Task Finished.\n")
            except Exception as e:
                self._log(f"❌ Error during [{mode.upper()}]: {e}\n")

        self._log(f"🎉 All tasks finished! Files saved to: {base_dir}")
        self.progress_bar.set(1.0)
        
        # Restore UI controls
        self.download_btn.configure(state="normal", text="Start Download")


if __name__ == "__main__":
    app = PlaylistSplitterGUI()
    app.mainloop()