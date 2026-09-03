# Phase 6 visual/table evaluation v1

This committed tier is deterministic and contains only synthetic, redistributable
content. It freezes 40 independently locatable regions and 80 questions across
figure relationships, charts, table lookup, exact calculation, and negative cases.

The 60/20/20 tune, validation, and holdout split is enforced by canonical hashes.
Candidate code may inspect tune repeatedly. It may evaluate validation only after
its fingerprint and budgets are frozen, and may not retrieve, score, or emit holdout
results unless validation passes. The tracked baseline summary intentionally omits
holdout metrics and contains no result identities.

Private representative source files, judgments, and raw outputs belong only under
the ignored `evaluation/phase6/representative/` and `evaluation/phase6/results/`
paths. Paid/provider runs require separate explicit authorization.
