# 📦 Legacy — TCAD v1 (pre-protocol)

These are the original markdown standards Miguel wrote before TCAD-H
became an executable harness. They are preserved for context, not for
use.

The current protocol lives in [`../docs/PROTOCOL.md`](../docs/PROTOCOL.md).

| Legacy file | Replaced by |
|---|---|
| `AGENTS_v1.md`        | [`../AGENTS.md`](../AGENTS.md) (Linux Foundation spec) |
| `TCAD_FRAMEWORK.md`   | [`../docs/PROTOCOL.md`](../docs/PROTOCOL.md) |
| `CAVEMAN_LOG.md`      | `.protocol/journal/` sharded entries |
| `CONTRACT_GATES.md`   | `scripts/tcad_review.py` + `tcad_check_boundaries.py` |
| `PHASE_CARDS.md`      | `tcad_handoff.py` lean WP + `.tcad_wp.json` metadata |

They are kept because they capture the original design intent and the
problems the v1 was trying to solve. Useful for understanding why the
current protocol looks the way it does.
