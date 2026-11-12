# Validation: evidence workflow update

Validation uses local synthetic data and injected provider responses. It does not establish real institution
accuracy, calibrated confidence, production PostgreSQL locking or Redis/Celery worker-loss behavior.

- Frontend tests: 156 passing (includes pinned PDF download, no spending on reads, version isolation,
  consolidated sidebar and removal of obsolete navigation).
- TypeScript/Vite production build: passes; existing large-bundle advisory remains.
- Native PDF: authenticated export test verifies all 216 condition IDs, run/input identity and no inference.
  A full 45-page synthetic report was rendered and visually inspected, including an all-page contact sheet.
- Model/migration and whitespace checks: checked separately after implementation.
- Backend regression: **804 tests ran; OK, one skipped (803 passed)** for scoring, extraction, facts and accounts.
- Supplemental regression after final integrity/persistence changes: **46 tests passed**, including immutable
  extraction snapshots, capability snapshot storage and recommendation serialization.
- `manage.py check`: only the expected unconfigured AI key warning. `makemigrations --check --dry-run`:
  no pending model changes beyond the included extraction 0016 migration. `git diff --check`: clean.

The initial backend invocation used production HTTPS redirect defaults; those failures did not exercise the
changed API paths. CI uses DEBUG=True. The final isolated run uses equivalent HTTP test behavior and a fast
MD5 test password hasher; production password configuration is unchanged. PyMuPDF is the repository-pinned
1.28.2. A temporary newer reader installation pulled ONNX Runtime and attempted unnecessary telemetry; that
run was stopped by automatic approval review, and the unused dependency was removed before retries.

Browser smoke could not launch Chromium in the restricted runtime: graphics initialization terminated
before a page could be tested. No new Chromium pass is claimed. Run the included synthetic smoke script in
an environment with a working browser, then exercise actual uploaded documents in development. The 156
frontend tests include DOM checks but are not a replacement for browser acceptance.

Reproduce the backend checks with the repository CI's DEBUG=True HTTP test configuration. The fast local
run used an external, uncommitted test settings overlay selecting Django's MD5PasswordHasher only for test
users; use normal production hashing in the deployed app. Local SOCKS transport support and pytest were
installed for this environment's existing SDK-construction/vision tests. No runtime dependency changes
were required in the project.
