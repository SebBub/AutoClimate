# AutoKlima

## Local Python environment

This machine has no Python on PATH by default (`python` resolves to the Microsoft
Store app-execution-alias stub and fails). A working interpreter exists at:

- `C:\Users\Sebastian\.conda\envs\autoklima-test\python.exe` (Python 3.12.13, conda env `autoklima-test`)

`.claude/settings.local.json` (gitignored, machine-specific) prepends this env and its
`Scripts` folder to `PATH` for Claude Code sessions in this project, so plain `python`/`pip`
should resolve to it — this takes effect on session start/restart, not mid-session.

As of 2026-08-21 this env has no `pip` installed (`python -m pip` fails with "No module
named pip") and none of `requirements.txt` is installed yet. Bootstrap before relying on it:
`python -m ensurepip` (or `conda install pip` in the env), then `pip install -r requirements.txt`.

This project otherwise only runs via GitHub Actions (`.github/workflows/daily-report.yml` on
Python 3.12) — the local env is for manual testing/debugging only.
