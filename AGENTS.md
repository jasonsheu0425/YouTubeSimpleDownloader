# Workspace and test safety

- Before running tests, verify the current worktree, branch, changes, and test
  isolation with `python scripts/check_test_isolation.py` from this checkout.
- Use the current verified main or an explicitly reviewed descendant. Historical
  worktrees may contain tests that clear real Windows QSettings; do not run them.
- Never bypass a legacy-worktree test guard or assume APPDATA isolation changes
  the Windows HKCU registry. Do not touch production settings, history or downloads.
- Before retiring a worktree, inventory its changes and build artifacts and verify
  their preservation. Never clean, reset, overwrite, or remove unreviewed work.
- The Python test guard is not an OS sandbox; use a dedicated disposable Windows
  user context when tests need stronger operating-system isolation.
