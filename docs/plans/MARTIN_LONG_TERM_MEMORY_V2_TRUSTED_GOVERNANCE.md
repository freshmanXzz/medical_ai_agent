# Martin Long-Term Memory V2
## Trusted Memory Governance & Clinical Usability

> **Status**: Proposed V2 execution plan  
> **Target branch baseline**: current `main` as reviewed by Codex  
> **Primary objective**: evolve Martin from “can remember across sessions” to “can remember with trust, provenance, correction, lifecycle control, and clinically safe boundaries”.

---

## 1. Background

The current Martin memory system has already gone beyond the original SqliteStore V1.

The current `main` has already implemented and validated, to varying degrees:

- Cross-session doctor preference memory
- Separation of session checkpoints, business facts, and long-term memory
- Identity / authorization isolation
- Longitudinal comparison based on confirmed business Findings
- Store failure degradation
- Multiple memory categories
- Exact retrieval
- Temporal retrieval
- Semantic retrieval
- Unified retrieval routing
- Selective memory writing
- Independent vector index
- V1.1 Finding field backfill and related follow-up work

Therefore, **V2 should not repeat the original V1 goals**.

V2 is not primarily about adding another retrieval channel, another memory type, or another storage backend.

The V2 problem is:

> How can Martin know whether a remembered item is trustworthy, still valid, correctly scoped, traceable to its source, superseded by later information, or in conflict with confirmed clinical data?

The intended direction is:

```text
V1 / V1.x
Persistent Memory
    ↓
Cross-session retrieval
    ↓
Exact / Temporal / Semantic
    ↓
Router + Selective Writer
    ↓
V2
Trusted Memory Governance
    ↓
Clinical Usability
```

---

# 2. V2 Definition

## 2.1 Core definition

Martin Long-Term Memory V2 should be treated as a **governed memory layer**, not merely a persistent store.

A useful memory record should be able to answer:

1. What is this memory?
2. Who does it belong to?
3. Where did it come from?
4. When was it created or observed?
5. Is it still active?
6. Has it been corrected, superseded, withdrawn, or expired?
7. Is it a confirmed fact, an unverified claim, a doctor decision, a preference, a task, or discussion context?
8. Does it conflict with the Business DB?
9. Is Martin allowed to use it in the current context?
10. Why did retrieval choose to inject it into the model context?

V2 should make these questions answerable in code and testable in acceptance scenarios.

---

# 3. Non-goals

V2 should **not** reimplement capabilities that already exist unless the current implementation must be adjusted to support governance.

Do not make the following the primary V2 objective:

- Rebuilding the existing nine memory categories
- Rebuilding Exact Retrieval
- Rebuilding Temporal Retrieval
- Rebuilding Semantic Retrieval
- Rebuilding the current Router
- Rebuilding the Selective Writer
- Replacing the existing BGE embedding model
- Replacing the independent vector index solely for architectural cleanliness
- Moving confirmed clinical facts from Business DB into Memory Store
- Migrating to PostgreSQL without evidence that current SQLite concurrency or scale is insufficient
- Large-scale unrelated agent refactors
- Treating V1 acceptance as full clinical-system acceptance
- Solving real CT inference, full clinical safety, or every workstation production concern under the V2 memory task

Codex may modify an existing component when required, but should prefer **extension over duplication**.

---

# 4. First Step: Inspect the Current Main

Before implementation, inspect the current `main`.

Do not assume the exact schema, class names, module paths, namespaces, or storage layout from this document.

Codex should determine:

- Current memory record representation
- Current write path
- Current Selective Writer behavior
- Current exact / temporal / semantic retrieval flow
- Current Router behavior
- Current vector index mapping
- Current namespaces and ownership rules
- Current doctor / patient / case / thread authorization path
- Current Business DB Finding model
- Current longitudinal comparison implementation
- Current failure-degradation behavior
- Existing memory tests
- Existing live-acceptance tests
- Existing documentation that defines V1 / V1.1 behavior

The implementation should preserve validated behavior unless a change is necessary and explicitly justified.

A short current-state note is recommended before major code changes.

Codex may choose the document name and format.

---

# 5. Architectural Principle

