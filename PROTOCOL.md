# TCAD-H Protocol v2.4

**TCAD-H** = Task Contextualization and Agentic Development — Handoff edition.
A local-first Multi-CLI Development Harness for coordinating software work across multiple coding agents (Claude Code, OpenCode, Kimi, Qwen, DeepSeek, GPT, Minimax) without losing context, breaking the system, or burning tokens on rework.

---

## What TCAD-H is

A protocol that converts human intent into versioned **Work Packages** that any coding CLI can execute, then converts the resulting code changes into **evidence + maps** that humans and reviewers can inspect without reading every diff line.

It is composed of:

- A **Conductor Agent** that drives a finite state machine through phases.
- A **Handoff Protocol** that produces self-contained Work Package folders.
- A **Boundaries layer** that defines what each agent can and cannot touch.
- A **Journal** that records what happened, sharded and indexable.
- A **Development Atlas** (Phase 2.5+) that visualizes structure and impact.
- A **Questions Protocol** that converts evidence into blocking questions before progress.

## What TCAD-H is NOT

- Not an API broker. Not a token router. You operate via CLI tools on subscriptions.
- Not a chat-history pipeline. Models never receive conversation history; they receive versioned artifacts.
- Not autonomous. Humans approve transitions on high-risk steps.
- Not yet-another-prompt-collection. Every doctrine is paired with executable scripts or it does not ship.
- Not a dashboard. UI is Phase 4, only after the artifact pipeline produces real evidence.

## The 5 questions every change must answer

Every Work Package must explicitly answer:

1. **What is being built?** → `01_goal.md`
2. **What can the agent touch?** → `02_allowed_files.md`, `03_forbidden_files.md`
3. **What actually changed?** → `15_diff.patch`, `16_code_graph.json`
4. **What impact does it have?** → `18_impact_map.md`, `19_mermaid.md`
5. **What should the human review or ask before accepting?** → `20_reviewer_focus.md`, `21_open_questions.md`

If a phase cannot answer its question, it does not graduate.

## Artifact map

| Artifact | Owner | Phase | Purpose |
|---|---|---|---|
| `AGENTS.md` | Human | Phase 0 | Universal agent entry point (Linux Foundation spec) |
| `CLAUDE.md` | Human | Phase 0 | Claude Code as Conductor instructions |
| `OPENCODE.md` | Human | Phase 0 | OpenCode as Worker instructions |
| `.protocol/method.md` | Human | Phase 0 | Formal TCAD-H method specification |
| `.protocol/conductor.yaml` | Human | Phase 0 | Conductor Agent FSM spec |
| `.protocol/boundaries.yaml` | Human | Phase 1 | Allow/deny zones per repo |
| `.protocol/status.json` | Conductor | Phase 1+ | Live FSM state |
| `.protocol/handoffs/WP-NNN/` | Conductor + Worker + Reviewer | Phase 1+ | Work Package folder |
| `.protocol/questions/INDEX.md` | Conductor | Phase 1+ | Global blocking questions |
| `.protocol/journal/YYYY-MM-DD-NNN.md` | Conductor | Phase 2+ | Per-task journal entry (sharded) |
| `.protocol/atlas/` | Atlas scripts | Phase 2.5c+ | Cross-WP composed graph |

## Phase ladder

| Phase | Goal | Deliverable | Status |
|---|---|---|---|
| **1** | Handoff MVP | Conductor can generate a Work Package | **CURRENT** |
| **1.5** | Conductor FSM | `tcad_conduct.py` enforces state transitions | Next |
| **2** | Evidence capture | `tcad_log.py` produces diff + summary + journal | |
| **2.5a** | Static graph | `tcad_graph_static.py` produces deterministic code graph | |
| **2.5b** | Semantic graph | LLM enriches with capabilities + risks | |
| **2.5c** | Atlas | Cross-WP composed view + heatmap + timeline | |
| **3** | Reviewer focus + contract gates | Reviewer reads compressed brief, not full diff | |
| **4** | TCAD Studio | Localhost visual interface | |
| **5** | MCP / Drive | External integrations | |

## Iron rules

1. **No model receives conversation history.** All inputs are versioned protocol artifacts.
2. **The Conductor never writes production code.** It writes plans, prompts, briefs, journal entries.
3. **The Reviewer is never the Implementer.** Different CLI or model. No self-validation.
4. **Open blocking questions halt progress.** Resolve via `.protocol/questions/` before transitioning state.
5. **No file is edited outside `02_allowed_files.md` of the active Work Package.** Boundaries are enforced, not suggested.

## Quickstart

```bash
# Create a new Work Package from a goal
python scripts/tcad_handoff.py \
  --name "add-health-endpoint" \
  --goal "Add a /health endpoint returning 200 for uptime checks" \
  --role backend

# Inspect the generated package
ls -1 .protocol/handoffs/WP-001-add-health-endpoint/

# Hand off to a worker CLI (example: OpenCode)
opencode --read .protocol/handoffs/WP-001-add-health-endpoint/05_worker_prompt_backend.md

# After worker completes, capture evidence (Phase 2)
# python scripts/tcad_log.py .protocol/handoffs/WP-001-add-health-endpoint/   [Phase 2]

# Update Conductor state
# python scripts/tcad_conduct.py transition REVIEWING   [Phase 1.5]
```

## Versioning

- v1 (legacy) — preserved at `AGENTS_v1.md`, `TCAD_FRAMEWORK.md`, `CAVEMAN_LOG.md`, `CONTRACT_GATES.md`, `PHASE_CARDS.md`.
- v2.4 (this) — current.
- See `.protocol/method.md` for the formal method spec.
