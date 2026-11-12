# Step 4 validation — 30 October 2026

From the repository root, with the repository's backend dependencies installed:

```bash
SECURE_SSL_REDIRECT=False python backend/manage.py test apps.scoring apps.extraction --noinput
python backend/manage.py check
python backend/manage.py makemigrations --check --dry-run
git diff --check
```

Final result: **491 tests ran in 130.829 seconds; OK, 1 skipped** (490 passed).
Includes 20 new recommendation tests, Step 3 API/metering tests, capability arithmetic/storage tests,
and existing scoring/extraction regressions. The initial broad run omitted the documented HTTP test
setting and encountered HTTPS redirects; the corrected final run above passed.

Django model checks: no errors; only expected extraction.W001 for an unconfigured AI key.
Migration consistency: No changes detected. Whitespace check: clean.

No live provider calls, production migrations, merge or deployment. Tests use injected SDK responses,
temporary SQLite databases and mocked broker/router services. Existing pipeline tests also exercise
mocked Celery tasks; this does not establish real Redis/Celery or PostgreSQL concurrent behaviour.
The skipped test is inherited; see the packaged full log and test source.

Independent remote branch checks found A1 and main only, no visible engineer branch or open PR.
GitHub create-branch publishing returned integration 403; feature branch delivery is by bundle/patch.
