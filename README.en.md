# Peer Company Selector (audit-peer-selector)

[🇰🇷 한국어](README.md) | 🇺🇸 English

Give it one company and it returns financially comparable **peer companies, ranked**. And a
**harness that automatically scores how well it does that**. The engine is replaceable; the scorer stays.

---

## 1. Introduction

In the **analytical procedures** of a first-year audit, an auditor detects risk by asking whether a
target's financial ratios are outliers relative to its peers. To do that, you must first answer
**"what do we compare this company against?"** This tool answers that question from data — feed it one
target and it returns a ranked peer list, each peer annotated with *why* it was chosen and *how much* to
trust the comparison.

Key distinctions:

- **Multi-axis similarity scoring, not filtering.** Industry, size, market cap, business description, and
  growth are treated as **scoring features**, not knockout conditions. Because no candidate is dropped in
  a single step, good peers near a boundary are never lost.
- **Confidence grade, rationale, and check-needed flags on the output.** Each peer list carries a
  confidence level (HIGH/MEDIUM/LOW), an axis-by-axis rationale, and "check-needed" flags where the target
  deviates far from the peer median.
- **Performance verified by a scoring harness.** On the principle that "good peers predict the target's
  financial ratios well," peer quality is scored automatically **without ground-truth labels** — so every
  change can be confirmed as a number.

**Universe:** Korean listed companies KOSPI + KOSDAQ, 2016–2025. Unlisted and overseas firms are excluded
on data grounds (rationale in §4 and `docs/`). Delisted firms are kept as candidates for the point in time
when they were alive (no survivorship bias).

---

## 2. How to run

### Prerequisites
- Python 3
- Libraries: `numpy`, `pandas`, `pyarrow` (parquet), `PyYAML`, `scikit-learn` (business-text vectors)
- An OpenDART API key (for financial/disclosure data)

### OpenDART key
1. Get an API key at https://opendart.fss.or.kr (free, 40 characters).
2. Copy `.env.example` to `.env` and fill in the value:
   ```
   OPENDART_API_KEY=your_key
   ```
3. The key is **never stored in files or logs.** `.env` is gitignored, and the code reads the key from
   the environment (or `.env`) and uses it only as an API request header — it is not logged.

### You can view results without running anything
Pre-computed real outputs ship with the repository:
- `runs/2026-07-16_loop8/sample_reports.json` — finished peer-selection report examples (§3 below).
- `docs/FINAL_REPORT.md` — final out-of-sample performance, limits, and usage guide.

### To reproduce it yourself
The point-in-time data layer is not committed (size). Reproduction goes:

