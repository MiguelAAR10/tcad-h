# 07 — Worker Prompt: Tests Role

N/A — the backend worker (`05_worker_prompt_backend.md`) is responsible for
writing the tests in `backend/tests/unit/test_health.py` as part of the same
Work Package. No dedicated test worker is needed for this small WP.

If a future variant of this WP requires a dedicated test worker, this file
would be populated with the test plan and the production code worker prompt
would explicitly defer test authoring.