Martin should keep three different concepts separate.

## 5.1 Confirmed Business Fact

Examples:

```text
Patient
Encounter
Study
Finding
Confirmed lesion size
Confirmed report result
Business authorization
```

These remain in the Business DB.

They are the primary source of truth for confirmed medical state.

---

## 5.2 Clinical Claim / Assertion

Examples:

```text
“The patient is allergic to penicillin.”
“The lesion should actually be labeled RUL.”
“I remember the previous study being about 6 mm.”
```

When such information is only expressed in conversation and has not gone through the appropriate business confirmation flow, it should not silently become a confirmed fact.

It may be represented as a claim, correction, pending assertion, memory item, or another equivalent structure.

The exact implementation is left to Codex.

The required semantic distinction is:

```text
unverified statement
≠
confirmed business fact
```

---

## 5.3 Discussion / Preference / Decision Context

Examples:

```text
Report conclusion should come first.
Keep routine reports concise.
We chose observation because the original images still required review.
Recheck the original images later.
```

These are legitimate long-term memories when they have future cross-session value.

They should remain distinguishable from confirmed medical facts.

---

# 6. Authority Model

V2 should make authority boundaries explicit.

A reasonable default order is:

```text
Confirmed Business Facts
    >
Explicit Current Doctor Instruction
    >
Valid Historical Doctor Memory
    >
Assistant Inference
```

This order does not have to be encoded as a single numeric field.

Codex may choose another implementation if it preserves the same safety property.

The important requirement is:

> Historical memory must not silently outrank current confirmed business state.

---

# 7. V2.1 — Trusted Memory

V2.1 is the highest-priority phase.

The focus is not memory volume.  
The focus is **trustworthiness and lifecycle**.

---

## 7.1 Provenance

Every long-term memory that may affect future responses should be traceable to its origin when technically possible.

Useful provenance may include:

- Original thread
- Original message
- Actor / source role
- Source type
- Creation time
- Observation time
- Case / patient context
- Tool or business event source where applicable

Codex should reuse existing IDs and metadata instead of inventing duplicate identity systems.

For migrated or legacy memories where provenance is incomplete:

- Preserve what is known
- Mark missing provenance explicitly
- Do not fabricate source message IDs or source events

Expected behavior:

```text
“Why does Martin remember this?”
    ↓
Martin / developer tooling can identify the source or state that the source is unavailable.
```

---

## 7.2 Claim / Fact Boundary

V2 should prevent conversational claims from being silently upgraded into confirmed medical facts.

Example:

```text
Doctor:
“Patient is allergic to penicillin.”
```

If this statement has not yet passed the system's confirmation or business update path, Martin should not behave as though the canonical allergy record has already been updated.

Possible implementation:

```text
Clinical Claim
status = unverified
source = doctor message
```

Later:

```text
verification / business confirmation
    ↓
Business DB update
```

Codex may choose a different representation.

The requirement is the semantic boundary, not the exact table design.

---

## 7.3 Correction

Doctors must be able to correct remembered information.

Example:

```text
Previous memory:
“Report should always be ≤ 200 characters.”

Later:
“For complex cases, do not enforce the 200-character limit.”
```

V2 should avoid destructive replacement when historical state is important.

The system should support the idea that:

```text
old memory
    ↓
superseded / retracted / invalid
    ↓
new valid memory
```

Codex may decide whether this uses:

- explicit status fields,
- version links,
- event records,
- replacement chains,
- append-only events,
- or another equivalent design.

What matters is that:

1. the latest valid state is retrievable,
2. old state does not leak into normal retrieval,
3. the history remains auditable when needed.

---

## 7.4 Retraction / Invalidation

Not every wrong memory needs to be replaced by a new one.

Example:

```text
“That note was wrong. Ignore it.”
```

Martin should be able to mark a memory as no longer valid.

Normal retrieval should not inject invalid / withdrawn memories into current context.

Historical inspection may still expose them.

---

## 7.5 Supersession

Where a newer memory changes an older one, normal retrieval should prefer the newer valid state.

Example:

```text
Old:
Routine reports ≤ 200 characters.

New:
Routine reports concise, but complex cases may exceed 200 characters.
```

