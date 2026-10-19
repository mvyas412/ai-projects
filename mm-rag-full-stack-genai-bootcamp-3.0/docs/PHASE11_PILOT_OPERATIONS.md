# Phase 11 pilot operations

Status: **Phase 11 accepted; acceptance records merged; existing inspection demo retained**

## Current demo disposition — October 18

Acceptance records were squash-merged in PR #31 at `768a67f`, with 460 CI tests
passing/4 skips and 83.59% coverage. No deployment or release tag accompanied the
merge. The subsequent [ADR 0065](architecture/decisions/0065-postpilot-demo-operating-mode.md)
and [`phase11-demo-v1.json`](../operations/phase11-demo-v1.json) retain the existing
deployment for inspection-only demonstrations: worker stopped/restart-no, existing
maintenance unchanged, no new paid calls or resources. Follow the
[demo runbook](DEMO_RUNBOOK.md), not the historical paid-proof/startup recipes below.

Existing authorized accounts may inspect READY documents and saved answers/citations.
No new questions, uploads, retries/reprocessing, connector sync, worker start, access
expansion, upgrades or new cloud resources are approved. A stopped worker does not
block paid chat/query embeddings; the restriction is operator-controlled, not a new
runtime/UI interlock. Preserve current backup/capacity schedules, private encrypted
backup destination, cost guards, backup-resume fix and manual-retention safeguards.
Scheduled backup quiescence can briefly interrupt access; no production SLA is claimed.

Last verified deployed revision remains `dba88de`, schema `0019`; this documentation
update is not a fresh host-health audit or deployment. Phase 5 closed without quality
acceptance, five-/ten-user validation is deferred/unvalidated and Next.js unpromoted.
Historical OCI USD 0 is operator-reported, not a future zero-cost guarantee. Review
aggregate-evidence retention manually November 17; no automatic product-data deletion.
The operator subsequently explicitly approves commit/push of these demo documentation
and diagram changes after the free verification gate. This source-only approval
does not authorize a new PR/merge, tag, deployment, service/access change or paid work.

### Approved source-only security remediation in PR #32

The operator separately authorizes fixing the failed dependency scans, committing/
pushing to the existing PR and reviewing CI again; no merge or deployment. Source
patches pin Docling/docling-slim `2.132.0`, Next.js `16.3.8`, sharp `0.35.5` and
source-map-js `1.2.2`, with required related transitive updates only. The Docling
package guard follows the new package pin while preserving the original model-tree
checksum and local-only/PDF extraction controls. Existing deployed revision/digests,
worker stop/restart-no, maintenance schedules, providers and frozen pilot evidence
remain untouched. Keep the original HIGH/CRITICAL security thresholds and publication
approval boundary; do not silence findings or treat local tests as a clean image scan.

## Historical acceptance and closure checkpoints

The dated authority and pending statements below retain their original checkpoint
meaning. The merged acceptance and current demo disposition above supersede pending
publication/disposition statements; frozen acceptance and review evidence is unchanged.

## October 18 explicit acceptance

The operator explicitly approved recording the limited acceptance at
`2026-10-18T23:10:45Z` (October 18 Pacific): **Phase 11 accepted for the two-person
learning pilot. Five- and ten-user product validation stages are deferred and remain
unvalidated.** The current decision is recorded in
`operations/phase11-acceptance-v1.json`; the earlier scope-only approval contract and
frozen rehearsal/review evidence remain unchanged historical records.

Acceptance adopts the closure review below, including guided-workflow and wider saved
document-scope limitations, direct/operator-relayed human feedback, historical versus
fresh safeguard evidence, actual OpenAI USD 0.00151422/six requests, and OCI USD 0 as
operator-reported rather than independently audited. No production, larger-cohort,
unassisted-discovery or fresh live negative-isolation claim follows.

Worker remains stopped/restart-no and existing Phase 10 maintenance remains unchanged.
No participant expansion, paid call, service/access/cloud mutation, Git publication,
merge or release tag is authorized. Post-pilot access/service disposition is separate.
The 30-day aggregate-evidence retention period now runs to November 17, 2026
(`2026-11-17T23:10:45Z`); removal requires reviewed manual action. No automatic deletion,
retention apply or reminder was created. Earlier dated pending/not-accepted statements
below describe their checkpoints and are superseded only by this final decision.

The operator subsequently separately approves committing and pushing these acceptance
records on the existing Phase 11 branch, after the required free verification gate.
That publication approval does not authorize merging, release tags, service changes
or paid work. The acceptance JSON retains the earlier decision's narrower authority;
the subsequent publication approval does not rewrite that historical boundary.

The October 18 pre-publication `make check` completes successfully: 448 tests pass,
16 expected skips, lint and typing (232 source files) pass, protected evaluation/
deployment contracts pass, schema head remains `20260919_0019` and no drift is detected.
Offline dependency mode and the previously verified public tokenizer cache are used;
no dependency upgrade or paid call occurs. Runtime/integration boundaries are unchanged,
so this documentation/contract publication does not rerun the live-service gate.

## October 18 limited closure review

The operator confirms that only MM-RAG used the provider project on October 8 UTC
and reports no OCI cost in response to the pilot-period infrastructure-cost question.
Record OpenAI actual exported cost **USD 0.00151422** (two chat/four embedding requests)
and OCI **USD 0, operator-reported**. Attribution is corroborated by matching saved
chat counts/tokens and unchanged upload/question aggregates. This is not a minute-level
provider audit or independently verified OCI bill/complete cloud-resource inventory.
Do not leave reported zero labeled unknown, or present it as independently audited.

The retrospective human ledger uses one authorized participant PDF-to-ready-to-answer/
citation workflow as its unit: **two attempted, two completed, 100%**, meeting the
90% threshold for these bounded actual-selected-document workflows. Both uploads and
both questions are included; return visits/component steps are not added to inflate
the denominator. The operator reports no further failed/repeated/extra attempts and
database/job/provider aggregates corroborate the two submitted workflows. Unanswered
draft conversations are not submitted question attempts. Optional ratings and earlier
technical cancel/retry/revocation scenarios are not counted as human journeys.
The first saved selection included two authorized documents: intended Webb-only
selection is not proved, even though the answer/citations complete the actual selected
scope. Preserve this intent/scope limitation, guided assistance of unquantified amount,
and direct/operator-relayed usability feedback; do not claim unassisted discovery.

The eligible October 7–11 observation checkpoint exceeds 72 hours with both people
active and no additional pauses/incidents reported; older recovery/unverified time
is excluded. Both final personal usability/persistence checks complete October 18.
The eight safeguard groups are assessed passing with their stated evidence boundaries:
consent; authorization/isolation; privacy; grounding/integrity; backup/recovery;
rollback; capacity/bounded execution; and cost. Fresh October 18 health/backup/timer/
queue/worker checks supplement protected authorization/isolation and accepted Phase 10
restore/rollback proof. September 20–21 recovery proofs remain within the 31-day drill
interval; no new restore is claimed. The local rollback-ready template is not live
pass evidence. Free checks and independently permitted read-only schema checks pass;
the `make check` shell exit itself remains sandbox-blocked, as recorded below.

The ignored limited-closure review recommends **acceptance for the existing two-person
guided learning pilot**, subject to an explicit operator decision acknowledging these
limitations and the operator-reported OCI cost. Phase 11 is **not yet accepted**.
Five-/ten-user validation remains deferred and unvalidated. No production SLA, broader
adoption or fresh negative live-tenant audit is claimed. Worker remains stopped and
maintenance unchanged. Git publication, post-pilot service/access disposition and any
new operational/paid action remain separately gated. No retention clock or deletion
is started before actual closure. The earlier checkpoints below remain historical.

## October 18 actual provider usage recovered

After renewed provider sign-in, the one-project October 8 UTC dashboard records two
chat requests with 3,307 input and 85 output tokens, matching the saved pilot answers,
and four embedding requests with 2,771 input tokens. Distinct embedding requests do
not imply automatic retries. A privately retained cost CSV confirms the exact daily
interval `[2026-10-08T00:00:00Z, 2026-10-09T00:00:00Z)` and actual project-day spend
of **USD 0.00151422**. This is provider-exported cost, not a token-rate estimate;
the overview's `$0.00` is a rounded display, not exact zero. The CSV and identifiers
stay outside Git; the ignored aggregate reconciliation retains its checksum.

The daily export is broader than the bounded approximately 02:08–02:46 UTC session.
Until unrelated same-project activity is excluded, record the daily amount as a
session upper bound, not an exactly attributed session charge. Operator exclusivity
confirmation and existing OCI aggregate cost/resource evidence are requested.
The export initially opened a prepared-file dialog rather than starting a download;
that dialog was inspected and its one-day file downloaded without a duplicate export.
This resolves provider authentication and missing daily usage/cost access, not every
cost or acceptance gate. Full journey/safeguard reconciliation, infrastructure cost
and explicit final acceptance remain open. No model call, runtime change or Git
publication occurred. The earlier checkpoint below remains a historical snapshot.

## October 18 read-only closure checkpoint

Strict SSH checks at `2026-10-18T22:57:01Z`–`22:57:30Z` pass eight running services,
unchanged `dba88de`/schema `20260919_0019`, worker exited zero/restart-no with its
October 7 finish unchanged, no active jobs or queue consumers, empty queues and
one-attempt/zero-SDK-retry controls. Core host services are active, SELinux enforcing,
failed units zero, maintenance timers enabled/waiting and their last runs successful.
Capacity passes with a 217-second-old sample: CPU 2.49%, memory 31.83%, disk 43.38%,
inodes 1.49%, certificate 60.16 days. The owner-only encrypted backup is 10.35 hours
old, with valid header and checksum matched to successful upload evidence; no
plaintext staging remains. Public UI/TLS/dependency readiness/anonymous 401 pass.
These are point-in-time checks, not continuous uptime or fresh restore proof.

