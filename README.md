# Folder Mirror for Windows

A small Python/Tkinter application that mirrors multiple source folders into their corresponding destination folders.

## Features

- Add multiple source/destination folder pairs through a Windows folder picker.
- Recursively synchronize all files and subfolders, including empty directories.
- Copy new files and update changed files.
- Delete destination files and folders that no longer exist in the source.
- Preview pending changes without modifying files (dry run).
- Move destination-only items to the Windows Recycle Bin by default instead of permanently deleting them.
- Start an independent background daemon from the UI.
- Configure the daemon interval (minimum 10 seconds).
- Stop the background daemon from the UI.
- View the latest log entries in the GUI and clear the log.
- Configuration is stored in `%APPDATA%\\FolderMirror\\config.json`.
- Logs are written to `%APPDATA%\\FolderMirror\\folder_mirror.log`.

## Requirements

- Windows 10 or Windows 11
- Python 3.10 or newer, with Tcl/Tk (the standard python.org installer includes Tkinter)
- No third-party Python packages are required.

## Run

1. Install Python from https://www.python.org/downloads/windows/ if it is not already installed.
2. During installation, enable **Add Python to PATH** and the Tcl/Tk option.
3. Extract the complete ZIP, keeping all `.py` files together in the same folder.
4. Double-click `run_gui.bat`.

You can also run it from PowerShell:

```powershell
py -3 .\\folder_mirror.py
```

## Independent daemon / command line

The daemon is a separate process and continues running after the UI is closed.

<<<<<<< HEAD
=======
- Start from the UI using **Start daemon**.
- Stop from the UI using **Stop daemon**.
- Preview a synchronization without changing files:

```powershell
py -3 .\\folder_mirror.py --run-once --dry-run
```

- Run one synchronization cycle without opening the UI:

>>>>>>> 479c71eb3fba6f99ab1012a49eb1360d4b28bb46
```powershell
py -3 .\\folder_mirror.py --run-once
```

- Run the daemon manually in a console:

```powershell
py -3 .\\folder_mirror.py --daemon
```

For automatic startup after Windows sign-in, create a shortcut to `run_daemon.bat` in the Windows Startup folder (`Win + R`, then `shell:startup`).

## Important mirror behavior

This is a one-way mirror, not a versioned backup:

- Source-only files are copied to the destination.
- Changed source files overwrite their destination copies.
- Destination-only files and folders are moved to the Windows Recycle Bin by default. On non-Windows systems, deletion is permanent.
- Empty destination subfolders are removed.
- Use **Preview** in the GUI or `--run-once --dry-run` to inspect the planned copy/update/delete counts without changing files.

<<<<<<< HEAD
The application rejects source/destination paths that are identical or nested inside one another, to prevent recursive copying or accidental deletion. Symbolic links are skipped.
=======
**A deletion in the source is propagated to the destination.** Do not use a destination folder containing unrelated files. Test with disposable folders before pointing the app at important data.

The application rejects source/destination paths that are identical or nested inside one another, to prevent recursive copying or accidental deletion. Source symbolic links are skipped. Synchronization fails closed if the destination tree or any destination ancestor contains a symbolic link, junction, or other Windows reparse point.

### Deletion behavior

On Windows, destination-only items are sent to the Recycle Bin by default. The setting is stored in `%APPDATA%\\FolderMirror\\config.json` as `"deletion_mode": "recycle_bin"`. To permanently delete destination-only items instead, stop the daemon and change this value to `"permanent"`. The next daemon cycle reloads the setting. On non-Windows platforms, the default is permanent deletion.

### Daemon process safety

The GUI checks the recorded PID against the running executable and command line before treating it as Folder Mirror or stopping it. If the process identity cannot be verified, the GUI refuses to terminate it.
>>>>>>> 479c71eb3fba6f99ab1012a49eb1360d4b28bb46

## Notes

- Synchronization is sequential; each configured pair is processed in order.
- A failed copy/delete is logged and stops that synchronization cycle.
- File comparison uses file size and modification timestamp. This is efficient for normal folder mirroring; it is not a cryptographic content verification.
- The daemon reloads the saved configuration on each cycle.


## Running the unit tests

Folder Mirror includes a standard-library `unittest` test suite. No test
framework or additional package needs to be installed.

1. Stop the background daemon and close the Folder Mirror GUI.
2. Open PowerShell in the extracted project folder (the folder containing
   `folder_mirror.py`).
3. Run:

```powershell
py -3 -m unittest discover -s tests -v
```

The `-v` option prints each test name and its result. A successful run ends
with output similar to:

```text
The exact test count and duration may change as tests are added.

OK
```

The exact number and duration may change as tests are added.

### What is tested

- Destination symlink/junction rejection and source symlink skipping.
- Dry-run preview does not modify files.

- Configuration defaults, saving/loading, and invalid JSON handling.
- Validation of source and destination paths, including overlapping paths.
- Copying new files and updating changed files.
- Creating nested and empty directories.
- Removing destination-only files and directories.
- Replacing a destination file with a directory and vice versa.
- Idempotence: a second sync with no changes should do no work.
- Rejection of unsafe source/destination overlap.

### Run a single test module

```powershell
py -3 -m unittest tests.test_config -v
py -3 -m unittest tests.test_sync -v
```

### Run tests from Command Prompt

The same commands work in `cmd.exe`, provided Python's `py` launcher is
installed and the current directory is the project folder.

### Safety of the tests

Tests create temporary source and destination folders under the operating
system's temporary directory. They do not read or modify your configured
Folder Mirror pairs or your `%APPDATA%\\FolderMirror\\config.json`.
The temporary test folders are cleaned up automatically.