The system should not return both as if they are equally current.

If both must be shown for audit, their relationship should be visible.

---

# 8. Retrieval Lifecycle Filter

Retrieval should not be treated as:

```text
search
↓
top-k
↓
prompt
```

V2 should enforce an additional governance stage.

Conceptually:

```text
Retrieve Candidates
    ↓
Authorization
    ↓
Scope Validation
    ↓
Lifecycle Validation
    ↓
Temporal Validity
    ↓
Supersession / Retraction Handling
    ↓
Conflict Detection
    ↓
Ranking / Budgeting
    ↓
Prompt Context
```

The exact implementation may be integrated into existing services.

Codex should avoid unnecessary architectural duplication.

The critical invariant is:

> A memory being retrievable from a store or vector index does not automatically mean it is eligible for prompt injection.

---

# 9. Vector Index Lifecycle Consistency

The vector index may still contain embeddings for memories that later become:

- superseded,
- invalid,
- retracted,
- expired,
- otherwise inactive.

V2 does not necessarily need to physically delete such vectors immediately.

But the system must guarantee that a stale vector hit cannot bypass lifecycle validation.

Conceptually:

```text
Vector hit
    ↓
Resolve memory identity
    ↓
Check authoritative memory state
    ↓
Only then consider prompt injection
```

Codex should adapt this to the current semantic retrieval implementation.

---

# 10. Conflict Validation

V2 should explicitly detect important memory conflicts.

At minimum, consider these categories.

## 10.1 Memory vs Business Fact

Example:

```text
Business DB:
location = LUL

Later doctor statement:
“Correction: it should be RUL.”
```

The correction must not silently mutate the confirmed Business DB unless an explicit business update path is executed.

Instead, Martin should be capable of representing:

```text
confirmed business value = LUL
doctor correction claim = RUL
conflict = present
```

A model answer should not silently choose one and present it as unambiguous truth.

---

## 10.2 Memory vs New Memory

Example:

```text
Old preference:
≤ 200 characters

New preference:
Complex cases may be longer
```

The lifecycle system should resolve which one is current.

---

## 10.3 Discussion vs Confirmed Fact

A prior speculative discussion must not become a confirmed diagnosis merely because it was recalled many times.

---

# 11. Prevent Self-Reinforcing Memory

V2 should explicitly guard against self-reinforcing model memory.

Failure pattern:

```text
Assistant inference
    ↓
stored as memory
    ↓
retrieved in later session
    ↓
treated as historical evidence
    ↓
assistant becomes more confident
```

Example:

```text
Assistant:
“This lesion may be high risk.”
```

This should not automatically become:

```text
confirmed patient risk = high
```

The current Selective Writer may already prevent part of this problem.

Codex should inspect existing behavior and add only the missing safeguards.

The intended rule is:

> Assistant-generated inference cannot promote itself into confirmed clinical truth without an appropriate external confirmation source.

---

# 12. Stable Lesion / Finding Identity

Stable cross-study lesion identity is important for longitudinal reasoning.

However:

> Stable lesion identity is primarily a Business / Clinical Entity Continuity problem, not a Memory Store problem.

Example desired model:

```text
Lesion Entity: lesion_001
    │
    ├── Observation 2026-06
    │     └── 6 mm
    │
    └── Observation 2026-09
          └── 8 mm
```

This allows Martin to distinguish:

```text
“two observations are both present”
```

from:

```text
“the same lesion changed from 6 mm to 8 mm”
```

V2 should define and test this boundary, but Codex should decide whether stable lesion identity belongs inside this implementation cycle or should be split into a parallel business-layer task.

Do not force lesion identity into the long-term memory store simply to satisfy V2.

At minimum, V2 documentation should state when longitudinal comparison is:

- based on stable lesion identity,
- based only on weaker matching,
- or unable to establish continuity.

---

# 13. Historical Validity vs Current Validity

Avoid using naive TTL rules for clinical observations.

Example:

```text
2024 CT:
lesion = 6 mm
```

In 2026 this may no longer be the current value, but it remains a valid historical observation.

Therefore:

```text
historically valid
≠
currently active value
```

