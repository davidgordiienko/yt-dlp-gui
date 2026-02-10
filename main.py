import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import subprocess
import os
import json
import sys
import re
import urllib.request
import signal

CONFIG_FILE = "config.json"


# --------------------------------------------------
# Resource Path (PyInstaller Safe)
# --------------------------------------------------

def resource_path(filename):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, filename)
    return os.path.join(os.path.abspath("."), filename)


YT_DLP = resource_path("yt-dlp.exe")
FFMPEG = resource_path("ffmpeg.exe")


class YouTubeDownloader:

    def __init__(self, root):
        self.root = root
        self.root.title("YouTube Downloader")
        self.root.geometry("560x360")

        self.load_config()

        # Title
        tk.Label(
            root,
            text="YouTube Video Downloader",
            font=("Segoe UI", 14, "bold")
        ).pack(pady=10)

        # yt-dlp version label (just under title)
        self.version_label = tk.Label(
            root,
            text="yt-dlp version: checking...",
            anchor="center",
            justify="center"
        )
        self.version_label.pack(pady=(0, 5))

        # URL
        tk.Label(root, text="YouTube URL").pack()
        self.url_entry = tk.Entry(root, width=70)
        self.url_entry.pack(pady=5)
        self.url_entry.focus()

        # Try to populate URL from clipboard when the field is empty
        self.root.after(200, self.populate_url_from_clipboard_if_empty)
        self.root.bind(
            "<FocusIn>",
            lambda event: self.populate_url_from_clipboard_if_empty()
        )

        # Format dropdown
        format_frame = tk.Frame(root)
        format_frame.pack(pady=5)

        tk.Label(format_frame, text="Download as:").pack(side="left", padx=5)

        self.format_var = tk.StringVar(value="MP4 (Video)")
        self.format_dropdown = ttk.Combobox(
            format_frame,
            textvariable=self.format_var,
            values=["MP4 (Video)", "MP3 (Audio)"],
            state="readonly",
            width=15
        )
        self.format_dropdown.pack(side="left")

        # Folder
        tk.Button(
            root,
            text="Choose Output Folder",
            command=self.choose_folder
        ).pack(pady=5)

        self.folder_label = tk.Label(
            root,
            text=self.output_dir or "No folder selected",
            wraplength=520
        )
        self.folder_label.pack()

        # Status
        self.status_label = tk.Label(
            root,
            text="Ready",
            anchor="w",
            width=70
        )
        self.status_label.pack(pady=5)

        # Progress bar (DETERMINATE again)
        self.progress = ttk.Progressbar(
            root,
            orient="horizontal",
            length=500,
            mode="determinate",
            maximum=100
        )
        self.progress.pack(pady=10)

        # Download button
        self.download_btn = tk.Button(
            root,
            text="⬇ Download",
            width=22,
            height=2,
            font=("Segoe UI", 10, "bold"),
            command=self.start_download
        )
        self.download_btn.pack(pady=10)

        # Progress tracking state
        self.current_format_choice = None  # "MP4 (Video)" or "MP3 (Audio)"
        self.phase_round = 0              # 0 = first phase (video), 1 = second phase (audio)
        self.last_raw_percent = 0.0       # last raw % reported by yt-dlp (0–100)

        # Download/update state
        self.is_downloading = False
        self.update_after_download = False
        self.current_process = None
        self.cancel_requested = False

        # Immediately check version and offer update options (no artificial delay)
        self.check_for_updates()

    # --------------------------------------------------
    # Config
    # --------------------------------------------------

    def load_config(self):
        self.output_dir = ""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    self.output_dir = json.load(f).get("last_folder", "")
            except:
                pass

    # --------------------------------------------------

    def populate_url_from_clipboard_if_empty(self):
        """Auto-fill URL field from clipboard if it looks like a YouTube link."""
        if self.url_entry.get().strip():
            return

        try:
            clip = self.root.clipboard_get().strip()
        except tk.TclError:
            return

        if re.search(r"https?://(www\.)?(youtube\.com|youtu\.be)/", clip, re.IGNORECASE):
            self.url_entry.delete(0, tk.END)
            self.url_entry.insert(0, clip)

    def save_config(self):
        with open(CONFIG_FILE, "w") as f:
            json.dump({"last_folder": self.output_dir}, f)

    # --------------------------------------------------

    def choose_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.output_dir = folder
            self.folder_label.config(text=folder)
            self.save_config()

    # --------------------------------------------------
    # UPDATE CHECKER
    # --------------------------------------------------

    def check_for_updates(self):
        def run():
            local_version = "Unknown"
            latest_version = None
            try:
                run_kwargs = {
                    "capture_output": True,
                    "text": True,
                }
                if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
                    run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

                result = subprocess.run([YT_DLP, "--version"], **run_kwargs)
                stdout = (result.stdout or "").strip()
                if stdout:
                    local_version = stdout.splitlines()[0]
            except Exception:
                pass
            # Try to fetch latest release info from GitHub.
            try:
                with urllib.request.urlopen(
                    "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest",
                    timeout=5
                ) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    tag = data.get("tag_name") or ""
                    # tag_name is typically like "2025.01.13" or "v2025.01.13"
                    tag = tag.lstrip("vV")
                    if tag:
                        latest_version = tag
            except Exception:
                latest_version = None

            def apply():
                # Update version label in UI
                self.version_label.config(text=f"yt-dlp version: {local_version}")

                # Only show update popup if we know a newer version exists
                def parse_ver(v):
                    try:
                        return tuple(int(x) for x in v.split("."))
                    except Exception:
                        return ()

                if local_version != "Unknown" and latest_version:
                    if parse_ver(latest_version) > parse_ver(local_version):
                        self.show_update_popup(local_version, latest_version)

            self.root.after(0, apply)

        threading.Thread(target=run, daemon=True).start()

    def show_update_popup(self, current_version=None, latest_version=None):
        popup = tk.Toplevel(self.root)
        popup.title("yt-dlp Update")
        popup.resizable(False, False)
        popup.grab_set()

        if current_version and latest_version:
            version_line = f"Current version: {current_version}\nLatest version: {latest_version}\n\n"
        else:
            version_line = ""

        message = (
            "Updating yt-dlp is strongly recommended.\n\n"
            "Older versions of yt-dlp may not work correctly with YouTube.\n\n"
            f"{version_line}"
            "Would you like to update yt-dlp now or after the current download "
            "finishes?"
        )

        tk.Label(
            popup,
            text=message,
            justify="left",
            wraplength=420
        ).pack(padx=20, pady=15)

        btn_frame = tk.Frame(popup)
        btn_frame.pack(pady=(0, 15))

        def close():
            popup.destroy()

        def update_now():
            popup.destroy()
            self.update_after_download = False
            self.run_update()

        def update_later():
            popup.destroy()
            # Defer update until the current/next download finishes
            self.update_after_download = True

        tk.Button(
            btn_frame,
            text="Update now",
            width=18,
            command=update_now
        ).pack(side="left", padx=5)

        tk.Button(
            btn_frame,
            text="Update after download",
            width=20,
            command=update_later
        ).pack(side="left", padx=5)

        tk.Button(
            btn_frame,
            text="Not now",
            width=12,
            command=close
        ).pack(side="left", padx=5)

    def run_update(self):
        self.status_label.config(text="Updating yt-dlp...")
        self.download_btn.config(state="disabled")

        def run():
            run_kwargs = {}
            if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
                run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

            subprocess.run([YT_DLP, "-U"], **run_kwargs)
            self.root.after(0, self.update_finished)

        threading.Thread(target=run, daemon=True).start()

    def update_finished(self):
        self.download_btn.config(state="normal")
        self.status_label.config(text="yt-dlp update complete.")
        messagebox.showinfo(
            "Update Complete",
            "yt-dlp was updated successfully."
        )

    # --------------------------------------------------
    # Download
    # --------------------------------------------------

    def start_download(self):
        url = self.url_entry.get().strip()
        format_choice = self.format_var.get()

        if not url:
            messagebox.showerror("Error", "Enter a YouTube URL.")
            return

        if not self.output_dir:
            messagebox.showerror("Error", "Choose an output folder.")
            return

        # Reset progress tracking for this download
        self.current_format_choice = format_choice
        self.phase_round = 0
        self.last_raw_percent = 0.0

        self.is_downloading = True
        self.cancel_requested = False
        self.download_btn.config(
            text="✖ Cancel",
            command=self.cancel_download,
            state="normal"
        )
        self.progress["value"] = 0
        self.status_label.config(text="Starting download...")

        threading.Thread(
            target=self.download_video,
            args=(url, format_choice),
            daemon=True
        ).start()

    # --------------------------------------------------

    def cancel_download(self):
        """Cancel the current download, if any."""
        # Mark as cancelled first so the worker thread can see it immediately.
        self.cancel_requested = True

        proc = self.current_process
        if proc is not None:
            try:
                if os.name == "nt":
                    # On Windows, send a console control event so yt-dlp can
                    # handle it like Ctrl+C and clean up its own .part files.
                    try:
                        os.kill(proc.pid, signal.CTRL_BREAK_EVENT)
                    except Exception:
                        os.kill(proc.pid, signal.CTRL_C_EVENT)
                else:
                    # On POSIX, send SIGINT first.
                    proc.send_signal(signal.SIGINT)
            except Exception:
                pass

            # Closing stdout helps break out of the read loop promptly.
            try:
                if proc.stdout:
                    proc.stdout.close()
            except Exception:
                pass

        self.status_label.config(text="Cancelling download...")

    # --------------------------------------------------

    def download_video(self, url, format_choice):
        try:
            output_template = os.path.join(
                self.output_dir,
                "%(title)s.%(ext)s"
            )

            if format_choice == "MP3 (Audio)":
                cmd = [
                    YT_DLP,
                    "--ffmpeg-location", FFMPEG,
                    "-x",
                    "--audio-format", "mp3",
                    "-o", output_template,
                    url
                ]
            else:
                cmd = [
                    YT_DLP,
                    "--ffmpeg-location", FFMPEG,
                    "-f", "bv*[ext=mp4]+ba[ext=m4a]/b",
                    "--merge-output-format", "mp4",
                    "-o", output_template,
                    url
                ]

            creationflags = 0
            if os.name == "nt":
                if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
                    creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP
                if hasattr(subprocess, "CREATE_NO_WINDOW"):
                    creationflags |= subprocess.CREATE_NO_WINDOW

            popen_kwargs = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
                "text": True,
                "bufsize": 1,
            }
            if creationflags:
                popen_kwargs["creationflags"] = creationflags

            self.current_process = subprocess.Popen(cmd, **popen_kwargs)

            collected_lines = []

            for line in self.current_process.stdout:
                if self.cancel_requested:
                    # Stop reading further output once cancel is requested.
                    break

                collected_lines.append((line or "").rstrip("\n"))
                self.parse_progress(line)

            # Wait for the process to exit (after normal completion or cancel).
            self.current_process.wait()

            if self.cancel_requested:
                # Treat as a user-cancelled operation rather than an error.
                self.root.after(0, self.download_cancelled)
                return

            if self.current_process.returncode != 0:
                # Build a more informative error message using yt-dlp's output.
                tail = "\n".join(collected_lines[-20:]) if collected_lines else "No output captured."
                raise RuntimeError(
                    f"yt-dlp failed with exit code {self.current_process.returncode}.\n\n"
                    f"Last output from yt-dlp:\n{tail}"
                )

            self.root.after(
                0,
                lambda: self.download_complete(self.output_dir)
            )

        except Exception as e:
            self.root.after(
                0,
                lambda: self.download_failed(str(e))
            )
        finally:
            self.current_process = None

    # --------------------------------------------------
    # Progress Parsing (THIS FIXES IT)
    # --------------------------------------------------

    def parse_progress(self, line):
        match = re.search(
            r"(\d+(?:\.\d+)?)%\s+of.*?at\s+([^\s]+).*?ETA\s+([0-9:]+)",
            line
        )

        if not match:
            return

        percent_str, speed, eta = match.groups()

        try:
            raw_percent = float(percent_str)
        except ValueError:
            return

        # Detect when yt-dlp starts the second phase (audio) for MP4 downloads:
        # the percentage jumps from ~100 back to a small number.
        if (
            self.current_format_choice == "MP4 (Video)"
            and self.phase_round == 0
            and self.last_raw_percent >= 99.0
            and raw_percent < self.last_raw_percent
        ):
            self.phase_round = 1

        self.last_raw_percent = raw_percent

        # Compute a unified 0–100% progress value, and clarify which phase we're in.
        if self.current_format_choice == "MP4 (Video)":
            if self.phase_round == 0:
                # First half of the bar is video
                display_percent = raw_percent * 0.5
                phase_label = "Video"
            else:
                # Second half is audio
                display_percent = 50.0 + raw_percent * 0.5
                phase_label = "Audio"

            status_text = (
                f"{phase_label}: {raw_percent:.1f}% "
                f"(Overall {display_percent:.1f}%) | {speed} | ETA {eta}"
            )
        else:
            # Pure audio downloads just map directly 0–100.
            display_percent = raw_percent
            phase_label = "Audio"
            status_text = (
                f"{phase_label}: {raw_percent:.1f}% | {speed} | ETA {eta}"
            )

        def update():
            self.progress["value"] = display_percent
            self.status_label.config(text=status_text)

        self.root.after(0, update)

    # --------------------------------------------------

    def download_complete(self, folder):
        self.is_downloading = False
        self.download_btn.config(
            text="⬇ Download",
            command=self.start_download,
            state="normal"
        )
        self.progress["value"] = 100
        self.status_label.config(text="Download complete!")

        subprocess.Popen(f'explorer "{os.path.normpath(folder)}"')
        messagebox.showinfo("Success", "Download finished!")

        # If user chose "update after download", run it now
        if self.update_after_download:
            self.update_after_download = False
            self.run_update()

    # --------------------------------------------------

    def download_failed(self, error):
        self.is_downloading = False
        self.download_btn.config(
            text="⬇ Download",
            command=self.start_download,
            state="normal"
        )
        self.status_label.config(text="Download failed.")

        messagebox.showerror(
            "Download Failed",
            "The download failed.\n\n"
            "YouTube sometimes changes things which can break downloads.\n\n"
            "Try updating yt-dlp using the update options in this app.\n\n"
            f"Error:\n{error}"
        )

    # --------------------------------------------------

    def download_cancelled(self):
        self.is_downloading = False
        self.download_btn.config(
            text="⬇ Download",
            command=self.start_download,
            state="normal"
        )
        self.status_label.config(text="Download cancelled.")
        self.cleanup_partial_files()

    # --------------------------------------------------

    def cleanup_partial_files(self):
        """Remove leftover .part files from the output directory for the user."""
        if not self.output_dir or not os.path.isdir(self.output_dir):
            return

        try:
            for name in os.listdir(self.output_dir):
                if name.endswith(".part"):
                    try:
                        os.remove(os.path.join(self.output_dir, name))
                    except Exception:
                        # Ignore individual delete errors; they are non-fatal.
                        pass
        except Exception:
            # If we can't list the directory, just skip cleanup silently.
            pass


# --------------------------------------------------

root = tk.Tk()
app = YouTubeDownloader(root)
root.mainloop()