Read-only aggregates retain two ready uploads across two accounts/workspaces, two
succeeded single-attempt jobs, no failed session jobs and two saved question/answer
pairs. Eleven successful scheduled backup-upload records and no nonpassing records
occur in the reviewed journal window. Chat totals remain 3,307 input/85 output tokens,
excluding embeddings; actual provider request counts and charges remain unknown.
Two completed guided primary workflows are not a reconciled denominator for every
attempted core journey. Preserve the first answer's wider two-document scope and
the direct/operator-relayed feedback qualifications.

Free local checks pass lint, typing (232 files), 446 tests (16 skipped), protected
contract stages and separately permitted read-only local schema head/no-drift checks.
The `make check` process stopped at sandbox database access; its exit is not reported
as success. Two benchmark tests initially needed the missing public tokenizer cache;
the SDK-pinned asset checksum was verified before the successful rerun. No model
API calls, upgrades, migrations or fresh live negative-isolation proof are claimed.

The recovery key is available, but the provider dashboard reports its previous
authentication token invalidated; a new sign-in handoff is open. Actual provider
usage/cost, fresh infrastructure billing/resource evidence, full journey/safeguard
reconciliation and explicit acceptance remain required. Unknown cost is not zero.
No runtime/cloud/access change or Git publication occurred during these checks.

## October 18 final participant checks

After the page reports an invalid session, the operator reports signing into the
own account and the assigned PDF Ready. Browser inspection verifies Ready, one
version/successful attempt one of one, two saved messages and the unchanged answer
with its matching citation-one/page-two excerpt. The saved chat labels scope
`Documents` without displaying the selected-document count; preserve the prior wider
scope observation. The operator subsequently personally confirms reading the answer
and citation, working keyboard navigation and understandable document scope. Record
the guided operator check complete, not unassisted discovery or a changed scope.
The operator then relays the second participant's own-account review: PDF Ready,
saved answer/citation readable, keyboard navigation working and scope understandable.
Browser inspection verifies one Library document/one ready, one version/succeeded
attempt one of one, two saved messages and citation one/page two containing the
unchanged characteristics table. All eight visible citations name the assigned PDF.
Both final participant checks are complete, with human usability attributed to the
direct report/operator relay rather than agent operation. Guided checks are not full
negative-isolation or unassisted-discovery proof. Public-only proof stays outside Git.
No new question/upload, feedback submission, host audit or service change. Actual
usage/cost, complete journey/safeguard reconciliation and final acceptance remain open.

## October 11 closure checkpoint

Both participants are reported available; the loaded recovery key permits strict
read-only host checks at `2026-10-12T02:24:40Z` and supplement at `02:24:47Z`
(October 11 Pacific). Eight services run at unchanged `dba88de`/schema `20260919_0019`.
Worker remains exited zero/restart-no with its October 7 finish time unchanged;
jobs and two queues are empty with no consumers. Core host services, enforcing SELinux,
zero failed units, both maintenance timers, capacity and the one-attempt/zero-retry
configuration pass. The 13.9-hour-old owner-only encrypted backup has a valid header
and checksum matched to successful upload evidence; no plaintext staging remains.
The permanent backup fix, Compose hash and current-boot override remain intact.
Public UI/TLS/API dependency readiness and anonymous denial pass. No fresh restore,
cloud-resource inventory or infrastructure billing check is claimed.

Read-only database aggregates at `02:26:59Z` still show exactly two new documents and
ready versions, two succeeded single-attempt jobs and two question/answer pairs across
two workspaces. The operator reports no additional incidents, manual pauses, failed/
repeated attempts or uploads/questions since resumption. About 96.3 hours have elapsed;
four successful scheduled backup uploads are recorded, with no nonpassing evidence in
the reviewed journal window. This is not continuous-uptime proof; normal scheduled
maintenance remains distinct from uninterrupted availability. Final personal
Ready/saved-citation/keyboard-focus/scope-clarity checks and the complete human journey
ledger remain pending.

The operator reports provider usage/cost details unavailable. Persisted chat totals
are 3,307 input and 85 output tokens, but omit embedding requests and do not establish
actual provider charges; the enterprise usage ledger has no session entries. No zero
cost or complete request count is inferred. Recover private aggregate billing/usage
evidence before final acceptance. Fifty-five focused local authorization/object/source/
citation/provenance/retry/pilot tests pass with one skip; these are current-checkout
checks, not new live negative-isolation or restore proof. Historical Phase 10 acceptance
supports the recovery evidence mapping; its local `rollback-drill.json` ready template
is not relabeled as a live pass. Full safeguard reconciliation, human evidence and
actual usage/cost remain open. No paid call, service/cloud change or Git publication.

## Accepted two person closure scope

October 11: the operator explicitly approved
[ADR 0064](architecture/decisions/0064-two-person-pilot-closure-scope.md). Phase 11's
closure objective is the existing two-person learning pilot, with five-/ten-user
validation deferred and unproven. ADR 0062's original mandatory stage completion is
amended only for this limited objective; all other acceptance gates remain intact.
Phase 11 stays in progress and is not accepted. The separate
`operations/phase11-closure-scope-v1.json` records scope approval without execution or
final-acceptance authority. Historical policy/evidence and runtime are unchanged.

The next closure checks are pause-adjusted duration, the human attempted/completed
journey ledger, targeted accessibility/scope clarity, actual aggregate usage/cost,
full safeguard mapping and fresh read-only health. The time floor has passed, not
the evidence gates. No additional paid question/upload is authorized or necessary
for the next read-only follow-up. Optional ratings remain voluntary. Scope approval
and final acceptance are separate decisions; neither authorizes Git publication or
service/access/cloud changes. The October 9 review below remains a historical snapshot;
its larger-stage closure blocker is now deferred by ADR 0064, not completed. All other
evidence gaps remain open until reviewed results resolve them.

## Formal canary review — October 9

The read-only review is complete with an **incomplete evidence / not accepted** outcome,
not a product-failure finding. Two distinct people's guided uploads/questions, original
source/citation checks, Day 2/3 persistence checks and participant-reported feedback
are recorded. Earlier same-session host safeguards pass. The original wider saved
document scope is retained; guided success is not unprompted discovery or complete
negative isolation proof. Historical synthetic and technical gates remain separate.

| Gate | Review finding | Remaining action |
| --- | --- | --- |
| Three-day canary observation | Only 40h22m32s between approved October 7 resumption and latest Day 3 checkpoint; no pre-recovery/unverified time credited | Reconcile further pauses; next time-only review floor October 10 at 19:08:38 Pacific |
| At least 90% attempted core journeys | Two guided PDF/question workflows pass; a complete human attempted/completed ledger is not recorded | Reconcile attempts, completions and assistance; do not infer a global completion percentage |
| Accessibility and scope usability | Positive voluntary reports, but no targeted human keyboard/focus/navigation and scope-clarity results | Short read-only human checks; no paid retest or mandatory rating |
| Actual provider usage/cost | Session request count and cost remain unmeasured | Collect private content-free aggregate usage/cost; zero SDK retries do not imply zero cost |
| All safeguards | Current host/backup snapshot passes; historical protected authorization/privacy/integrity/recovery evidence is separate | Map applicable evidence and freshness to all gates; no fresh restore or cloud inventory claimed |
| Full staged rollout/closure | Only the two-person canary is authorized; ADR 0062 also includes five/ten-user stages and an explicit conclusion | Separate expansion authorization, or a reviewed scope change/remediate/stop decision; do not silently accept Phase 11 |

The provisional time floor is `2026-10-11T02:08:38Z` (Saturday, October 10, 19:08:38
Pacific), anchored to approved resumption at `2026-10-08T02:08:38Z`. Elapsed time is
not continuous uptime or activity proof, and additional pauses move the review floor.
Neither person needs continuous online attendance; no new question/upload is needed
for the next persistence/operational check. Reaching the time floor does not by itself
accept the canary or full phase. Voluntary structured ratings remain optional.

Accepted policy validation, the existing nine-scenario synthetic gate, the historical
ten-scenario technical gate and eleven focused free pilot tests pass. These are
contract checks, not automatic formal live acceptance. Frozen evidence is unchanged.
The separate ignored review record preserves source hashes and gap statuses; no
service/provider/cloud change, paid test, commit or push occurs in this review.

## Latest participant checkpoints

October 9 Day 3 completion: the operator reports own-account sign-in, the Webb PDF
Ready and no issues. Read-only browser inspection verifies the selected `webbfactsheet`
Library card Ready, one version and successful ingestion attempt one of one. `Webb Test`
retains two messages; citation one/page two shows the same 21.3-foot/6.5-metre mirror
and 18 gold-plated hexagonal deployable segments as the original verified answer.
The original wider two-document saved scope remains recorded; no retest or new
isolation conclusion is inferred. Together with the independent participant's
follow-up and the earlier same-session host audit, Day 3 checks are recorded complete.
Feedback is participant-reported, not a structured application rating. No new question,
upload, rebuild, feedback submission, worker start or service change. Public-only
screenshots remain outside Git. Formal pause-adjusted minimum-duration and remaining
product-evidence review are pending; Phase 11 is not accepted and no later cohort is
authorized by this checkpoint.

October 9 independent-participant follow-up: the operator reports her assigned PDF
Ready and everything opening correctly in response to the personal-review instructions.
Browser inspection verifies one Library document/one ready, the assigned document's
Ready badge, two persisted chat messages, the unchanged answer and citation one/page
two with the matching characteristics table. This is operator-reported participation
plus read-only persistence/citation proof, not agent-performed human validation or an
application rating. Public-only proof screenshots remain outside Git. No new question,
upload, rebuild, feedback submission or service change. The operator's own Webb
follow-up and formal observation/product-evidence review remain pending.

