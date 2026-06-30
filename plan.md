# JORADP Pipeline — Improvement Plan

_Generated 2026-06-28 after reviewing the 2020–2026 sample run._

Goal recap: turn JORADP OCR text into a structured **legal database with act
versioning & lineage** (which act amends / supplements / abrogates which).
The pipeline has 4 stages: `structure → enhance → infer → view`.

---

## 1. Where we are (what the review found)

### Working well ✅
- **Structure stage is solid and lossless.** Across the 2020–2026 sample it
  detected 49 / 29 / 32 / 48 / 19 acts per issue with `[LOSSLESS]` on every run.
- **TOC-vs-act disambiguation fixed.** The `in_toc_section` gate + lowered
  `_RE_TOC_DOTS` threshold stopped budget tables (JO-2022 had 3,185 false index
  rows → now 33) and stopped TOC entries being parsed as fake acts.
- **OCR split-word regexes fixed.** `مؤر خ` → matches `_DATED`, `ماد ة` →
  matches `_RE_ARTICLE`. This was the root cause of "2 acts" on JO-2020-001.
- **Numeral normalization** (Arabic-Indic / Farsi → ASCII) applied at load time.
- **Key rotation works** — cycles through `.groq_key`, `.groq_key2020`,
  `.groq_key2`, `.groq_key3` on 429.
- **Resumability works** — re-runs skip already-enhanced acts.

### Sample run scorecard
| JO | acts | enhanced | light | full | errored |
|----|------|----------|-------|------|---------|
| JO-2020-001 | 49 | 48 | 1 | 47 | 1 (400) |
| JO-2021-001 | 29 | 24 | 3 | 21 | 5 (1×400, 4×quota) |
| JO-2022-001 | 32 | ~2 | — | — | ~30 (quota) |
| JO-2023–2026 | — | 0 | — | — | not reached (quota) |

---

## 2. Problems, ranked by impact

### P1 — Quota is the binding constraint 🔴 (blocks everything)
Groq free tier = **200K tokens/day per key, 8K tokens/minute**. Four keys ≈ 800K
TPD in theory, but a *single* JO of 30–50 acts in **full mode** burns a large
share of that, because **every act re-sends the full ~1.5K-token system prompt +
its raw text**. Result: we cannot finish even 7 sample issues in a day, and the
full corpus is **1,333 issues** — infeasible at the current cost-per-act.

This is the #1 thing to fix. Everything else is secondary.

### P2 — Large acts fail with HTTP 400 `json_validate_failed` 🔴
`act-005` (21K chars) and `JO-2021-act-019` failed. The model's JSON output is
truncated past `max_output_tokens=4000`, producing invalid JSON. The truncation
cascade in `_enhance_one` only triggers on the string `"413"` — it does **not**
catch 400, so these acts are simply lost.

### P3 — The quality metric is a false-positive factory 🟠
`_reconcile`'s "N/M long words absent" warning compares **raw OCR words against
cleaned output without normalizing either side**. Inspection of the flagged
`act-001`: the 19 "missing" words were `المادّة` (shadda) → cleaned to `المادة`,
plus OCR-split fragments `الرّ`, `الشّ`, `سميّة`, `مؤرّ`. **These are successful
cleanups, not content loss.** The metric currently cannot be trusted, which means
*real* content loss is invisible. (The `articles N->M (fewer)` / `measures`
warnings are meaningful and should be kept.)

### P4 — No graceful handling of total quota exhaustion 🟠
When all keys are 429, every remaining act still runs the full 5-cycle retry
(slow) and is written with `_error`. JO-2022 burned minutes failing 30 acts
one-by-one. The run should detect global exhaustion, **stop cleanly, save
progress, and print resume instructions**.

### P5 — Enhance is fully serial with a fixed 1s delay 🟡
No concurrency; `delay=1.0` between every act. Each key has its **own** 8K-TPM
bucket, so we could run keys in parallel for ~4× throughput. At current speed the
full corpus would take weeks of wall-clock even ignoring quota.

### P6 — `light`/`full` threshold is crude 🟡
`_LIGHT_CHARS=4500`. Light mode **drops the body entirely** (metadata only). Long
*legislative* acts >4500 chars silently lose their article text, while short
*administrative* personnel acts get expensive full treatment they don't need. The
split should be driven by **act kind**, not just length.

