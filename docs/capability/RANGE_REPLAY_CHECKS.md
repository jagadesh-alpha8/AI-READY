# Wide-range arithmetic checks

This update extends the offline comparison command with per-indicator components, foundation/decision-state counts, full-width indicator counts and an explicitly labelled optimistic validator counterfactual. The comparison protocol is `range-replay-0.2`.

The code operates on a caller-supplied export and does not include institutional data. The generic tests construct their own decisions from the public rubric. They are mathematical boundary tests, not a pilot assessment or empirical rubric validation.

## Properties checked

- A supported assertion does not complete its unknown companion under cumulative scoring. Independent arithmetic can expose that partial credit without awarding a badge.
- Unknown evidence permits both outcomes. An unresolved population can therefore retain a 0–100 range without an arithmetic error.
- Optimistically treating validator-affected unknowns as met does not necessarily resolve other prerequisites. This counterfactual does not assert that the evidence supports those states.
- Explicit negative findings are never overwritten by the counterfactual. Arbitrary model prose is not classified as a validator error.
- Comparison does not mutate decisions or recast them as candidate findings. A mismatch with the saved result is reported, not silently repaired.
- New requirements need new adjudication and separate retrieval validation. Old ranked passages do not establish coverage of revised requirements.

Run from `backend` with project dependencies:

```sh
python -m unittest apps.scoring.test_range_replay \
  apps.scoring.test_experimental_ladder \
  apps.scoring.test_experimental_candidate \
  apps.scoring.test_experimental_candidate_command

python manage.py compare_capability_aggregation /path/to/assessment-export.json
```

The focused suite passes 36 tests. Full CI must pass on the final PR head before merge.

Merging these offline tools does not activate the candidate methodology or change production score ranges. No midpoint, unknown-to-zero conversion, automatic negative finding or badge threshold is introduced. A separate methodology release and evidence validation are required for live candidate scoring.