1. **Build the point-in-time data** (needs OpenDART; fetches are cached on disk so re-runs don't re-call):
   ```
   python scripts/pit_build.py        # financial / industry / size point-in-time snapshots
   ```
   Business-text, market-cap, growth, and segment features are filled by separate build scripts (full
   sequence in `docs/LOOP_LOG.md`).
2. **Run an engine** → peer list (`peers.parquet`):
   ```
   python -m engines.baseline.run      # industry + size baseline
   python -m engines.similarity.run    # multi-axis similarity (L6)
   ```
3. **Build the report** → output with confidence grade, rationale, and check-needed flags:
   ```
   python scripts/build_report.py      # → runs/…/sample_reports.json, peer_report.csv, thresholds.json
   ```

> The engine (`engines/`) and the scorer (`scoring/`) never import each other. Their only contact point is
> the `peers.parquet` file (blocking "cheating off the answer sheet" — see §4).

---

## 3. Example output (pre-computed real output)

The following is taken verbatim from `runs/2026-07-16_loop8/sample_reports.json`. All examples are from the
**dev period (as-of 2022-05-15)** (holdout not used).

### Confidence HIGH — target `00100601` (peer cohesion 0.5337)
Top peers (rank, similarity, per-axis rationale):

| rank | peer | similarity | industry | size | mktcap | text | growth |
|--:|---|--:|--:|--:|--:|--:|--:|
| 1 | 00863038 | 0.568 | 0.107 | 0.193 | 0.129 | 0.129 | 0.010 |
| 2 | 00328191 | 0.549 | 0.000 | 0.240 | 0.137 | 0.110 | 0.062 |
| 3 | 00445160 | 0.543 | 0.214 | 0.198 | 0.082 | 0.043 | 0.007 |

- **rationale** = weight × per-axis similarity; the sum is that peer's similarity score ("why is this a peer").
- Ratio diagnosis for this target (peer median = prediction):

| ratio | peer median | target actual | deviation | check-needed | comparable |
|---|--:|--:|--:|:--:|:--:|
| gross margin | 0.208 | 0.112 | 85.2% below | — | yes |
| operating margin | 0.057 | 0.043 | 30.8% below | — | yes |
| receivables turnover | 4.425 | 3.094 | 43.0% below | — | yes |

### Confidence MEDIUM — target `00101257` (cohesion 0.4902) · "check-needed" example
- Inventory turnover: peer median 16.90 vs target 1.96 → **deviation 763%, `check_needed=true`.** Shown as a
  **weak signal** ("worth a human look") that the target is unusually far from its peers.

### Not-comparable example — target `00100939`
- Gross margin: target actual 0.024, near break-even → **`comparable=false`, note "not comparable
  (near break-even)".** The denominator (earnings) is near zero, so the ratio comparison is structurally
  unsuitable (see the ceiling in §4).

### Output schema (excerpt)
```json
{
  "target": "<corp_code>", "as_of": "YYYY-05-15",
  "peer_confidence": "HIGH | MEDIUM | LOW",   // dev tertile of peer cohesion (mean top-k similarity)
  "peers": [ { "rank": 1, "peer_code": "…", "similarity": 0.57,
               "rationale": { "industry":…, "scale":…, "mktcap":…, "text":…, "growth":… } } ],
  "ratios": [ { "ratio": "…", "peer_median": …, "target_actual": …,
                "deviation_pct": …, "check_needed": false, "comparable": true } ]
}
```
A generic CSV (`peer_report.csv`) is emitted too. Full schema: `docs/OUTPUT_FORMAT.md`.

---

## 4. Design principles and hurdles cleared ★ the heart of this project

This matters more than the results — **how the thinking went.** (Details in `docs/JOURNEY.md`.)

### Principle 1 — clearing the absence of ground-truth labels
There is no answer key for "this company's true peer set." Market peer lists (broker reports, etc.) are
labels contaminated by valuation/IPO-pricing purposes and differ from audit comparability → **not used.**
Instead we score by **financial-ratio prediction error**: take the median of the ratios of the engine's
peers as the target's prediction, and measure peer quality by the error (APE) against the actual. This
scorer (the "oracle") is built and **frozen first**, and only then is the engine touched — to structurally
block the self-deception of adjusting the ruler when the score looks bad.

### Principle 2 — scoring, not filtering
Filtering candidates by industry/size cannot bring a dropped candidate back; good peers near a boundary are
lost by construction. So we **score and rank every ticker.** Industry, size, market cap, business content,
and growth are features, not knockout conditions.

### Principle 3 — no hardcoding, no lookahead, no survivorship bias (structurally enforced)
- **No hardcoding:** no ticker/company-name literals, no arbitrary threshold constants. Constants
  (penalty, separation, confidence-grade cutoffs) are all derived from the dev data distribution.
- **No lookahead:** a peer at time T is chosen using only information before T. Disclosures are indexed by
  filing date, and post-T amendments are treated as unavailable.
- **No survivorship bias:** a firm that was listed at T stays in the T candidate pool even if it has since
  been delisted.

### Hurdle 1 — the trap of scoring yourself
If the engine could see the scored accounts (those that compute the 4 ratios), it could cheat by picking
"5 with similar margins" for a perfect score. So engine input is restricted to an allow-list (industry,
size, market cap, business text, growth), and the engine (`engines/`) and scorer (`scoring/`) are
**physically separated** (no mutual import; the only contact is the `peers.parquet` file). Beyond that, a
**development side and a verification side are separated**: the verification side does not trust the
development code and **re-aggregates independently** from the raw data.

### Hurdle 2 — design errors in the verification gates themselves
The data-quality gates were designed wrong several times — putting headcount in the required accounts, or
encoding a tautology (always true by definition), circular reasoning, or an unmeasurable criterion — **six
times.** Each time the harness caught it, and the check rule was added in **code**, not prose (even checking
"can this criterion logically fail?"). A gate violation where work proceeded despite a `FAIL`, false-label
incidents where an output label disagreed with the actual data, and an account-mapping bug — all were
**recorded rather than hidden, with recurrence blocked in code.** That process is itself the core design.
(Failures are logged in `docs/DECISIONS.md` with root cause, never buried.)

### Hurdle 3 — reading results honestly
The holdout (2023–2025) was sealed throughout development, all settings were frozen (hash-pinned), and it
was opened **exactly once.**

- **What was verified:** out-of-sample, the final engine beat the industry+size baseline by **−10%,
  significantly** (a firm-clustered bootstrap confidence interval that excludes 0), and the dev ranking held
  fully on the holdout (a real improvement, not overfitting).
- **What fell short (not hidden):** the ambitious target line (baseline −20%) was missed. The wall reached
  by measuring all six axes, prediction methods, and neural embeddings is **median APE ≈ 0.50.** This is not
  a failure but a coordinate of the **structural ceiling of "predicting financial ratios from a peer
  median"** — the residual error is business heterogeneity within the peer group, which no further peer
  refinement removes. **Knowing this limit is the precondition for audit use.**

Conclusion: this tool is usable as a "better peer selector + anomaly detector" (verified), but not as a
precise predictor. **Demonstrating the ceiling** is the result.

---

*See `docs/JOURNEY.md` for the design journey, `docs/FINAL_REPORT.md` for final performance and limits, and
`docs/ORACLE.md` for the frozen scoring spec. This is a local tool for educational and research purposes.*