October 9 Day 3 preparation: both participants are operator-confirmed available.
Strict read-only host checks at `2026-10-09T18:15:54Z` and supplement at `18:16:31Z`
pass: eight services running, unchanged application revision/schema and retry profile,
worker exited zero/restart-no with unchanged stop timestamp, zero active jobs and
empty queues/no consumers. Core host health, enforcing SELinux, zero failed units,
both enabled active maintenance timers and fresh capacity pass. Latest owner-only
encrypted backup is 5.8 hours old; header and checksum match successful upload evidence,
with no plaintext staging. Public readiness/TLS/anonymous denial pass. No service
change, worker start, paid request, fresh restore or cloud-resource inventory occurs.
The open browser still displays the saved second-account answer and citation table;
that alone does not verify fresh human review or PDF Ready. Each person's own-account
Ready/saved-answer/citation/usability follow-up is pending. Three calendar sessions do
not alone establish the minimum observation duration or formal Phase 11 acceptance.

Latest October 8 read-only follow-up: the operator reports own-account sign-in and
the assigned PDF Ready. Browser inspection verifies the saved answer, two persisted
messages and its original page-two citation excerpt remain available. Public UI/TLS,
API dependencies and anonymous denial pass. A subsequent second-account check verifies
its saved answer and page-two table excerpt after the operator reports PDF Ready.
Both accounts' persistence checks pass. The operator confirms the independent
participant personally reviewed her items and reports no issues; this is voluntary
operator-relayed feedback, not an application rating. Both participant follow-ups are
recorded, while the operator's separate usability sentiment is not inferred.
The initial check lacked the recovery key and did not verify fresh internal state.
The subsequent key-loaded read-only audit at `2026-10-09T03:11:53Z` and supplement at
`03:12:42Z` pass: eight services run at the unchanged `dba88de` application revision;
worker remains exited zero/restart-no with its October 7 stop timestamp unchanged.
Active jobs and queue messages/consumers are zero; effective ingestion budget one and
provider retries zero remain intact. SELinux is enforcing, core host services active,
failed units zero and both maintenance timers enabled/active/waiting with successful
last services. Fresh capacity passes; the 14.6-hour-old encrypted backup has its
owner-only mode, age-v1 header and SHA-256 matched to successful upload evidence.
No plaintext staging remains; the permanent backup-resume fix is unchanged. Public
UI/TLS/readiness/anonymous denial pass. No new restore or cloud-resource inventory is
claimed. No new question, upload, rebuild, worker start or service change occurs.
Day 2 participant checks and current read-only host safeguards are verified; formal
observation, remaining product evidence and Phase 11 acceptance remain pending.

Day 1 October 7 checkpoint: the approved two-PDF/two-question maximum is consumed.
Both guided answers match their public source facts and cited page. The second saved
conversation selects only its assigned document; all eight sources remain within
that selection and workspace. Exactly two question/answer pairs are persisted across
two workspaces. Worker remains stopped, exit zero/restart-no, and API is ready.
The first conversation's wider two-document selection remains recorded; no automatic
resubmission or full isolation proof is claimed. Optional genuine feedback and formal
active-observation/safeguard review remain pending; Phase 11 is not accepted.

Ingestion cleanup checkpoint: both approved uploads are ready with active generations,
each succeeded at attempt one of one under separate accounts/workspaces. The second
Library shows only its assigned PDF. After fresh zero-job/queue/in-flight checks, the
existing worker is stopped gracefully at `2026-10-08T02:42:16Z`, exit zero, restart-no
preserved. API remains ready for the second person's single question. No further
uploads, rebuilds or first-question resubmission are authorized by this run. Account
counts do not by themselves prove independent human participation or full isolation.

Session startup checkpoint — October 7 Pacific: renewed explicit approval covers one PDF and
at most one question per independent participant, required embeddings and optional
feedback, with no automatic retries or new cloud resources. Fresh guards pass before
one in-place start of the existing `dba88de` worker at `2026-10-08T02:08:38Z`.
Nine services are running; a fresh ready worker heartbeat, one broker consumer and
empty queues are verified. Worker restart remains disabled. API readiness, public
UI/TLS and anonymous API denial pass; fresh capacity, encrypted backup age, maintenance
timers and zero failed host units pass. Participant uploads/questions/feedback have
not yet occurred in this session. This clearance permits only the supervised bounded
journey; it does not accept Phase 11 or count paused recovery time as active observation.
Stop on workflow failure; further attempts require review and separate approval.
Subsequent October 7 observation: the first participant reports the upload Ready.
Content-free read-only verification confirms exactly one new document/version/job,
ready with an active generation and successful ingestion at attempt one of one.
Worker remains ready, one delivery acknowledged, queues empty and restart count zero.
The first question and second person's journey remain pending; provider call count
has not been measured. This is partial workflow evidence, not a completed canary gate.
The first participant subsequently completes one guided question. The used citation's
page and both answer facts match the original public PDF. Read-only checks show one
persisted question/answer pair, but the answered conversation selected two documents
instead of the intended single document. All six supporting sources belong to that
saved scope and workspace; this is a scope-selection observation, not proof of an
authorization leak or UI defect. Do not resubmit the paid question to retest without
separate approval. Feedback and the independent participant's journey remain pending.
The separately approved October 5 local test-isolation
fix passes `make check` (442 tests/16 expected skips) and `make check-live`
(457 tests/one expected skip); the earlier outbox-test failure is resolved in this gate.
OCI recovery and the permanent backup-resume fix are preserved. The dated recovery checkpoints
below are chronological evidence, not instructions to repeat completed recovery actions.
Recovery publication was separately squash-merged through PR #27. The bounded retry
profile is now implemented with source publication approved; deployment and paid pilot execution remain separate
gates. Phase 11 is not accepted.

