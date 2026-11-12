"""Tkinter user interface for managing pairs, logs, and the daemon."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from tkinter import Tk, StringVar, END, messagebox, filedialog
from tkinter import ttk

from app_config import (
    APP_NAME, CONFIG_FILE, DEFAULT_INTERVAL, LOG_FILE, PID_FILE,
    ensure_app_dir, load_config, save_config, validate_pairs,
)
from daemon import daemon_lock_is_held, is_folder_mirror_daemon
from app_logging import setup_logging
from sync import run_sync

class FolderMirrorUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Folder Mirror")
        self.root.geometry("1180x650")
        self.root.minsize(900, 500)
        self.config = load_config()
        setup_logging()  # Ensure the log file exists before the live viewer starts.
        self.status = StringVar(value="Ready")
        self.interval = StringVar(value=str(self.config.get("interval_seconds", DEFAULT_INTERVAL)))
        self._build()
        self.refresh_pairs()
        self.refresh_daemon_status()

    def _build(self):
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="Folder synchronization pairs", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(
            outer,
            text="Each destination is an exact mirror of its source, including subfolders.",
            foreground="#555"
        ).pack(anchor="w", pady=(2, 10))

        # Main workspace: folder mappings on the left, live log viewer on the right.
        workspace = ttk.Panedwindow(outer, orient="horizontal")
        workspace.pack(fill="both", expand=True)

        left_panel = ttk.Frame(workspace, padding=(0, 0, 8, 0))
        right_panel = ttk.Frame(workspace, padding=(8, 0, 0, 0))
        workspace.add(left_panel, weight=3)
        workspace.add(right_panel, weight=2)

        pair_list_frame = ttk.Frame(left_panel)
        pair_list_frame.pack(fill="both", expand=True)

        columns = ("source", "destination")
        self.tree = ttk.Treeview(pair_list_frame, columns=columns, show="headings", selectmode="extended")
        self.tree.heading("source", text="Source folder")
        self.tree.heading("destination", text="Destination folder")
        self.tree.column("source", width=260, minwidth=150)
        self.tree.column("destination", width=260, minwidth=150)
        tree_scroll = ttk.Scrollbar(pair_list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")

        # Keep pair-management buttons directly below the folder-pair list.
        controls = ttk.Frame(left_panel)
        controls.pack(fill="x", pady=(9, 0))
        ttk.Button(controls, text="Add pair", command=self.add_pair).pack(side="left")
        ttk.Button(controls, text="Remove selected", command=self.remove_pair).pack(side="left", padx=6)
        ttk.Button(controls, text="Save configuration", command=self.save).pack(side="left")

        log_header = ttk.Frame(right_panel)
        log_header.pack(fill="x", pady=(0, 5))
        ttk.Label(log_header, text="Latest log entries", font=("Segoe UI", 11, "bold")).pack(side="left")
        ttk.Button(log_header, text="Refresh", command=self.refresh_log).pack(side="right")

        log_frame = ttk.Frame(right_panel)
        log_frame.pack(fill="both", expand=True)
        self.log_text = __import__("tkinter").Text(
            log_frame,
            wrap="word",
            state="disabled",
            font=("Consolas", 9),
            background="#171717",
            foreground="#E5E5E5",
            insertbackground="#FFFFFF",
            padx=7,
            pady=7
        )
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

        log_actions = ttk.Frame(right_panel)
        log_actions.pack(fill="x", pady=(7, 0))
        ttk.Button(log_actions, text="Clear log", command=self.clear_log).pack(side="right")

        daemon_frame = ttk.LabelFrame(outer, text="Background daemon", padding=9)
        daemon_frame.pack(fill="x", pady=(9, 8))
        ttk.Label(daemon_frame, text="Run every (seconds):").pack(side="left")
        ttk.Spinbox(daemon_frame, from_=10, to=86400, increment=10, width=9, textvariable=self.interval).pack(side="left", padx=6)
        ttk.Button(daemon_frame, text="Start daemon", command=self.start_daemon).pack(side="left", padx=(12, 5))
        ttk.Button(daemon_frame, text="Stop daemon", command=self.stop_daemon).pack(side="left")
        ttk.Button(daemon_frame, text="Preview", command=lambda: self.run_now(dry_run=True)).pack(side="right", padx=(0, 6))
        ttk.Button(daemon_frame, text="Run now", command=self.run_now).pack(side="right")

        footer = ttk.Frame(outer)
        footer.pack(fill="x")
        ttk.Label(footer, textvariable=self.status).pack(side="left")
        ttk.Button(footer, text="Open log", command=self.open_log).pack(side="right")
        ttk.Label(
            outer,
            text="Source deletions are mirrored; on Windows, destination-only items go to the Recycle Bin by default.",
            foreground="#A33"
        ).pack(anchor="w", pady=(8, 0))

        self.refresh_log()
        self.root.after(1500, self.refresh_log)

    def refresh_log(self):
        """Show the most recent log lines; refreshes while the daemon runs."""
        try:
            if LOG_FILE.exists():
                with LOG_FILE.open("r", encoding="utf-8", errors="replace") as log_file:
                    lines = log_file.readlines()[-250:]
                content = "".join(lines)
            else:
                content = "No log entries yet. Run a synchronization or start the daemon."
        except OSError as exc:
            content = f"Could not read log file: {exc}"

        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", END)
        self.log_text.insert("1.0", content)
        self.log_text.see(END)
        self.log_text.configure(state="disabled")

        # Keep refreshing the viewer independently of the daemon process.
        if self.root.winfo_exists():
            self.root.after(1500, self.refresh_log)

    def refresh_pairs(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for index, pair in enumerate(self.config.get("pairs", [])):
            self.tree.insert("", END, iid=str(index), values=(pair["source"], pair["destination"]))

    def add_pair(self):
        source = filedialog.askdirectory(title="Select source folder")
        if not source:
            return
        destination = filedialog.askdirectory(title="Select destination folder")
        if not destination:
            return
        self.config.setdefault("pairs", []).append({"source": source, "destination": destination})
        try:
            self.config["pairs"] = validate_pairs(self.config["pairs"])
        except Exception as exc:
            self.config["pairs"].pop()
            messagebox.showerror("Invalid folder pair", str(exc))
            return
        self.refresh_pairs()
        self.save(silent=True)

    def remove_pair(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Remove pair", "Select at least one pair first.")
            return
        indexes = sorted((int(item) for item in selected), reverse=True)
        for index in indexes:
            del self.config["pairs"][index]
        self.refresh_pairs()
        self.save(silent=True)

    def save(self, silent=False):
        try:
            self.config["pairs"] = validate_pairs(self.config.get("pairs", []))
            interval = int(self.interval.get())
            if interval < 10:
                raise ValueError("The daemon interval must be at least 10 seconds.")
            self.config["interval_seconds"] = interval
            save_config(self.config)
            self.status.set(f"Configuration saved: {CONFIG_FILE}")
            if not silent:
                messagebox.showinfo("Saved", "Configuration saved successfully.")
            return True
        except Exception as exc:
            messagebox.showerror("Configuration error", str(exc))
            return False

    def run_now(self, dry_run=False):
        if not self.save(silent=True):
            return
        if not self.config.get("pairs"):
            messagebox.showinfo("Nothing to synchronize", "Add at least one folder pair first.")
            return
        self.status.set("Generating synchronization preview..." if dry_run else "Synchronization running...")
        def worker():
            try:
                result = run_sync(self.config, dry_run=dry_run)
                prefix = "Preview complete" if dry_run else "Finished"
                message = f"{prefix}. Copied: {result[0]}, updated: {result[1]}, deleted: {result[2]}"
                self.root.after(0, lambda: self.status.set(message))
            except Exception as exc:
                # Exception variables are cleared when the except block exits.
                # Capture the message now so the scheduled Tkinter callbacks
                # can safely use it later on the main thread.
                error_message = str(exc)
                self.root.after(
                    0,
                    lambda message=error_message: self.status.set(
                        f"Synchronization failed: {message}"
                    ),
                )
                self.root.after(
                    0,
                    lambda message=error_message: messagebox.showerror(
                        "Synchronization failed", message
                    ),
                )
        threading.Thread(target=worker, daemon=True).start()

    def daemon_pid(self):
        try:
            return int(PID_FILE.read_text(encoding="ascii").strip())
        except Exception:
            return None

    def refresh_daemon_status(self):
        pid = self.daemon_pid()
        lock_held = daemon_lock_is_held()
        if lock_held:
            if is_folder_mirror_daemon(pid):
                self.status.set(f"Background daemon running (PID {pid})")
            else:
                self.status.set(
                    "Background daemon active (lock held; process identity not verified)."
                )
        elif not getattr(self, "_daemon_start_pending", False):
            self.status.set("Background daemon stopped.")
        self.root.after(3000, self.refresh_daemon_status)

    def _read_recent_log(self, max_lines=20):
        try:
            if LOG_FILE.exists():
                with LOG_FILE.open("r", encoding="utf-8", errors="replace") as log_file:
                    return "".join(log_file.readlines()[-max_lines:]).strip()
        except OSError:
            pass
        return "No daemon log output was recorded."

    def _check_daemon_start(self, process, attempts_left=12):
        """Confirm that the child process initialized, or report why it exited."""
        pid = self.daemon_pid()
        if process.poll() is not None:
            self._daemon_start_pending = False
            details = self._read_recent_log()
            self.status.set(f"Daemon failed to start (exit code {process.returncode}).")
            messagebox.showerror(
                "Daemon failed to start",
                f"The background process exited before becoming active.\n\n"
                f"Exit code: {process.returncode}\n\nRecent log entries:\n{details}"
            )
            return

        if pid == process.pid and daemon_lock_is_held():
            self._daemon_start_pending = False
            if is_folder_mirror_daemon(pid):
                self.status.set(f"Background daemon running (PID {pid})")
            else:
                self.status.set(
                    "Background daemon active (lock held; process identity not verified)."
                )
            return

        if attempts_left > 0:
            self.root.after(
                500,
                lambda: self._check_daemon_start(process, attempts_left - 1)
            )
            return

        self._daemon_start_pending = False
        details = self._read_recent_log()
        self.status.set("Daemon startup could not be confirmed.")
        messagebox.showerror(
            "Daemon startup not confirmed",
            "The process is still running, but it did not register its PID. "
            "Check the log for details.\n\nRecent log entries:\n" + details
        )

    def start_daemon(self):
        if not self.save(silent=True):
            return
        pid = self.daemon_pid()
        if daemon_lock_is_held():
            if is_folder_mirror_daemon(pid):
                messagebox.showinfo("Daemon", f"The daemon is already running (PID {pid}).")
            else:
                messagebox.showwarning(
                    "Daemon already active",
                    "The daemon lock is held by another process, so a second daemon "
                    "will not be started. The recorded process identity could not "
                    "be verified; no process was terminated."
                )
            self.refresh_daemon_status()
            return
        # Launch the application entry point, not this GUI module.
        # gui.py only defines the interface; folder_mirror.py handles --daemon.
        script = str(Path(__file__).resolve().with_name("folder_mirror.py"))
        creationflags = 0
        if os.name == "nt":
            creationflags = (
                getattr(subprocess, "DETACHED_PROCESS", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            )
        try:
            ensure_app_dir()
            with open(LOG_FILE, "a", encoding="utf-8") as log:
                process = subprocess.Popen(
                    [sys.executable, "-u", script, "--daemon"],
                    cwd=str(Path(script).parent),
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=log,
                    creationflags=creationflags,
                    close_fds=(os.name != "nt")
                )
            self._daemon_start_pending = True
            self.status.set("Starting background daemon...")
            self.root.after(500, lambda: self._check_daemon_start(process))
        except Exception as exc:
            self._daemon_start_pending = False
            self.status.set("Could not start background daemon.")
            messagebox.showerror("Could not start daemon", str(exc))

    def stop_daemon(self):
        pid = self.daemon_pid()
        if not daemon_lock_is_held():
            self.status.set("Background daemon stopped.")
            messagebox.showinfo("Daemon", "No active daemon lock was found.")
            return
        if not is_folder_mirror_daemon(pid):
            messagebox.showwarning(
                "Daemon identity not verified",
                "The PID file does not point to a verified Folder Mirror daemon. "
                "For safety, no process was terminated. If a stale PID file exists, "
                "remove it only after confirming no Folder Mirror daemon is running."
            )
            return
        if os.name == "nt":
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
            if result.returncode != 0:
                messagebox.showerror("Could not stop daemon", result.stderr or result.stdout)
            else:
                self.status.set("Daemon stop requested.")
        else:
            os.kill(pid, 15)

    def clear_log(self):
        """Empty the log file and immediately refresh the log viewer."""
        try:
            logger = logging.getLogger("folder_mirror")
            for handler in logger.handlers:
                handler.flush()

            ensure_app_dir()
            with LOG_FILE.open("w", encoding="utf-8"):
                pass

            self.refresh_log()
            self.status.set("Log cleared.")
        except OSError as exc:
            messagebox.showerror("Could not clear log", str(exc))

    def open_log(self):
        ensure_app_dir()
        LOG_FILE.touch(exist_ok=True)
        try:
            os.startfile(str(LOG_FILE))
        except AttributeError:
            subprocess.Popen(["notepad.exe", str(LOG_FILE)])
