# ADR 0029: Structured tables and safe exact calculation

- Status: Proposed
- Date: 2026-09-02
- Milestone: 6.3 and 6.4

## Context

The current system extracts PDF text and treats table-like content as ordinary
chunks. It has no durable rows, columns, headers, cell spans, data types, units, or
calculation provenance. A language model can summarize retrieved text, but it must
not be trusted to reconstruct a table or calculate an exact value from generated prose.

Docling documents local table detection, row/column/cell reconstruction, and
TableFormer fast/accurate modes in its
[pipeline options](https://docling-project.github.io/docling/reference/pipeline_options/).
That output still requires application-owned validation and an authorized execution
contract before it can support exact answers.

## Decision drivers

- Preserve the original table, crop, cell text, structure, type, unit, and location.
- Distinguish extracted values from normalized values and calculated results.
- Execute only supported, bounded, deterministic calculations.
- Never run user- or model-generated SQL, Python, formulas, file paths, or extensions.
- Keep authorization and generation scope in PostgreSQL and RLS.
- Abstain when structure, units, types, or intent are ambiguous.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Keep Markdown tables only | No new schema or executor | Loses spans/types and produces unreliable numeric operations |
| Ask the answer model to parse and calculate | Minimal application code | Hallucination, rounding, hidden reasoning, and no reproducible operands |
| Store table JSON only in object storage | Portable immutable artifact | Weak queryability, scope enforcement, and relational validation |
| Load each table into DuckDB and allow generated SQL | Rich analytics and good local performance | Untrusted SQL is code; DuckDB can access files/network/extensions unless tightly sandboxed |
| Store validated structure in PostgreSQL and execute a closed typed operation plan | Reuses RLS/transactions and makes operands inspectable | Requires schema, type/unit rules, and a deliberately limited operation set |

DuckDB's own [security guidance](https://duckdb.org/docs/current/operations_manual/securing_duckdb/overview)
warns that untrusted SQL should be treated like arbitrary code. It may remain useful
for offline analysis but is not the recommended request-time execution boundary.

## Proposed decision

### Structured representation

Persist immutable generation-scoped `table_regions`, `table_columns`, and
`table_cells` beneath ADR 0026 provenance and tenant RLS. A table records its page,
bounding box, caption, header depth, dimensions, extraction revision, source crop,
structure checksum, confidence, and validation state. Each cell records row/column,
row/column spans, header associations, raw text, normalized text, inferred logical
type, normalized typed value, unit/currency, confidence, and its own bounding box
when available.

The normalized JSON/CSV representation is also written as an immutable object for
reproducibility and export, but PostgreSQL remains the authorization and execution
authority. Qdrant receives a summary/index representation and trusted table/region
identity, never the sole copy of structure.

### Validation

Promotion requires:

- rectangular/span consistency and no impossible cell overlaps;
- deterministic header association and stable reading order;
- explicit parsing for integer, decimal, percentage, currency, date, and text;
- preserved raw text beside every normalized value;
- unit/currency compatibility and declared rounding rules;
- source and structure checksums; and
- confidence thresholds that mark a table `retrieval_only` when exact execution is unsafe.

A failed exact-validation step does not discard useful visual/text evidence. It
prevents the table from entering the exact-calculation path.

### Calculation contract

Use a closed, versioned typed plan built by backend code:

```text
table identity + authorized generation
  -> selected row/column/cell identities
  -> one allowlisted operator
  -> typed operands with units
  -> deterministic result and rounding
```

The initial proposed operators are `lookup`, `count`, `sum`, `average`, `minimum`,
`maximum`, `difference`, and `ratio`. The router may map a question to this schema,
but backend validation resolves all table/cell identities and rejects unknown fields,
multiple plausible matches, mixed units, invalid types, excessive row counts, or an
unsupported operation. Execution uses parameterized, application-authored queries;
neither the user nor a model supplies SQL.

Every successful result stores a content-free calculation trace containing the
operator revision, table and cell identities, typed operands, units, rounding rule,
and result. If resolution is ambiguous, the system returns the relevant table
evidence or abstains instead of calculating.

## Recommendation

Approve PostgreSQL-backed normalized table structure and a closed typed calculation
plan. Use Docling accurate TableFormer as the first extraction candidate under ADR
0027, but let validation—not the extractor name—decide whether a table is eligible
for exact calculation. Do not add request-time DuckDB or generated SQL.

## Consequences

- Numerical answers become reproducible and inspectable rather than model arithmetic.
- PostgreSQL row volume increases, especially for large tables.
- The first operator set is intentionally narrow and may abstain on complex pivots,
  joins, formulas, and multi-table analytics.
- Better extraction models can replace the first candidate through successor
  generations without changing the execution safety contract.

## Approval questions

1. Approve PostgreSQL normalized tables plus immutable JSON/CSV artifacts?
2. Approve the proposed logical types, validation rules, and `retrieval_only` fallback?
3. Approve the eight-operation typed calculation allowlist?
4. Approve parameterized application queries only, with no generated SQL or request-time DuckDB?

## Acceptance evidence required after approval

- Migration, RLS, cross-workspace, lifecycle, and promotion-fault tests pass.
- Golden fixtures cover spans, multi-row headers, repeated labels, footnotes,
  percentages, currencies, units, scanned cells, and malformed tables.
- Supported calculations match exact expected operands/results; ambiguous,
  mixed-unit, malformed, or unsupported cases abstain.
- Calculation traces and public errors contain no raw private content, SQL, object
  keys, provider detail, or unauthorized identity.
