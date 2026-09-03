# Phase 5 retrieval evaluation v3

This synthetic, content-safe fixture implements the accepted ADR 0023 quality
contract. It contains 120 chunks and 80 judged queries split into 48 tuning, 16
validation, and 16 holdout cases. Each split covers semantic paraphrase, exact
identifier, multi-document, unanswerable, and unauthorized-scope behavior.

The document themes are reused from v2, but protected v3 query text, judgments, and
identifiers are new. The v2 holdout is not used to tune or score `hybrid-v2`.

Run the free integrity check with:

```bash
make phase5-evaluation
```

The manifest hashes all benchmark inputs. Validation must pass before the runner
retrieves or emits holdout results. Embedding the fixture is paid and remains behind
the explicit `--allow-paid-openai` boundary.