### P7 — No global lineage graph (this is the actual deliverable) 🟠
`infer` resolves cross-references *within* a single JO. But the project goal —
"act A amended by act B in JO-YYYY-NNN, abrogated by act C" — requires a
**corpus-wide resolver** that links `ref_id` mentions (e.g. `مرسوم-19-369`)
across *all* issues into a versioning/lineage graph. This does not exist yet.

### P8 — Output sprawl, no canonical store 🟡
Eight output dirs (`fix_test`, `fix_test2`, `fix_test3`, `sample_*`, …). There is
no single consolidated database — the end product the whole pipeline is meant to
produce.

---

## 3. Plan of action (phased)

### Phase A — Make enhancement survivable & cheap (unblocks the corpus)
1. **Fix the 400 cascade (P2).** In `_enhance_one`, treat `400`/
   `json_validate_failed` the same as `413` → fall into the truncation cascade.
   Additionally, for large legislative acts raise `max_output_tokens` (e.g.
   8000) and, when an act has many articles, **enhance it in article batches**
   instead of one giant request.
2. **Cut token cost per act (P1).**
   - **Shrink the system prompt.** It's ~1.5K tokens re-sent on every call.
     Trim examples, move the JSON schema to a terse form.
   - **Skip the LLM for trivial administrative acts.** Personnel
     appointments/terminations (the bulk of admin acts) are already parsed well
     deterministically; send them through a cheap metadata-only path (or no LLM
     at all). Reserve full mode for legislative acts.
   - **Drive light/full by `kind`, not length (P6):** legislative → full (with
     body); administrative → light/deterministic.
3. **Graceful exhaustion (P4).** Track consecutive "all keys exhausted" failures;
   after the first, stop the run, persist what's done, and print a one-line
   resume command. Re-run already resumes via skip-logic.
4. **Add a token budget meter.** Estimate tokens/act and print a running
   per-key total so we can see how close we are to 200K before hitting the wall.

### Phase B — Trustworthy quality signal
5. **Fix `_reconcile` (P3):** strip tashkeel (`_dt`) and apply `_norm` to **both**
   raw and enhanced word sets before diffing; drop OCR-fragment-length tokens.
   Keep the `articles/measures (fewer)` checks. Goal: a warning means real loss.
6. **Re-run the 2020–2026 sample** and confirm the "words absent" noise is gone
   and only genuine issues remain.

### Phase C — Throughput
7. **Parallelize enhance across keys (P5).** One worker per key (each key has its
   own TPM bucket); within a key, respect 8K TPM. Evaluate Groq's batch API.
8. Tune `delay` down once concurrency + per-key TPM accounting are in place.

### Phase D — The actual product: lineage DB
9. **Consolidate outputs (P8).** One canonical `db/` (e.g. SQLite or a single
   JSONL per year) keyed by `act_id`; deprecate the scratch `fix_test*` dirs.
10. **Global cross-reference resolver (P7).** After all issues are enhanced,
    build a corpus-wide graph: resolve every `ref_id` to a real act, materialize
    `amends / supplements / abrogates / replaces` edges, and compute each act's
    **version chain** (original → amendments → current/abrogated status).
11. **Lineage view.** Extend the viewer (or add a new one) to show an act's
    amendment history and what it amends/abrogates.

### Phase E — Scale to full corpus
12. Run year-by-year (2010→2026), resuming on quota, writing into the canonical
    DB. Track coverage (issues done / 1,333).

---

## 4. Suggested immediate next steps (this session / next)
- [ ] **P2 + P4**: fix the 400 cascade and add graceful exhaustion — small,
      high-leverage edits to `_enhance_one` / `do_enhance`.
- [ ] **P3**: fix `_reconcile` normalization so warnings mean something.
- [ ] Re-run JO-2020-001 (already structured) to validate P2/P3 with quota to
      spare, then expand to the rest of the sample as quota allows.
- [ ] Decide on the canonical store format (SQLite vs JSONL) before Phase D.

## 5. Open questions for you
- **Quota strategy:** stay on Groq free tier + more keys, or move to a paid tier
  / different provider? This decides whether P1 mitigations are "nice" or
  "mandatory."
- **Admin acts:** OK to handle personnel appointment/termination acts
  deterministically (no LLM) to save ~80% of calls? They rarely contain
  cross-references that matter for lineage.
- **Canonical store:** SQLite (queryable, good for lineage graph) vs JSONL
  (simple, git-friendly)?