V2 should preserve historical observations needed for longitudinal reasoning.

Codex may model this with:

- observed_at,
- valid_from,
- valid_until,
- effective intervals,
- current flags,
- supersession relationships,
- event sourcing,
- or another appropriate mechanism.

Do not delete clinically useful longitudinal data simply because it is old.

---

# 14. Where TTL Is Appropriate

TTL may still be useful for some memory types.

Examples:

- Temporary workflow preferences
- Short-lived tasks
- Temporary reminders
- Ephemeral operational state
- Time-bounded contextual instructions

TTL should not be applied mechanically to all medical observations.

Codex should decide which existing memory types benefit from TTL based on semantics and current implementation.

---

# 15. V2.2 — Memory Growth & Consolidation

After V2.1 trust semantics are stable, address long-term memory growth.

Primary problems:

- Duplicate memories
- Near-duplicate memories
- Repeated preferences
- Repeated discussion conclusions
- Very long histories
- Excessive prompt injection
- Summary drift
- Loss of provenance during summarization

---

## 15.1 Candidate Review / Deduplication

Existing Selective Writer behavior should be reviewed first.

Do not rebuild it unnecessarily.

The next step should focus on whether repeated statements produce redundant memory records.

The system may distinguish:

```text
duplicate
update
new information
```

Codex may use:

- deterministic keys,
- normalized content,
- structured fields,
- semantic similarity,
- temporal context,
- or a hybrid.

Do not rely solely on embedding similarity for identity decisions where deterministic metadata is available.

---

## 15.2 Rolling Summary

Long-running patient or doctor memory may benefit from a rolling summary.

However, summaries must not destroy traceability.

Preferred property:

```text
Summary:
Doctor usually places conclusions first and emphasizes spiculation.

Sources:
message A
message B
message C
```

A summary should be considered a projection over source memories, not a magical new source of truth.

Codex should determine whether current storage already supports this cleanly.

---

## 15.3 Summary Correction

If a source memory becomes superseded or invalid, summary state must not remain permanently stale.

Possible strategies include:

- regenerate summary,
- update affected summary segment,
- mark summary stale,
- compute summary from active source set,
- another equivalent method.

No single method is mandated.

The acceptance criterion is that stale source memories should not continue to influence the “current” summary indefinitely.

---

## 15.4 Prompt Injection Budget

Long-term memory should not consume an unbounded amount of context.

V2.2 should define a measurable injection budget.

Possible dimensions:

- maximum number of memory items,
- maximum tokens,
- category quotas,
- recency / relevance balance,
- exact memory priority,
- semantic memory priority,
- clinical importance.

Codex should choose the implementation based on the current Router and context builder.

---

# 16. V2.3 — Retrieval Reliability & Operations

After trust and growth governance are stable, make reliability measurable.

Candidate metrics include:

- Relevant-memory recall
- Irrelevant-memory rate
- Wrong-patient retrieval rate
- Wrong-doctor retrieval rate
- Superseded-memory leakage rate
- Invalid-memory leakage rate
- Conflict detection rate
- Provenance coverage
- Retrieval latency
- Semantic retrieval timeout rate
- Store timeout behavior
- Vector index failure behavior
- Prompt injection token usage
- SQLite lock / write contention under concurrent access

Not every metric must be implemented exactly as listed.

Codex should select a practical set that can be reliably measured in the current codebase.

---

# 17. Failure Degradation

V1 already includes degradation behavior.

V2 should preserve and extend it rather than replacing it.

## 17.1 Store Failure

If long-term memory is unavailable:

```text
Business DB available
    ↓
Current confirmed case facts remain usable
```

Martin should not fabricate:

- prior preferences,
- historical discussions,
- prior decision rationale,
- previous tasks.

The answer should be able to indicate that memory retrieval is unavailable when that limitation affects the answer.

---

## 17.2 Vector Index Failure

If semantic retrieval fails:

- Exact retrieval may continue
- Temporal Business DB retrieval may continue
- Confirmed longitudinal facts may still be available
- Semantic historical discussion may be unavailable

The system should degrade by capability rather than failing everything.

---

## 17.3 Partial Provenance

