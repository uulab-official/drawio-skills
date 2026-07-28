# Contributing

Thank you for helping make deterministic diagram tooling better.

## Before opening a change

1. Open an issue for schema changes, new importers, or output compatibility changes.
2. Keep the skill instructions concise; move detailed material into a directly linked reference.
3. Keep JSON compilation standard-library-only. Optional format adapters may use clearly declared dependencies.
4. Add tests for every defect fix and for all new IR behavior.
5. Do not add shape libraries, logos, or third-party assets without documenting their license and provenance.

## Local checks

```bash
python3 -m unittest discover -s tests -v
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  skills/drawio-diagram-engineer
```

Run `compile` twice for new fixtures and assert byte-identical `.drawio` output. Run `validate --strict` against the result.

## Commit and pull request guidance

Use focused commits. Explain user-visible behavior, compatibility impact, test coverage, and any generated artifacts in the pull request. Never include secrets, customer diagrams, or proprietary architecture samples.
