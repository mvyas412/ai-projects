# Operations contracts

Current mode: the existing inspection demo is retained under ADR 0065 and
[`phase11-demo-v1.json`](phase11-demo-v1.json). Phase 11 acceptance was merged in
PR #31 (`768a67f`). Worker stopped/restart-no; existing Phase 10 maintenance unchanged;
no new paid calls or resources. Inspect existing READY documents and saved answers/
citations only. Worker stop does not disable API chat; this is an operator restriction,
not a new runtime interlock. Follow the [demo runbook](../docs/DEMO_RUNBOOK.md).
Frozen acceptance/rehearsal evidence is historical and must not be regenerated to
record this disposition. Aggregate-evidence manual retention review is November 17;
automatic product-data deletion and retention apply remain disabled.

## Unchanged Phase 10 contracts

`phase10-policy.json` is the tracked, provider-neutral form of accepted ADRs 0051–0056.
Validate it with `make phase10-policy-check`. The accepted learning thresholds mark an
oldest queue item of 15 minutes or a certificate with 14 days or less remaining as
critical; changing either value requires a reviewed policy update.

Keep exact plans, cloud inventory, backup names, private URLs, host identifiers and all
credentials under ignored `operations/private/`. Keep generated evidence under ignored
`evaluation/phase10/results/`. Only aggregate, content-free evidence may be copied into a
reviewed release record.

The operational validator supports:

- non-destructive backup-retention plans;
- encrypted-backup and isolated-restore evidence;
- preview-only application-retention reports;
- grouped maintenance and urgent-vulnerability classification;
- capacity, backup-age, certificate, queue and unexpected-cost checks;
- plan-first upgrade/rollback checks; and
- the final Phase 10 evidence gate.

None of these commands enables application-data deletion, upgrades a host, creates cloud
resources, or authorizes a plan. Those actions retain their explicit approval boundary.
