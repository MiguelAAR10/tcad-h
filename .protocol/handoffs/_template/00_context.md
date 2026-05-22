# 00 — Context

<!--
The Conductor fills this section. The worker reads it to understand the surrounding
state of the project before touching anything. Keep it factual and grounded in
files that already exist in the repo. No invented capabilities.
-->

## Project at a glance

(One paragraph: what does the system do, who uses it, where is it deployed.)

## Active spec

(Link or paste: `specs/<id>/spec.md` title and one-line summary.)

## Related prior work

(Last 3 relevant journal entries by id and date, with a single-line takeaway each.)

- `.protocol/journal/YYYY-MM-DD-NNN.md` — (takeaway)
- `.protocol/journal/YYYY-MM-DD-NNN.md` — (takeaway)
- `.protocol/journal/YYYY-MM-DD-NNN.md` — (takeaway)

## Existing components likely to be reused

(List paths. Worker should extend, not duplicate.)

- `path/to/file` — (what it already does)

## Contracts that must not break

(Pydantic models, OpenAPI schemas, TS interfaces, DB schemas.)

- `path/to/contract` — (which consumers depend on it)

## Reuse score

(Number 0.0–1.0. Conductor estimate. ≥0.6 unlocks AUTO_GO if other gates hold.)

`reuse_score: 0.0`