If a legacy memory has incomplete provenance:

- it may still be usable if otherwise valid,
- but the system must not invent missing provenance,
- lower trust or restricted use may be appropriate.

Codex should determine the appropriate handling.

---

# 18. Privacy, Scope, and Isolation

Existing authorization isolation must be preserved.

At minimum:

```text
Doctor A private memory
≠
Doctor B private memory
```

and:

```text
Patient Alpha memory
must not leak into
Patient Beta context
```

Doctor-level preferences may legitimately span patients when their scope is doctor-level.

V2 should not break existing scope semantics while adding lifecycle logic.

---

# 19. Recommended V2.1 Acceptance Scenarios

The exact tests may be adapted to the current API and test harness.

The following behaviors should be covered.

---

## Scenario A — Preference Provenance

Doctor says:

```text
“以后报告结论放前面。”
```

New session asks for a report.

Expected:

- preference is recalled,
- source is traceable,
- correct doctor scope is preserved.

---

## Scenario B — Current Instruction Overrides Historical Preference

Historical memory:

```text
“报告控制在 200 字以内。”
```

Current session:

```text
“这次详细写，不限制字数。”
```

Expected:

- current instruction wins for this session,
- historical preference is not necessarily deleted,
- Martin does not force the old rule onto this answer.

---

## Scenario C — Preference Supersession

Old:

```text
“报告控制在 200 字以内。”
```

Later:

```text
“以后复杂病例不用限制 200 字。”
```

Expected:

- newer valid rule becomes effective,
- obsolete interpretation does not leak into normal retrieval,
- historical relationship remains inspectable.

---

## Scenario D — Retraction

Doctor says:

```text
“刚才那条偏好记错了，取消。”
```

Expected:

- target memory becomes inactive / retracted / equivalent,
- future sessions do not apply it,
- audit history remains available.

---

## Scenario E — Claim vs Confirmed Fact

Doctor states:

```text
“患者青霉素过敏。”
```

No business confirmation has occurred.

Expected:

- statement can be retained as an unverified claim if appropriate,
- it is not silently represented as a confirmed canonical allergy fact.

---

## Scenario F — Correction vs Business DB

Business DB:

```text
location = LUL
```

Doctor says:

```text
“更正，应该是 RUL。”
```

Expected:

- correction is preserved,
- Business DB remains unchanged unless an explicit business update occurs,
- conflict can be surfaced,
- future answers do not silently hide the disagreement.

---

## Scenario G — Assistant Self-Reinforcement

Assistant previously says:

```text
“This lesion may be high risk.”
```

Expected:

- this statement does not become confirmed clinical truth merely through memory persistence,
- later retrieval does not falsely treat it as authoritative doctor evidence.

---

## Scenario H — Superseded Semantic Hit

A superseded memory remains in the vector index and is semantically similar to the current query.

Expected:

- vector search may return the candidate internally,
- lifecycle validation prevents obsolete memory from entering normal prompt context.

---

## Scenario I — Doctor Isolation

Doctor A has private memory about Alpha.

Doctor B has access to Alpha's case but not A's private memory.

Expected:

- B does not automatically receive A's private discussion context.

---

## Scenario J — Patient Isolation

Alpha has a stored decision rationale.

Query is made in Beta context.

Expected:

- Alpha memory is not injected.

---

## Scenario K — Store Failure

Long-term memory store unavailable.

Business DB contains current case facts.

Expected:

- current case analysis still works where possible,
- historical memory-dependent claims are not fabricated,
- degradation is explicit when relevant.

---

## Scenario L — Historical vs Current Value

Historical observation:

```text
2024: 6 mm
```

Later observation:

```text
2026: 8 mm
```

Expected:

- 2024 observation remains historically valid,
- 8 mm may be current,
- old data is not deleted merely because of age,
- longitudinal reasoning preserves chronology.

---

# 20. Live Acceptance

After unit / integration tests pass, run real-model acceptance using isolated synthetic clinical data.

At minimum include:

1. doctor preference + later override,
2. supersession or retraction,
3. claim vs confirmed fact,
4. memory vs Business DB conflict,
5. semantic retrieval of a superseded memory,
6. Store failure,
7. cross-doctor isolation,
8. cross-patient isolation.

