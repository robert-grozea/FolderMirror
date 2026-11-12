# Folder Mirror for Windows

A small Python/Tkinter application that mirrors multiple source folders into their corresponding destination folders.

## Features

- Add multiple source/destination folder pairs through a Windows folder picker.
- Recursively synchronize all files and subfolders, including empty directories.
- Copy new files and update changed files.
- Delete destination files and folders that no longer exist in the source.
- Run a one-time synchronization from the UI.
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
- Destination-only files are deleted.
- Empty destination subfolders are removed.

The application rejects source/destination paths that are identical or nested inside one another, to prevent recursive copying or accidental deletion. Symbolic links are skipped.

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
Ran 23 tests in 0.1s

OK
```

The exact number and duration may change as tests are added.

### What is tested

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