Publication checkpoint — 2026-10-04: PR #28 passed eight applicable source CI checks
at `541ab9c` and was squash-merged as `dba88de` with identical trees. Explicit approval
now dispatches one protected application-image publication at that exact merged revision:
[run 37262385321](https://github.com/mvyas412/ai-projects/actions/runs/37262385321).
All eight jobs pass in 19m20s, including the published-image scan and OIDC-signing gate.
Published immutable application index:
`sha256:4a39d5affe71651ca5a19bf6d79542ee578f3bc4aca62234d6abf86721ec9978`.
Registry metadata verifies AMD64/ARM64 manifests, SLSA provenance containing the approved
revision and both SPDX SBOMs with the reviewed Python versions. Publication is not deployed
profile adoption or pilot acceptance; independent signature verification remains a deployment
preflight check. No automatic rerun or Next.js publication.
Host deployment requires fresh preflight, rollback manifest and exact unchanged plan-hash
approval; worker stop and participant pause remain binding. No paid call or new resource.
The source-security checkpoints below retain historical validation boundaries.

Historical deployment preparation checkpoint — 2026-10-04 Pacific: read-only preparation is
authorized, not host execution. The existing host answers SSH but the dedicated recovery
identity is not loaded; authentication ends before remote commands. Fresh host revision,
backup/capacity/jobs/queues and readiness are therefore not verified. The local previous
release manifest is historical rollback input only. Independent signature verification
also remains outstanding. No executable ready plan or approval hash is issued.
Review must explicitly bound Compose dependency traversal during application startup and
stage matching image/profile configuration for the stopped worker without starting it.
No host mutation, automatic retry, paid call, worker start or participant resumption.

Fresh deployment preflight — 2026-10-04 Pacific (04:40 UTC October 5): operator reloads
the recovery key. Strict SSH and bounded noninteractive privilege checks pass. Current
application/rollback revision is `8000dab`; all six immutable image pins and deployment
input hashes match. SELinux is enforcing, core services active, no failed units, disk use
39% and inode use 2%. API/storage readiness, public TLS/UI and anonymous API 401 pass.
Both application queues are empty with zero consumers; no active ingestion jobs exist.
Worker remains stopped. Backup/capacity timers are active, latest capacity evidence passes,
and the latest mode-0600 encrypted backup is 3.4 hours old with verified ciphertext SHA;
no plaintext staging remains. Five cached models pass verify-only checks without downloads.
This is not a fresh cloud-resource inventory or independent proof of participant pause.

Independent signature verification now passes for the published index, constrained to
the approved workflow identity, GitHub issuer, repository, main ref and full `dba88de`
revision. Project-local Cosign 3.0.6 is checksum-verified against the already pinned
official installer before execution; certificate trust and transparency evidence pass.
The ignored complete supervised plan binds current/staged file hashes and immutable
rollback/target manifests. It awaits explicit unchanged canonical plan-hash approval.
It is not a generic `phase10_release execute` plan: that executor's upgrade dependency
traversal is broader than this paused-pilot scope. Exactly bounded manual steps use
`--no-deps` and `--pull never`, one forward-only unchanged-head migration, offline model
verification and API/dispatcher/UI startup only. Edge/storage remain running unchanged.
Worker configuration is created but never started, with matching target image/profile
and a private `restart: no` override retained until separately approved resumption.
Backup timer pause/restore and existing maintenance leases prevent concurrent deployment;
the tested host backup fix is preserved rather than resetting the host checkout.
Any drift/failure aborts without automatic retry or rollback. Approval rechecks freshness
and requires participant pause. Twenty-six focused free release/retry tests and plan
input/manifest checks pass. No deployment, paid call, worker start, commit/push or new resource.

Supervised apply checkpoint — 2026-10-04 Pacific: the operator approves the exact
prepared plan hash. Fresh guards pass; exclusive backup/release leases are acquired,
original inputs saved privately on host, and the existing backup timer paused. The signed
target app digest pulls successfully with ARM64/full revision verified. API/dispatcher/UI
are stopped; reviewed Compose/profile/manifest and two runtime fields are installed.
One forward migrator and offline model verification both exit zero at unchanged head
`20260919_0019`. The next `compose create --no-deps` fails because installed Compose
does not support that option for `create`. This is an agent planning error, not an
operator error, worker start, model failure or data-integrity finding.

Execution stops at that first failed command: no startup, retry or rollback. The backup
timer is restored active/enabled and leases released. Read-only inspection confirms
API/UI/dispatcher and the old worker stopped, five unchanged edge/storage services running,
empty application queues/jobs, unchanged recorded release revision and no failed units.
The application is unavailable, and runtime adoption/Phase 11 acceptance are not passed.
Private original inputs remain for recovery; no secrets are transferred or printed.
Host help and a content-free dry run verify the corrected `up --no-start --no-deps
--pull never worker` recreates only the worker without starting it or touching dependencies.
A separate exact-hash continuation is prepared, not executed. It skips the completed
pull/environment/migration/model steps, configures the worker stopped/restart-no, then
starts and verifies API/dispatcher/UI only. Fresh guards and new direct approval are
mandatory. Free `make check-live` passes 443 tests/one skip with no drift and local
API/UI health; this is local regression evidence, not cloud recovery. No paid calls,
worker/participant resumption, new resources, automatic retry, commit/push or acceptance.

Continuation preflight checkpoint — 2026-10-04 Pacific: the operator approves the exact
corrected continuation hash. Read-only guards stop on the sole failed unit,
`mm-rag-phase10-capacity.service`, before any timer pause, worker configuration or
application startup. Its unchanged collector invokes `docker compose exec api` for
the operations report; journal error-category markers confirm that command exits one
while API is stopped. The earlier passing capacity report is historical, not fresh.
Docker/journald/D-Bus/SSH, storage/edge and both enabled/waiting timers remain healthy;
recorded revision and stopped roles are unchanged, with no continuation apply record.
Direct provider-free CPU/memory/disk/inode measurements are within existing limits.

A separate complete recovery plan is prepared, not executed: validate the known sole
capacity failure and direct fresh safeguards explicitly, configure the worker without
starting it, restore API/dispatcher/UI, then obtain one successful provider-free
capacity collection (or verify a fresh timer-produced success). No collector, policy
or timer edits and no `reset-failed` error hiding. Any other failure aborts. Only after
all readiness/retry/capacity safeguards pass may recorded revision advance. Original
backup/rollback inputs are preserved. No repeat pull/environment staging/migration/model
verification, automatic retry/rollback, worker start, participant resumption, paid call,
new resource, Git publication or Phase 11 acceptance. Twenty-six focused free tests pass;
the prior full live gate remains 443 passed/one skip, not a cloud deployment pass.

Approved recovery completion — 2026-10-04 Pacific (05:14–05:15 UTC October 5): exact
new-plan approval authorizes one execution. Strict fresh hash/original-input/rollback,
known stopped-API capacity-failure, direct policy metrics/TLS, encrypted-backup checksum
and quiescence checks pass under existing backup/release leases. The backup timer is
briefly paused. Supported no-start/no-dependency/no-pull worker configuration succeeds;
the worker remains created/never-started/restart-no with the target image/profile.
Only API/dispatcher/UI start; storage/edge/setup identities, mounts, networks, pins and
start times are preserved. Public TLS/UI, dependency readiness, anonymous API 401 and
empty application jobs/queues pass. One provider-free capacity service start succeeds,
producing fresh passing evidence and clearing its prior failure normally, without
`reset-failed`, policy/source/timer edits or a retry.

The provider-free report verifies `pilot-single-attempt-v1`, one ingestion attempt,
zero embedding/chat retries and `live_execution_authorized=false`. Only after full
postflight does recorded application revision advance to `dba88de`. The backup timer
is restored, leases released and independent read-only verification passes: eight
services running, no failed units, both timers enabled/active/waiting, worker never
started and setup roles stopped. SELinux, private originals, owner-only runtime secrets,
current-boot generator override and permanent backup fix are preserved. No repeated
image pull, migration, model verification, paid call, new resource, participant resumption,
automatic retry/rollback, Git publication or Phase 11 acceptance.

The October 4 recovery-session `make check-live` was **not a pass**: 442 tests pass, one skips and the
existing PostgreSQL outbox lease integration test fails because its first claim returns
zero events. Read-only inspection confirms the local dispatcher running and worker
stopped; competing consumption of the test's past-due event is a plausible inference,
not a confirmed cause. No test retry, dispatcher stop or source fix is performed.
This local regression finding is separate from the verified cloud recovery and remains
an explicit follow-up; the prior 443-test live pass is historical, not this run's result.

Local diagnosis — 2026-10-05 Pacific: read-only metadata confirms the integration
test and running local dispatcher share PostgreSQL; the local worker remains exited.
The test commits its year-2000 event before several concurrency checks, whereas the
dispatcher claims events due at the current time. The past clock excludes newer rows
from the test's query but does not protect its event from the real dispatcher.
An in-memory repository diagnostic returns one test claim without competition and zero
after a normal-clock competing claim. This confirms the isolation defect and reproduces
the failure mechanism, not the original event's claimant or PostgreSQL lock acceptance.
Recommend a dedicated isolated PostgreSQL test database with the same migrations and
unchanged assertions. Implementation remains separately approved; no live test replay,
persistent database writes, service changes, paid calls or cloud actions occurred.

Approved test-isolation implementation — 2026-10-05 Pacific: the outbox proof now
uses a uniquely named disposable database on the existing local PostgreSQL server.
Its fixture applies the unchanged Alembic chain, verifies the actual database and
current head, and leaves the application URL/settings untouched. All 20 original
lease, expiry, publication and standard/bounded idempotency assertions are unchanged.
The fixture refuses remote/production/query-overridden targets; cleanup checks exact
database identity/ownership and never force-drops or terminates other sessions.
Fourteen synthetic safety/lifecycle tests and the targeted real PostgreSQL proof pass
with the application dispatcher still running and worker stopped. The disposable
database is removed and catalog cleanup verified. Full free gates pass: `make check`
442 tests/16 expected skips and `make check-live` 457 tests/one expected skip, static/
frozen-evidence/deployment/observability checks, head `20260919_0019`, zero drift and
local API/dependency/UI health. No dependency synchronization, paid call, cloud action,
service start/stop, participant resumption, commit/push or Phase 11 acceptance occurs.
Historical failure evidence remains above; this is new passing regression evidence,
not proof of the original claimant or permission to start the formal paid workflow.

Source publication approval — 2026-10-05 Pacific: the operator separately approves
commit and normal push of the local test-isolation fix and pending recovery records
on the existing Phase 11 branch. The fresh pre-commit `make check` passes 442 tests/
16 expected skips, unchanged head and zero drift. This approval does not authorize a
new PR, merge, image publication/deployment, worker start or participant resumption.

## Single-attempt pilot retry profile

The opt-in `EXECUTION_RETRY_PROFILE=pilot-single-attempt-v1` is a temporary execution
boundary, not a new general retry default. `standard` retains three ingestion attempts,
two embedding-client retries and the existing chat SDK default. Invalid profile names
fail configuration validation. Set the same reviewed profile on API and worker only
after separate deployment approval; no runtime environment is changed by
this local implementation.

Under the pilot profile:

- New jobs durably store `max_attempts=1`; duplicate delivery cannot add an attempt.
- Retryable failures and expired leases become terminal without a retry outbox event.
  The stored one-attempt budget survives a later process-profile rollback.
- Embedding and chat clients (including image transcription) receive `max_retries=0`.
  Query-embedding failure does not proceed to generation; generation failure is not replayed.
- Successor retry/rebuild and differently keyed re-enqueue of the same version are
  rejected after authorization. Same-key replay preserves the original job/history.
- Worker startup checks active job budgets before connecting the broker consumer.
  A pilot worker refuses multi-attempt jobs; a standard worker refuses bounded jobs.
  The claim path rechecks compatibility without performing indexing or altering history.
- Single-attempt Library jobs show an operator-contact notice instead of Retry/Rebuild.
  The backend remains authoritative, including for historical jobs visible in the UI.

This profile is **not** a participant allowlist, PDF/question counter, token/spending cap,
or paid-run authorization. The existing two-person, one-PDF/one-question-per-person
maximum remains an operator-supervised workflow boundary. Legitimate embedding batches
may require multiple distinct requests; disabling retries does not limit batch count or
guarantee a monetary ceiling. Stop on failure and review any further attempt separately.
Do not reopen access or start the worker from a configuration-report pass alone.

Provider-free local configuration check:

```bash
EXECUTION_RETRY_PROFILE=pilot-single-attempt-v1 uv run python -m scripts.phase11_retry_controls
```

It emits only the profile and effective retry values, exits nonzero for standard mode,
and always reports `live_execution_authorized=false`. It does not inspect the deployed
processes, jobs/queues, participant limits, capacity, backups, or consent. Before a
separately approved deployment/run, verify exact reviewed source/image, matching API and
stopped-worker configuration, no incompatible active jobs, reviewed empty/limited queue,
fresh operational safeguards and the two independent participant sessions. Preserve the
worker stop and both-person pause until all these gates pass. Do not use Compose startup
as a configuration probe or rewrite old jobs to make the scope check pass.

Installed-SDK transport tests use only local mocked HTTP for 429, 503, connection and
timeout failures. The profile follows the official advice to avoid multiplying SDK and
application retries ([OpenAI retry guidance](https://developers.openai.com/api/docs/guides/rate-limits)).
No real provider call is required to test it.

Local verification checkpoint — 2026-10-04: `make check` passes 420 tests with 16
expected skips; `make check-live` passes 435 tests with one expected skip. Ruff/Mypy,
deployment/observability contracts, accepted migration head and zero schema drift pass.
The real PostgreSQL concurrency proof passes for same-key replay and differently keyed
submission rejection. Existing local API/dependency readiness and UI health pass; these
health checks do not attest that the deployed processes use the new profile. Added-line
and new-file privacy checks pass. No cloud deployment, worker start, participant
resumption, paid call or Phase 11 acceptance is included. Commit/push approval covers
source publication only and does not activate this profile.

Candidate security checkpoint — 2026-10-04: draft PR #28 initially failed its
dependency scan on the pre-existing Next.js 16.3.5 pin. Separately approved
source-only remediation pins 16.3.6 and matching runtime/compiler dependencies for
[GHSA-vcvr-r3jv-pc5j](https://github.com/advisories/GHSA-vcvr-r3jv-pc5j). Four candidate
tests, type-checking, production compilation and npm audit (zero vulnerabilities)
pass under Node 24 without credentials or provider calls. Expected build-time Auth0
configuration warnings do not constitute authenticated browser verification.
Fresh free `make check` (420 tests/16 skips) and `make check-live` (435 tests/one
skip), static/offline/schema gates and existing local API/dependency/UI health pass.
No image publication, deployment, worker start or participant resumption is included;
Streamlit remains authoritative and the PR stays draft pending review/checks.
The initial native application-image scan separately reports existing Python dependency
findings, including PyJWT, pypdf and urllib3. Do not treat the clean candidate npm audit
as an application-image scan pass, suppress findings or widen upgrades implicitly.
Separate remediation approval and passing security gates are required before merge.

Python security checkpoint — 2026-10-04: subsequent source-only approval covers
PyJWT 2.13.0 → 2.15.0, pypdf 6.15.0 → 6.19.0 and urllib3 2.7.0 → 2.8.0 only.
The lockfile changes exactly these three package versions. A deeply nested synthetic
token reproduced an uncaught exception before the upgrade and is rejected before JWKS
fetch afterward. Offline coverage also checks valid RS256 resolution/caching, redirect
refusal, non-RS256 rejection, PDF text/page locators and existing single-attempt controls.
All future ingestion fingerprints change because the existing manifest records pypdf for
every media type; historical manifests and generation identities remain untouched.
No reindex, paid call, image publication, deployment, worker start or participant
resumption is included. Subsequent approval covers commit/push and inspection of fresh CI;
the native-image scan must pass before the existing CI blocker can be considered resolved.
Free verification passes: focused regressions (28 tests), `make check` (428 tests,
16 skips) and `make check-live` (443 tests, one skip), including lint/types,
protected offline evidence, schema and existing local API/dependency/UI health.
The local worker remains exited. Existing-process health is not proof of deployed
adoption of these source dependency updates.

## Purpose

The Phase 11 controls provide a deterministic, content-free rehearsal of the pilot
control contract before any real participant is invited. This verifies policy and
evidence completeness; it is not evidence that a person completed the product UI. The
commands do not enroll users, call providers, spend money, change cloud resources,
promote Next.js, or enable automatic retention.

## Current commands

Validate the accepted policy:

```bash
make phase11-policy-check
```

Generate ignored synthetic evidence and validate it:

```bash
make phase11-rehearsal
make phase11-evidence-gate
make phase11-canary-readiness
make phase11-technical-template
make phase11-technical-gate
```

The contract gate enumerates login/logout, personal-workspace defaulting, upload/progress/cancel/retry,
library readiness, grounded chat/citations, structured feedback, access revocation,
support/pause handling, and backup/rollback readiness. Evidence contains no identities,
content, provider identifiers, or secrets.

## Approved live-pilot defaults

- The workspace Owner approves and revokes access.
- Support is best effort within one business day.
- Aggregate evidence is retained for 30 days after closure and removed manually after
  review; automatic deletion remains disabled.
- Stage gates are 2 users/3 days/2 active, 5 users/7 days/3 active, and
  10 users/14 days/5 active.
- At least 90% of attempted core journeys must complete, while all safeguard gates must
  pass without exception.

Exactly two approved account identities were supplied through the private operator
workflow and are not present in Git or aggregate evidence. Both are verified, have
participant-controlled credentials, and completed authenticated Personal-workspace
login. Auth0 public database signup and MM-RAG Google social login remain disabled.

One human accepted the participant notice for both accounts. ADR 0063 therefore permits
a clearly labeled two-account technical rehearsal while preserving ADR 0062's formal
two-user gate. The rehearsal does not start the three-day clock, satisfy product-user
validation, or authorize expansion. `make phase11-canary-readiness` reports the
technical rehearsal ready and the formal canary blocked on a second independent human.
The technical-template command creates ignored, identity-free evidence with every live
scenario pending. Operators update only aggregate statuses and provider-call/cost totals;
the technical gate cannot convert that evidence into formal product validation.

## Two-person observation checkpoint — 2026-09-30 Pacific

The independent participant has personally consented. Read-only Auth0 inspection
confirms verified activation, successful login, MFA enabled, and an unblocked account;
the operator confirms that the participant sees her own cloud Personal workspace.
The bounded canary now comprises the operator and one independent participant, not
the two accounts controlled by the operator during the earlier technical rehearsal.
No additional invitation or cohort expansion is authorized.

The observation window starts at `2026-10-01T02:10:47Z` (September 30, 19:10:47 Pacific).
The earliest three-day review is `2026-10-04T02:10:47Z` (October 3, 19:10:47 Pacific).
Elapsed time alone does not pass the gate: both people must be active, at least 90% of
attempted core journeys must complete, and all safeguards must pass. Current operational
checks, workflow results, accessibility, and voluntary feedback remain to be collected.
The public Streamlit health endpoint returned `ok`; that does not prove API dependency,
backup, capacity, or tenant-isolation readiness. Phase 11 is not accepted.

Record only content-free aggregate observations in the ignored Phase 11 results
directory. The start record is an operator observation, not evidence accepted by the
synthetic or technical gates. `make phase11-canary-readiness` remains a frozen
technical-rehearsal preflight, not a live enrollment or formal acceptance check; its
second-human blocker describes that earlier boundary and is superseded for manual
observation by this checkpoint. Do not rewrite historical rehearsal evidence to pass a
formal gate.

The observation-start checkpoint alone does not authorize paid processing or unattended
execution. The subsequent bounded approval below supersedes the pending paid-approval
boundary. For now, each participant can confirm sign-in, Personal
workspace, Library navigation, notice clarity, and logout, and report usability issues
through the existing manual support path. Safety or recovery failures pause the pilot;
expansion still requires an explicit decision.

## Bounded workflow approval — 2026-09-30 Pacific

The operator reports successful logout on both participants' laptops and authorizes
one workflow run with one authorized, non-sensitive PDF and up to one question per
participant, required embeddings, optional structured feedback, no automatic retries,
and no new cloud resources. This is a two-PDF/two-question maximum, not recurring paid
authorization. Each person must perform their own journey; an agent-operated replay
cannot substitute for independent product-user evidence.

Execution remains paused before upload or model calls. Public Streamlit health responds,
but the local SSH agent has no identities and the default host connection was rejected.
Fresh host readiness, backup age, capacity, active-job/queue inspection, and worker state
therefore remain unverified. Restore access using the existing private key through the
private operator path; do not disclose its contents, replace the host, or widen ingress.

Recovery inspection found the existing VM running and its Run Command plugin enabled
and running, but with a permissions advisory. The inspected compartment and tenancy
policies do not grant the instance permission to consume Run Command jobs. Its existing
instance-principal dynamic group matches exactly this VM. A bounded, non-mutating
diagnostic was submitted and initially remained undelivered with no output. Its
cancellation was subsequently acknowledged and execution marked `Canceled` after
the separately approved permission took effect. Do not count that command as a
successful host-access or operational check.

After explicit security-change approval, a separate temporary policy was created and
its stored statement verified. It allows the existing exact-host dynamic group to use
`instance-agent-command-execution-family` in the existing compartment, constrained by
`request.instance.id=target.instance.id`. The backup-upload policy is unchanged. One
newly approved 60-second read-only diagnostic was submitted without reading key-file
contents or changing host configuration. OCI acknowledged that command and reported
`Succeeded`, exit code `0`, with start/completion markers and
`privileged_key_file_access=false`. This proves bounded command execution, not
privileged SSH-file access, recovered SSH access, or current operational readiness.
The boolean does not distinguish missing sudo permission from an unreadable or absent
file. No OS administrator privileges,
credentials, ingress, or reboot were changed. Any SSH-key repair or reboot requires a
separate reviewed approval. After separate explicit cleanup approval, the temporary
policy was deleted and the compartment inventory verified to contain only the original
backup-upload policy. Its exact-bucket object-create-only restriction remains intact;
no Run Command permission remains in that policy. The deleted policy has no normal
restore flow; any recreation requires a new reviewed permission change. No VM data,
credential, OS privilege, network rule, or application runtime was changed by cleanup.

The next recovery decision is to locate the original private key in an operator-owned
backup or approve a separately reviewed console/key-repair procedure and any required
maintenance reboot. Do not grant broad sudo rights to the command agent as a shortcut.
Keep the paid run paused until host access, current safeguards, and bounded retry
controls are actually verified.

### Staged console recovery — setup approved; maintenance not authorized

If the checked operator backups yield no original key, use the existing VM's serial
console recovery path rather than replacing the host or widening agent privileges.
First restore operator console authentication and inspect the existing encrypted-backup
metadata, instance state, and maintenance prerequisites. If backup freshness/integrity or
writer quiescence cannot be verified before maintenance, stop for an explicit incident
risk review; do not treat historical evidence as a current preflight pass.

Then obtain separate approval for a dedicated, securely retained local recovery key and
a temporary console connection. Preserve the GitHub key and never expose private key
contents. A maintenance reboot and SSH-file repair require a further reviewed approval
and a stated downtime window. Preserve existing authorized keys; append only the approved
public key with correct ownership, permissions, and SELinux context. Do not reset account
passwords, replace data volumes, grant broad agent sudo, or create replacement hosts.
After normal boot, verify SSH and current operational safeguards, and separately review
console-connection cleanup. Stop rather than automatically retrying a failed recovery.

The operator subsequently approved dedicated recovery-key and temporary-console setup
on October 1. Key creation/passphrase entry and the public-key upload/submission are
handed off to the operator; only the public `.pub` file belongs in OCI, never the private
key. A dedicated persistent local filename was checked as unused, the SSH directory
has mode 0700, and the unsubmitted console form was set to public-key upload. On October
3, operator-created key files and owner-only permissions were verified; inspecting only
the public file confirmed RSA 4096-bit. Private contents and passphrase protection were
not inspected. After operator submission, renewed read-only OCI inspection verifies one
Active connection with a public-key fingerprint matching the local key. The operator
subsequently supplied the serial-console banner followed by an OS login prompt. This
is operator-provided attachment evidence, not an authenticated shell or recovered SSH.
Validate the console
server fingerprint against OCI before accepting any SSH trust prompt; stop on mismatch
or a changed-host-key warning rather than disabling verification. The console-copy
action yielded no command through the browser clipboard API, so use the operator's
reviewed UI copy workflow, never guessed resource IDs. Preserve existing keys and stop rather than
overwriting a file. This setup approval does not authorize a reboot, password reset,
SSH-file repair, or new IAM/network permission. Maintenance remains Proposed, and the
bounded paid pilot remains paused.

Read-only inspection on October 1 confirmed renewed OCI console authentication, the
existing Oracle Linux 9 VM Running, and local/Cloud Shell console-connection controls
with no existing connection listed. The private, versioned backup bucket contains a
new encrypted bundle last modified at `2026-10-01T12:32Z` (05:32 Pacific), sized
44,031,700 bytes, with MD5 and SHA-256 response headers. This verifies recent ciphertext
presence and available upload metadata only: no bundle was downloaded, decrypted,
compared with the host verification record, or restored. Current writer quiescence,
queue/worker state, dependency readiness, disk/inode capacity, and backup restore
integrity remain unverified. The later setup approval does not supersede the separate
maintenance boundary. At that inspection no new credential or connection was verified;
the later key/Active-connection checks above do not establish host operational access
or authorize maintenance. Refresh backup evidence before any later maintenance review.

The October 3 read-only refresh finds ciphertext last modified at `2026-10-03T12:36Z`
(05:36 Pacific), approximately 42.01 MiB, with MD5/SHA-256 headers. Fresh upload metadata
still does not prove restore integrity, writer quiescence, current jobs/queues, disk
capacity, or worker state. These unresolved preflight gaps require explicit incident
risk review before any reboot; ordinary release preflight has not passed.

Proposed maintenance is supervised and separately authorized: both users pause activity;
use a graceful reboot and a temporary recovery boot entry, not a forced reset or persistent
boot-configuration change; inspect the actual Oracle Linux 9 boot/filesystem before
modification; preserve all existing keys and append only the approved public key through
operator credential handoff. Maintain ownership, permissions and SELinux context. Never
replace volumes, reset passwords, broaden sudo/IAM/ingress, or automatically retry a
missed boot interception. Inspect the actual worker restart/stopped state before normal
application startup: tracked Compose uses `unless-stopped`, but its historical manual
stop is not current evidence. Do not authorize paid processing merely by restoring
Docker/services. Stop for review if safe startup cannot be established. This proposed
procedure was subsequently approved by the operator, but execution remains conditional
on both-user activity-pause confirmation and an attached console. The operator's latest
transcript reports remote console closure and return to the Mac shell; the cause and
VM state cannot be inferred from that transcript. Reconnect once using the existing
verified connection/key and strict host-key checks. Do not create another connection,
automatically retry, or reboot while disconnected. Neither maintenance nor SSH repair
has been executed, and both-user pause confirmation remains outstanding.

The operator subsequently confirms both-user pause and console reconnection; OCI
reports Running/Active. Direct Terminal control is blocked by the product safety
boundary, so the operator must perform timing-sensitive boot interception and credential
entry; do not circumvent that boundary through another app or client. The existing-VM
reboot confirmation is open but unsubmitted, with Force reboot unchecked. OCI's default
sends an OS shutdown request but powers off/on after waiting up to 15 minutes; the dialog
warns of possible corruption if applications have not stopped. This is not a guaranteed
graceful-only shutdown and requires specific risk acknowledgement before proceeding.
Participant pause is not verified writer/job quiescence. No reboot, boot-entry edit,
SSH repair, or paid processing has occurred. Stop rather than automatically retrying.

The operator subsequently acknowledged the default reboot fallback/corruption risk
and confirmed readiness at the attached console. One supervised attempt is approved,
with Force reboot unchecked. Final submission is handed to the operator to coordinate
immediate Terminal boot interception. Stop at the first firmware/GRUB menu for inspection;
do not automatically repeat a missed attempt or edit boot entries before inspecting
the actual Oracle Linux 9 screen. Reboot execution and SSH repair remain unverified;
no worker/application startup or paid execution is authorized by this handoff.

The operator subsequently reports the reboot submitted. Following serial disconnection
and reconnection, the console displays the OS login prompt, with no captured firmware/
GRUB menu or maintenance shell. OCI reports Running and the existing connection Active;
the empty Work requests view does not independently certify reboot completion. Stop
this attempt. Do not automatically reboot again: any additional coordinated attempt
requires fresh explicit authorization and operator-controlled timing. No SSH repair or
application/worker safety pass is evidenced, and paid pilot execution remains paused.

After an explicit operator pause, read-only recovery checks resumed. Dedicated key-file
permissions/public fingerprint still match, but the earlier one-hour agent loading
interval elapsed and current loaded state is unverified. OCI now requires operator
reauthentication before fresh VM/console verification. A resume request does not
authorize a second reboot; retain the attached-console/readiness and fresh-approval
boundaries. No second reboot, SSH repair, or paid execution occurred.

Operator reauthentication subsequently restored read-only OCI access. The current page
verifies Running and the existing console Active with the same verified fingerprints.
Reloading the local key is operator-reported, not proof of an attached serial session.
Reconnect through the existing Linux/Mac copy workflow; do not create another connection.
No second reboot or SSH repair occurred. Fresh authorization for an additional attempt
is still required after console attachment and operator readiness are confirmed.

The subsequent operator transcript evidences serial reconnection at the OS login prompt.
OCI still reports Running/Active. An additional reboot confirmation is open but
unsubmitted, with Force reboot unchecked. Fresh approval for exactly one additional
attempt, current both-user pause, and keyboard readiness remain required; the default
15-minute shutdown/power-cycle risk and unverified host preflight gaps still apply.
No second reboot, SSH repair, worker start, or paid execution has occurred.

The operator subsequently explicitly approved exactly one additional supervised reboot
and affirmed availability in response to the pause/readiness and fallback-risk review.
Final submission is operator handoff for immediate Terminal interception, with Force
reboot unchecked. Stop at the first firmware/GRUB menu before editing. No third attempt
or automatic retry is authorized. Execution and SSH repair remain unverified; paid work
and application/worker startup remain gated on actual current safeguards.

The additional attempt subsequently produced normal-boot evidence: Docker/containerd
stopped during shutdown, then the OS login prompt, container bridge forwarding, and
cloud-init completion appeared. OCI reports Running/Active, but no firmware/GRUB menu,
maintenance shell, or SSH repair is evidenced. The additional approval is consumed;
do not run a third reboot automatically. Review earliest firmware/GRUB scrollback before
another recovery decision. Oracle's guide lists OL9 support but its detailed key/menu
branches describe versions 7/8, so do not treat generic Esc advice as a verified A1/OL9
sequence. Do not enable Cockpit from the generic OS banner. Container networking does
not verify the worker, queue/jobs, provider activity, or application readiness. Keep
participants and paid work paused pending those safeguards.

Full operator scrollback subsequently confirms Oracle AAVMF's boot-device menu and
GRUB 2.06 both appeared on the additional attempt. GRUB's five-to-one-second countdown
was not paused, so normal boot followed. This supersedes the incomplete-snippet inference
that no menu was captured; firmware/GRUB access is evidenced, but maintenance/SSH repair
is not. The firmware menu explicitly says Esc exits. On any further separately approved
attempt, stop repeated Esc at the first boot-device menu and inspect a screenshot before
selection. When intentionally advancing to GRUB, interrupt its countdown with an arrow
key and inspect the normal entry before editing. Do not infer the precise past keystrokes.
An EFI-runtime warning at power-down is followed by successful startup; neither proves
data integrity nor authorizes firmware/security changes. No further reboot is authorized
or performed, and paid work/current worker/job/host safeguards remain paused.

The operator clarified that Right arrow did not pause the GRUB countdown, then explicitly
approved one further supervised reboot under the same reviewed fallback risk. The current
OS login prompt evidences attached serial console; the pending OCI dialog has Force
reboot unchecked. Final submission is operator handoff for immediate Terminal focus:
stop Esc at the FIRST menu; if GRUB countdown appears, immediately press Up/Down and
obtain a screenshot before any boot edit. No retry loop or subsequent reboot is authorized.
Submission, temporary boot changes, and SSH repair remain unverified; maintain participant
pause and actual worker/job/backup/readiness gates before any paid work.

The next operator screenshot evidences GRUB 2.06's command prompt, not a Linux recovery
shell or configuration corruption. One Esc press should return to the loaded menu;
inspect the resulting screenshot and stop if the prompt persists, before entering any
commands or rebooting. No boot-entry edit, SSH repair, or paid execution is yet evidenced.

If one Esc press leaves the plain GRUB prompt active, inspect only the current GRUB
root/prefix and device inventory through operator handoff first. Do not infer corruption,
reboot, write configuration, or load normal/configfile/kernel commands before reviewing
the output; loading configuration may start another automatic countdown. This is a
read-only bootloader diagnostic, not an authenticated Linux shell or SSH repair.

Subsequent operator screenshots verify the boot partition and saved normal BLS
kernel/initramfs paths, root-volume and original boot arguments. The two referenced
tuning variables are empty in the current GRUB session. The reviewed next handoff
stages that exact kernel using GRUB `linux` with temporary `init=/bin/bash`, retaining
the original arguments and security settings. This does not save configuration or
boot the OS; inspect the result before the separate initramfs-load and boot handoffs.
Oracle's maintenance-shell procedure supplies the recovery argument, but its detailed
menu instructions are not a verified A1/OL9 sequence; actual operator screenshots are
the path/argument evidence. No successful kernel load, recovery shell, key repair,
application/worker start or paid execution is yet verified. Preserve participant pause
and inspect actual worker/job/provider safeguards before any normal service startup.

The long kernel command's serial rendering overwrote its input, so the operator
stored the temporary arguments in a task-specific GRUB variable and echoed them.
The complete original arguments plus `init=/bin/bash` are verified in the printed
output. Short kernel and matching initramfs load commands returned without visible
errors. Next handoff is GRUB `boot` for the current approved attempt, not another
OCI reboot. Inspect the resulting shell and running init before any file modification;
stop on errors or an unexpected normal login/service startup. Neither recovery-shell
access nor SSH repair is yet evidenced, and no saved configuration or key file has
changed. Keep participants paused; no automatic reboot/retry or paid processing.

The subsequent operator transcript reaches `bash-5.1#` after root-volume discovery,
mount and switch-root. Initramfs iSCSI discovery warnings did not prevent that
transition; do not infer full data integrity or change storage/network configuration
from those warnings. Next handoff checks only PID 1's command name and actual root
mount source/type/options. Verify the real-root maintenance context before loading
SELinux policy, remounting or inspecting exact key-file metadata. No key repair,
normal-service start, further reboot or paid processing has occurred.

Operator checks subsequently confirm Bash as PID 1 and the expected XFS root mounted
read-only. Initial SELinux policy loading returned zero. Next handoff remounts only
root read/write and verifies its actual mount mode before exact SSH-directory/key-file
metadata inspection. Do not print key-file contents, replace existing authorized keys,
or start normal services. No root remount or key modification is yet evidenced.

Operator output now verifies writable root with SELinux labeling, an opc-owned
mode-700 SSH directory and a regular opc-owned mode-600 authorized-keys file with
SSH-home labeling. The first home-directory path is display-overwritten; do not
infer a path/type fault from that rendering. Next handoff creates a unique backup
through `mktemp`, copies the existing authorized-keys file while preserving metadata,
and verifies backup metadata only. Do not print key contents or append until the
approved local public key is fingerprint-verified. No backup or append is yet evidenced;
normal services, worker processing and paid workflows remain gated.

Operator unique-backup byte comparison returned zero. Clipboard handoff copied only
the approved public key into the recovery shell; its remote fingerprint matches the
verified local public key. Exact-line presence check returned one (absent), with no
reported error. Next approved handoff appends once using a separating newline, without
replacing any original bytes, then verifies original-prefix preservation, key presence
and ownership/modes/labels. No append or restored SSH is yet evidenced. Keep Docker,
normal-service startup and paid workflows gated; no private key was read or transferred.

Operator append returned zero; original-prefix comparison returned zero and regular-file
ownership/mode/SSH-home label remain correct. Exact recovery-key line count is two, so
the intended single append is not yet accepted. Next handoff compares the complete file
read-only against the verified backup plus exactly two approved append payloads before
any narrow duplicate correction. Do not print key contents, remove original keys or infer
execution count solely from overwritten input rendering. Preserve the unique backup;
SSH access and controlled normal startup remain unverified, with paid workflows gated.

The complete-file comparison subsequently returned zero for backup plus exactly two
approved append payloads. Operator calculated the byte size of backup plus one payload,
then removed only the duplicate tail; correction reported zero and exact-line count is
one. Original backup remains. Next verify the entire file against backup plus one payload
and recheck metadata, then flush the repair and review a temporary Docker-autostart
barrier before normal init. Do not rely on historical worker state or start Docker/paid
processing merely because SSH repair succeeds. SSH access/startup remain unverified.

Final operator whole-file comparison returned zero against original backup plus exactly
one approved public-key payload. Regular-file ownership, mode and SSH-home label remain
correct; original backup remains available. File-level repair is verified, not live SSH
authentication. Next handoff flushes the write and inspects Docker unit enablement offline
without starting anything. Review temporary runtime-only autostart protection before
normal init; do not silently change persistent Docker enablement or start containers.
No additional reboot, live SSH pass, worker start or paid execution occurred.

Operator `sync` returned zero; offline inspection reports Docker service enabled and
socket disabled. Before normal init, verify `/run` is runtime storage, then stage and
verify temporary runtime-only masks for both units using offline unit-file operations.
Do not force replacement of an existing override, change persistent enablement, proceed
on mask errors or assume the current worker state. Both masks must be verified before
normal init. They prevent ordinary systemd activation but disappear on a future reboot;
no additional reboot is authorized. Live SSH and host/worker safeguards remain pending.

Operator verifies `/run` is tmpfs; offline runtime mask creation returned zero and
both Docker units report masked-runtime. Persistent enablement is unchanged. Next
inspect the existing public SSH host-key fingerprint before controlled normal init;
do not read private host keys or replace local trust entries. Recheck both masks and
actual inactive Docker state after normal init, before considering any container start.
No further reboot, live SSH pass, container/worker start or paid execution occurred.

Operator public SSH host-key fingerprint matches existing local trust. Normal init was
handed off without another reboot, but partial subsequent logs show auditd create denials
with tmpfs target labeling, unavailable journal socket and repeated OCI repository-service
failures. Do not wait indefinitely or accept normal startup: inspect actual runtime labels
and relevant unit status before correction. Do not disable SELinux, relabel globally or
reboot away the runtime masks. One bounded TCP probe confirms SSH reachable. One strict
host-verified authentication probe using only the public identity and existing agent
cannot obtain a usable signing identity; no private-key values were read and this does
not prove the repaired server key file is incorrect. Next handoff is operator private
key loading/login, followed by direct post-init masks/labels/units inspection. Host
container/provider activity is unverified; no agent-issued worker/provider start occurred.

Operator private key reload and strict trusted-host login subsequently restore live SSH;
public-identity/agent diagnostics also authenticate without reading private-key contents.
Read-only root unit queries succeed despite the failed system bus: Docker service/socket
are masked-runtime and inactive, journald/D-Bus failed, audit/OCI services restarting.
Bounded named-process inspection lists no dockerd/containerd process. Policy comparison
and `restorecon -n -v` identify exactly eight type mismatches on `/run`, `/run/systemd`,
`/run/systemd/journal`, `/run/systemd/system`, `/run/dbus`, `/run/systemd/private` and the
two `/run/systemd/system/docker.*` mask links. Journal/D-Bus/notification sockets checked
separately already match policy. Proposed separate authorization restores only those
eight default types, non-recursively and without force/policy changes, preserves mask
links and SELinux enforcement, then restarts only journald/D-Bus and checks audit/OCI
recovery. No global relabel, reboot, data/credential edit, Docker start, paid call or new
resource is included. Do not execute this newly identified repair before approval.

The operator subsequently explicitly approves that exact repair. Fresh preflight
confirms SELinux enforcing, Docker service/socket masked-runtime and inactive, and
both mask targets `/dev/null`. Non-recursive `restorecon` changes exactly the eight
reviewed types; all eight policy comparisons pass and mask targets/status remain
unchanged. Approved bounded journald/D-Bus restart reports journald control-process
failure. Follow-up read-only status/log/metadata SSH yields no results and stalls;
terminate only the verified agent-owned local diagnostic connection, never operator
SSH/serial sessions or VM services. Existing operator SSH is the next read-only
process/runtime-metadata handoff. Do not automatically repeat restart, extend relabel
scope, disable SELinux, reboot away masks or start Docker/paid work. Post-restart core
service state and full recovery remain unverified; original key backup remains available.

Existing operator SSH remains responsive for non-root diagnostics. Named-process
inspection lists D-Bus/auditd, not journald; unit metadata reports journald failed with
exit-code/status one. Policy comparison confirms `/run/systemd/journal/streams` is
tmpfs-typed instead of journal-runtime-typed. This target was not among the eight approved
objects. Treat it as a verified mismatch/suspected contributor, not a proven sole cause.
Request separate authorization for only its non-recursive default-type correction and
one bounded journald restart, with post-change checks. Do not silently extend to other
paths, repeat restarts, disable enforcement, remove masks, reboot or run paid processing.
That additional correction/restart has not occurred; full recovery remains unverified.

The operator subsequently approves the single-directory correction and one bounded
journald restart. One strict SSH connection includes read-only safeguards before those
operations, but returns only a server-not-responding timeout with no remote command
output. Preflight/correction/restart execution is unverified, not proof of success or
no change. Do not repeat blindly or assume disconnected privileged processes stopped.
Use existing operator SSH for read-only streams-label/unit-state and lingering process
metadata checks before any further handoff. No wider correction, reboot, mask removal,
Docker start or paid processing is included; complete operational recovery is pending.

Subsequent operator metadata distinguishes the remaining `agent -> sudo -> runcommand`
tree from the diagnostic SSH session; do not terminate it based on the command name.
The readable journald unit log contains only the earlier startup/shutdown, not the
current failure cause. A supervised, bounded single-directory correction from the
existing operator SSH shell returns `Killed`/status 137; policy validation still reports
the streams directory mismatch. The correction is not accepted, and no subsequent
journald restart is performed. Wrapper termination does not prove privileged children
exited: inspect named-process metadata before any further action. Do not repeat sudo,
extend relabel scope, reboot, remove Docker masks or start paid work automatically.

Follow-up named-process inspection lists only the previously identified agent-owned
sudo tree, with no listed timeout/restorecon/systemctl. Operator shell, PID 1 and SSH
contexts are respectively unconfined, init and sshd; sudo runtime directories are
PAM-runtime-typed. These observations do not establish the sudo hang's cause or repair
journald. Do not keep repeating privileged commands. A possible next route is a
separately approved supervised normal boot, using verified one-boot
`systemd.mask=docker.service systemd.mask=docker.socket` arguments rather than the
temporary bash init. This is only a proposal: first check current Docker inactivity,
generator availability and attached console/operator readiness. Runtime masks expire
on reboot; missed boot interception can allow normal Docker autostart. Obtain fresh
approval including that risk and OCI's possible 15-minute shutdown/power-cycle fallback.
No reboot, boot-argument change, security bypass or additional repair has occurred.

The operator verifies Docker service/socket are both inactive and runtime-masked,
and the debug generator is present and executable. This is a preflight observation,
not a recovered OS or application pass. The operator explicitly pauses recovery due
to intermittent availability before any further reboot approval. Stop recovery work
here; do not retry sudo, restart units, reboot, unmask Docker or run paid processing
while paused. SSH access is restored, but journald remains failed and privileged
command recovery is unresolved. On explicit resume, recheck key-agent availability,
host/console state and Docker safeguards before reviewing any new action. Runtime
masks are not reboot-persistent; no additional reboot is approved.

October 4 resumption is limited to read-only prerequisites. Local dedicated recovery-key
permissions and public fingerprint still match; the agent has no loaded identities.
Operator private reload is required for new agent-authenticated host diagnostics.
Reverify current host/console state, Docker safeguards and uninterrupted operator
availability; do not treat yesterday's state as current or the resume request as reboot,
repair, service-start or paid-work authorization.

The operator subsequently reports a two-hour key load and a disconnected old SSH
window. One strict new SSH attempt times out before authentication; no remote command
executes. One HTTPS connect probe also times out, without a TLS or readiness pass.
These observations do not identify key failure or VM state; Docker was intentionally
blocked at the last checkpoint. Agent browser inspection times out without current
OCI verification. Next verify existing instance/serial-connection state through operator
read-only handoff, not SSH retries, reboot, new connections or network/IAM changes.

October 4 operator inspection reports the existing VM Running, unchanged public IP and
existing console Active. Reconnection through that exact connection yields the serial
banner/login prompt and ongoing repository-service restart/journal-socket refusal.
Console attachment is evidenced, not privileged access or recovered OS readiness.
Next prepare only an unsubmitted reboot/risk review, confirming continuous availability
and participant pause before fresh approval for one supervised normal boot with
verified one-boot Docker masks. Current backup/writer/job/Docker checks remain incomplete;
the runtime-mask expiry, missed-interception/autostart and power-cycle risks still apply.
No new reboot, connection, repair, service start or paid processing occurs.

Agent browser inspection confirms the existing-VM reboot dialog is unsubmitted with
Force unchecked. A partly obscured red instance-health warning is visible behind it;
inspect its full wording before seeking reboot approval. Readiness gates remain pending.

Subsequent inspection verifies the unresponsive-instance warning, Active matching-key
console, and zero infrastructure/maintenance status over the displayed hour. This does
not establish guest readiness. Operator confirms 90 minutes availability; current
participant pause remains pending. A normal reboot confirmation is prepared but not
submitted, Force unchecked. Seek fresh approval for exactly one supervised normal boot
with temporary Docker service/socket masks, acknowledging incomplete backup/quiescence
checks, mask expiry, missed-interception/autostart and OCI's 15-minute fallback risks.

The operator subsequently confirms both participants paused, serial Terminal connected,
and explicitly approves exactly one supervised normal reboot with temporary Docker
boot masks. Fresh dialog verification shows Force unchecked and no submission. Final
click/interception are operator handoff; no automatic second attempt or Docker/paid
processing start is authorized. Submission and new boot-mask staging remain unverified.

Subsequent serial output retains long uptime and the existing repository/journal
failures, not a new boot. Fresh OCI inspection shows Stopping and the dialog closed,
evidencing shutdown transition after operator handoff. Startup/interception/new masks
remain unverified; do not issue a second reboot or force action. Exact click time is
not recorded, so do not infer elapsed shutdown time or failure from this snapshot.

The subsequent operator screenshot evidences GRUB menu interception. Rescue is selected;
the normal UEK entry is second. Select the normal entry and open its temporary editor
for inspection before staging one-boot Docker masks. Do not boot the rescue entry,
persist boot changes or infer OS readiness; no additional reboot is authorized.

The normal-entry editor screenshot verifies the expected kernel/initramfs, original
root/storage/serial arguments and no maintenance Bash override. Append only
`systemd.mask=docker.service systemd.mask=docker.socket` to the kernel line, preserving
all other content, then visually verify before boot. These are main-system one-boot
masks; no persistent edit, debug shell, SELinux bypass or Docker start is authorized.

The subsequent screenshot verifies both exact mask arguments on the normal kernel
line, with original arguments and initramfs preserved. Hand off one temporary-entry
boot within the approved reboot attempt. Verify actual command line, Docker masks/
inactivity, SELinux and core-service/SSH health after startup before any container start.

Post-boot strict host-verified SSH and bounded privileged checks establish OS recovery:
normal boot, SELinux Enforcing, journald/D-Bus/audit/SSH healthy, runtime labels matching,
no failed units and repository mapper successful. Root usage is 39%, inode usage 2%.
Docker is inactive with both masks in `generator.early`; all saved containers are stopped.
Worker metadata retains manually-stopped=true and unless-stopped; eight existing
services retain unless-stopped, two one-shots restart=no. The accepted phase10 backup
and capacity timers are enabled/waiting. Generic timer names queried earlier were
nonexistent, not evidence that the accepted safeguards were disabled.

Application restoration remains separately approval-gated. Proposed scope: recheck
worker/inventory, runtime-mask only `systemd-debug-generator`, reload unit configuration
once and verify generated Docker masks removed before starting existing Docker/services.
The host runs systemd 252; generator masking and reload are documented in its
[generator manual](https://github.com/systemd/systemd/blob/v252/man/systemd.generator.xml).
Plain runtime unmask does not remove generator-created masks. Preserve other generators,
persistent boot configuration, existing images/data, worker stop and participant pause.
No pull/recreation/migration, another reboot or paid processing is included. No such
restoration mutation has occurred; OS recovery alone is not data-plane/pilot acceptance.

Subsequent operator-approved restoration passes guarded strict SSH preflight. Runtime-
only debug-generator override and one reload release two generated masks; verified
vendor-unit startup resumes eight existing services without pull/recreation/migration,
saved boot edit or further reboot. Retain override while current kernel masks remain;
it expires next boot. Health/TLS/readiness/anonymous denial pass, revision/schema
retained, worker/one-shots stopped, participants paused, no active job/queue backlog.
No paid/pilot action or inactive-generation modification occurs.

Both enabled maintenance timers remain failed/resources: journals show failed starts
while Docker was masked, before restoration. Capacity evidence is stale, newest encrypted
bundle approximately 36.6 hours old without renewed integrity/restore proof. Separately
review timer recovery/catch-up backup because backup pauses services and existing resume
uses compose up/dependencies. No timer restart, backup/upload or participant resumption.
Application startup passes; full operational readiness/pilot acceptance remain pending.

Subsequently approved timer recovery and one catch-up backup pass: backup exits zero,
encrypted checksum/upload verified, owner-only ciphertext retained, plaintext staging
removed; no new restore proof or second backup. Original calendar/jitter and capacity
cadence restored, both timers enabled/active/waiting, fresh capacity evidence passes,
eight services healthy and no failed units. Worker/one-shots remain stopped, participants
paused; no paid calls/image upgrades/new resources or additional reboot.

The first temporary compose-start guard unexpectedly starts existing migrate/models
dependencies. Both now stopped/exit zero, schema/image unchanged; direct container
restoration and a corrected current-boot guard prevent dependency starts. Exact deployed
hash and five scope tests pass. Review permanent direct-existing-container backup resume
before another reboot or pilot resumption; this incident is not Phase 11 acceptance.

The subsequent approved permanent backup-only fix is deployed and checksum verified.
It validates full running container IDs before stopping and restores only those IDs,
never Compose dependencies or an originally stopped worker/storage role. Twenty focused
tests, the complete free gate (398 passed/16 expected skips), live gate (413 passed/one
expected skip) and five synthetic host resume cases pass. No real backup is repeated.
The temporary backup drop-in/helper are removed; protected canonical unit and original
timer schedules remain. Retain the current-boot Docker generator override.

A strict installer timer assertion stops final validation after installation; fresh
independent read-only checks then confirm both timers enabled/active/waiting, services
successful, fresh capacity pass, eight healthy application services, dependency/TLS/
anonymous denial checks, empty queues and no failed OS units. Worker/setup-job start
times and existing schema/image are unchanged. Both participants remain paused; no paid
call, image upgrade/new resource, extra reboot, Git publication or formal acceptance.
The existing bounded retry-control and independent-human workflow gates below still apply.

The product creates ingestion jobs with three attempts. The installed embedding client
also defaults to two provider retries, and the chat call sites do not explicitly disable
retries. Before processing either approved PDF, enforce and verify a single ingestion
attempt and zero provider retries for the bounded run, without silently changing the
accepted general retry contract. Keep the worker stopped until that control, a clean
queue scope, and all operational preconditions pass. No paid calls, uploads, retries,
or worker starts have occurred under this approval.

The accepted participant wording is maintained in
[the Phase 11 pilot notice and consent](PHASE11_PILOT_CONSENT.md).