Live acceptance should evaluate the **final model answer**, not only whether retrieval returned the right records.

This matters because correct retrieval can still produce unsafe phrasing.

---

# 21. Regression

Run the existing test suite relevant to:

- memory,
- entity isolation,
- RAG,
- REST,
- WS,
- permissions,
- longitudinal comparison,
- report generation,
- failure degradation.

Then run the full regression suite if feasible.

V2 must not be considered accepted solely because new V2 tests pass.

---

# 22. SQLite vs PostgreSQL

Do not migrate to PostgreSQL by default.

Keep SQLite unless measurements demonstrate a real limitation.

Potential triggers for reconsideration:

- repeatable multi-process write contention,
- unacceptable lock duration,
- operational instability,
- dataset size / indexing behavior that materially impacts latency,
- deployment topology that requires a shared DB service.

If such evidence appears during V2.3, document it and propose a separate migration plan.

---

# 23. Implementation Freedom for Codex

This document intentionally defines **behavioral requirements and safety boundaries**, not a mandatory class diagram.

Codex should have freedom to decide:

- whether to extend existing memory metadata or introduce a new structure,
- whether lifecycle is represented by status fields, version chains, events, or another design,
- whether claim handling belongs in the memory service or a neighboring domain layer,
- how much of stable lesion identity belongs in V2 vs a parallel business-layer task,
- how existing Router / Writer / retrieval services should be extended,
- whether lifecycle validation is a new module or integrated into current retrieval code,
- whether summaries are materialized or computed,
- how migrations should be performed,
- how API / developer tooling should expose provenance and lifecycle.

However, any chosen design should preserve these invariants:

```text
1. Confirmed business facts remain authoritative.
2. Unverified claims are distinguishable from confirmed facts.
3. Memory provenance is preserved when available.
4. Superseded / invalid memories do not leak into normal retrieval.
5. Corrections do not silently rewrite Business DB facts.
6. Assistant inference cannot self-promote into confirmed truth.
7. Scope and authorization isolation remain intact.
8. Historical clinical observations are not destroyed by naive TTL.
9. Semantic retrieval cannot bypass lifecycle validation.
10. V1 / V1.x validated capabilities continue to work.
```

---

# 24. Suggested Phase Plan

## V2.1 — Trusted Memory

Priority:

```text
Provenance
    ↓
Claim / Fact Boundary
    ↓
Supersession / Retraction
    ↓
Conflict Validation
    ↓
Retrieval Lifecycle Filter
```

This is the main V2 implementation target.

---

## V2.2 — Memory Governance

Then address:

```text
Deduplication
Rolling Summary
Summary Source Pointers
Growth Control
Prompt Injection Budget
```

---

## V2.3 — Production Reliability

Finally measure:

```text
Retrieval Quality
Latency
Leakage
Timeouts
Failure Degradation
Concurrency
SQLite Limits
```

---

# 25. Deliverables

At the end of each phase, update or create implementation documentation.

For V2.1, the final implementation report should explain:

- Current baseline
- What changed
- Final trust model
- Provenance model
- Claim / fact boundary
- Supersession / retraction behavior
- Conflict behavior
- Retrieval lifecycle filtering
- Business DB boundary
- Migration / compatibility handling
- Test results
- Live acceptance results
- Remaining limitations
- Deferred decisions
- Recommendations for V2.2

Codex may choose the exact filenames to fit the repository's current documentation structure.

---

# 26. Definition of Done for V2.1

V2.1 is complete when Martin can reliably demonstrate:

```text
记得住
+
知道从哪里记来的
+
知道这是不是事实
+
知道现在还是否有效
+
知道有没有被纠正
+
知道有没有和业务库冲突
+
知道这次回答该不该使用
```

The implementation should make Martin's long-term memory **governed, auditable, and clinically safer**, rather than simply larger.

---

# 27. Final Principle

V1 answered:

> Can Martin remember across sessions?

V2 should answer:

> Can Martin remember the right thing, with the right authority, at the right time, for the right doctor and patient, and still explain where that memory came from?

That is the standard for this V2.
