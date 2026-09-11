# GitHub Actions Pin Policy

Every external GitHub Action used by this repository is pinned to a reviewed,
full 40-character commit SHA. The inline comment beside each `uses:` reference
records the upstream release that was reviewed for that commit.

| Action | Reviewed release | Immutable commit |
| --- | --- | --- |
| `actions/checkout` | `v7.0.1` | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| `actions/setup-python` | `v7.0.0` | `5fda3b95a4ea91299a34e894583c3862153e4b97` |
| `actions/setup-node` | `v7.0.0` | `820762786026740c76f36085b0efc47a31fe5020` |

The pin checker validates every YAML workflow under `.github/workflows` without
network access:

```powershell
.\.venv\Scripts\python.exe scripts\check_workflow_action_pins.py
```

To update a pin, review the upstream action release and its source, confirm
that its tag resolves to the intended commit in the action's own repository,
then update the workflow reference, this table, and the checker mapping in the
same reviewed change. Do not replace a SHA with a mutable branch, major tag, or
minor tag.
