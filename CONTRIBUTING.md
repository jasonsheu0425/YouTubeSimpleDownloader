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
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip install -e .
```

Run the checks before sending a pull request:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m compileall src tests
.\.venv\Scripts\python.exe tests\smoke_download.py --help
```

Keep changes focused, preserve the public-only scope, and include a clear explanation plus tests when behavior changes.

## Reporting bugs

Include the app version, Windows version, whether you used the installed EXE or a development run, selected formats and processing mode, the exact friendly error message, and steps to reproduce. Screenshots and logs are useful after removing private information.
