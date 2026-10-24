# Contributing to YouTube Simple Downloader

Thanks for helping improve the project.

## Before opening an issue

- Check existing issues first.
- Use a public test URL only when you are allowed to share it.
- Never include cookies, login information, tokens, private URLs, or paid/private content details.
- The project does not accept features for login, cookies, private, paid, members-only, DRM-protected content, or bypassing access restrictions.

## Development setup

```powershell
git clone https://github.com/jasonsheu0425/YouTubeSimpleDownloader.git
cd YouTubeSimpleDownloader
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements\bootstrap.lock
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.txt -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
```

Run the checks before sending a pull request:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m compileall src tests
.\.venv\Scripts\python.exe tests\smoke_download.py --help
.\.venv\Scripts\python.exe scripts\check_dependency_locks.py
```

Keep changes focused, preserve the public-only scope, and include a clear explanation plus tests when behavior changes.

## Test data isolation

Ordinary `python -m pytest` uses shared, automatic fixtures in `tests/conftest.py`.
Application settings use an explicit per-test INI filename with fallbacks disabled;
history and download directories are per-test, and the FFmpeg runtime cache and
profile environment are session-owned pytest directories. Widgets are closed and
deleted before their settings fixture is released. No runner-specific adapter or
production registry reset is necessary.

Use `isolated_settings` and `isolated_settings_factory()` when inspecting or
reloading settings. Do not construct QSettings in test modules or redefine these
fixtures locally. On Windows, the organization/application constructor always
uses NativeFormat: `setDefaultFormat(IniFormat)`, `setPath()`, and changes to
APPDATA/LOCALAPPDATA do not redirect that constructor away from HKCU. The shared
factory instead uses the filename/IniFormat constructor. A source check runs
before test collection and rejects unsafe constructors and fixture shadowing:

```powershell
.\.venv\Scripts\python.exe scripts\check_test_isolation.py
```

This guard prevents accidental test regressions; it is not a sandbox for untrusted
Python. Real-download `tests/smoke_download.py` runs and manual/packaged GUI QA are
separate, explicitly authorized operations, not pytest cases. Real downloads need
isolated output/profile/cache paths; manual Windows GUI QA additionally needs a
dedicated account because environment variables cannot isolate HKCU. Capture a
read-only production-state baseline before such QA. Never clear or restore user
settings as a test cleanup step, or infer restoration without an exact baseline.
Older tags and worktrees do not inherit this fix automatically. Do not run their
GUI tests in a production Windows account; first integrate the isolation fix on
a reviewable branch, or use a disposable account.

## Reporting bugs

Include the app version, Windows version, whether you used the installed EXE or a development run, selected formats and processing mode, the exact friendly error message, and steps to reproduce. Screenshots and logs are useful after removing private information.
