# Decision Log: Prevalence Estimator

Newest entries go at the bottom. Each entry records the decision, the reason, and what was rejected or deferred. Add an entry at the end of every working session.

---

## D-001 | 2026-10-02 | Purpose and required output

**Decision.** For each pilot and a set of case variants, the tool reports which variants are likely to be captured in a sample and at what sample sizes, and which are not.

**Why.** Variants differ in prevalence. High-prevalence variants are captured with high probability at modest sample sizes. Low-prevalence variants would need impractical sample sizes, so they get synthetic variants or a targeted search instead.

---

## D-002 | 2026-10-02 | Capture rule

**Decision.** A variant is "probable to be captured" if there are **at least N occurrences with at least M% probability at sample size S**. N and M are configurable per run, with optional per-variant overrides. N varies by use case (for example 10 for one, 20 for another).

**Why.** This is the business definition of an adequate sample, and it differs by use case, so it cannot be hardcoded.

---

## D-003 | 2026-10-02 | Bayesian approach

**Decision.** Use a Bayesian model.

**Why.**
1. Data is not always available, so priors (SME estimates) must be set explicitly.
2. Implementing Bayesian models is a learning goal.

---

## D-004 | 2026-10-02 | Model v1: independent Beta-binomial per variant

**Decision.** Each variant gets its own prevalence p ~ Beta(a, b). Count data (k occurrences out of n cases) updates it to Beta(a + k, b + n - k). The probability of at least N occurrences in a sample of size S is computed from the Beta-binomial posterior predictive.

**Why.** Variants are not mutually exclusive: one case can carry several variants. Each variant is therefore its own yes/no question about a case. The conjugate form is exact and needs no sampling, which suits a first implementation.

**Notes.**
- For a simple random sample, the finite population does not change the Beta-binomial predictive (exchangeability). The population acts as a cap on S, and matters if conditioning on data from the same window.
- P(X >= N) never decreases as S grows, so the minimum S can be found by binary search.

**Deferred.** Dirichlet-multinomial for exclusive sibling groups, and hierarchical models across strata. Both are candidates for the PyMC phase.

---

## D-005 | 2026-10-02 | Hierarchy handled as metadata in v1

**Decision.** Variants with structure (for example NIGO types such as Missing Plan Signature and Missing Participant Signature) are modeled as independent leaf variants, each with its own count out of total cases. A `parent` field is used for rollups and grouping in reports only.

**Why.** Some NIGO types are exclusive and others are not, and which is which is not known ahead of time. Independent leaves are the simplest model that still answers the sampling question.

---

## D-006 | 2026-10-02 | Stratification: support both views

**Decision.** Results can be produced per stratum (plan type, business, and so on), combined across strata, or both, selected by config (`stratum_view`).

**Why.** Sampling may need to be stratified, and stakeholders may need either a stratum-specific or an overall answer.

**Note.** The combined view uses known stratum shares of the population. Under proportional allocation it can be computed exactly by convolving the per-stratum Beta-binomial distributions.

---

## D-007 | 2026-10-02 | Versioning rules

**Decision.** A version is a change in **config or data**. Code changes are tracked separately (in git). Each run gets a fingerprint (hash of config plus data). A run whose fingerprint matches an existing run is **rejected**.

**Why.** The goal is a history of projections for the business, and every run must be reproducible from retained inputs.

---

## D-008 | 2026-10-02 | Storage deferred

**Decision.** Storage is out of scope for now. When added, it will be a simple relational database (SQLite) that records inputs and the config snapshot per run, supports comparing outputs across runs, and keeps tables long and tidy for possible Power BI use.

**Why.** Build the core model and planner first.

---

## D-009 | 2026-10-02 | Implementation conventions

**Decision.**
- Python, object-oriented.
- Nothing hardcoded. YAML config files wherever sensible, validated at load time.
- Math implemented by hand with Claude's help first (numpy/scipy), with a possible migration to PyMC later behind the same model interface.
- Run from the VS Code terminal for now.

---

## D-010 | 2026-10-02 | Outputs

**Decision.**
- Table output, with an option to write to Excel.
- A recommendation flag per variant: Sample, Borderline, or Synthetic / targeted search.
- Two reports: a working report for the analyst, and a more consumable report for business stakeholders.

---

## Open questions

- Exact thresholds for the recommendation flags (what multiple of the practical sample-size limit counts as Borderline).
- Allocation rule across strata for the combined view (proportional is assumed).
- Whether the stakeholder report needs charts in addition to tables.
- How SME priors will be elicited and documented (raw Beta parameters are stored in config, with a `source` label).
