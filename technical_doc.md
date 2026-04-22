# Technical Design Dossier: Atlas Knowledge Fabric

## 1. Executive Overview
Atlas Knowledge Fabric is a distributed retrieval and reasoning platform designed for enterprise technical documentation, change logs, runbooks, architecture decision records, and post-incident analysis. The platform serves engineering, support, and operations teams that need fast answers from large internal corpora without losing source attribution. The core product goal is to reduce the time between a user question and a trustworthy technical answer.

The design prioritizes four properties:
1. Precision under ambiguity.
2. Low-latency retrieval at scale.
3. Explainable answers with visible evidence.
4. Operational resilience during partial infrastructure failure.

Atlas is typically deployed across three logical planes: an ingestion plane, an indexing plane, and a query execution plane. Each plane scales independently and can be throttled without fully disabling the others. This isolation reduces blast radius during document storms, re-indexing events, or model upgrades.

## 2. Problem Statement
Traditional enterprise search often fails for technical documents because terminology is inconsistent and critical knowledge is buried inside long paragraphs, code samples, and operational caveats. Simple keyword search does not understand that "replication lag", "write delay", and "commit propagation latency" may refer to overlapping phenomena. Naive chunking makes the problem worse by cutting paragraphs in arbitrary places, which separates a design decision from its constraints, risks, or mitigation steps.

The Atlas platform addresses this by combining structured chunking, retrieval scoring, evidence-aware answer composition, and interface elements that show why a result was selected.

## 3. Reference Deployment Topology
The reference deployment uses the following components:

- Edge API Gateway for authentication, rate limiting, and request shaping.
- Query Coordinator service that routes user questions through retrieval, reranking, and response synthesis.
- Ingestion Workers that normalize Markdown, HTML, PDF text, and exported wiki pages.
- Document Registry backed by PostgreSQL for source metadata, ownership, and retention policies.
- Vector Index cluster for semantic retrieval.
- Lexical Index for exact match, identifiers, and code-heavy queries.
- Result Cache using Redis for repeated technical questions.
- Observability stack using OpenTelemetry, Prometheus, and Grafana.

Each document is assigned a `source_id`, `owner_team`, `confidence_tier`, `freshness_window`, and `access_scope`. The access scope is enforced before retrieval results are shown to the end user. Atlas never relies on the answer synthesis layer to hide sensitive data after the fact; authorization occurs during candidate selection.

## 4. Ingestion Pipeline
The ingestion pipeline is event-driven. A source connector detects a change in a repository, knowledge base, or file bucket and publishes a `document.changed` event. The event is consumed by a normalization worker that extracts readable text, preserves heading hierarchy, and attaches metadata. A segmentation worker then creates semantic sections that align with headings, lists, code blocks, and paragraph boundaries.

Normalization performs the following actions:
- Converts mixed line endings and strips duplicated boilerplate.
- Preserves heading ancestry such as `Architecture > Query Layer > Reranking`.
- Marks code fences, warning blocks, and tables as special regions.
- Extracts references to services, APIs, queues, storage systems, and incident IDs.
- Creates a deterministic `content_hash` so unchanged sections are not re-embedded.

The ingestion system is intentionally idempotent. If the same document version is processed twice, Atlas reuses the stored chunk records instead of generating duplicate vectors. This property matters during webhook replay and recovery after worker outages.

## 5. Chunking Strategy
Atlas does not use a fixed-size splitter by default. The chunker follows structural boundaries first and token limits second. A section remains intact if its size stays below the target ceiling. If a section exceeds the ceiling, it is divided by paragraph, then by sentence group, while preserving the parent heading path in metadata.

The chunking policy uses these defaults:
- Preferred chunk size: 220 to 420 tokens.
- Soft overlap: 40 to 60 tokens.
- Hard stop at code block boundaries unless a block exceeds the token limit.
- Metadata preserved per chunk: title path, document version, tags, source URL, product area, and last review date.

This policy was introduced after an internal benchmark showed that rigid character chunking created retrieval noise in architecture docs, especially when "trade-offs" and "failure modes" were separated from the section they described. In the benchmark, heading-aware chunking improved top-3 retrieval precision by 18 percentage points on multi-clause technical questions.

## 6. Hybrid Retrieval Model
Atlas combines lexical retrieval with semantic retrieval. Lexical search is strong for explicit identifiers such as `KafkaTopicRouter`, `ERR_CONN_POOL_EXHAUSTED`, or incident IDs like `INC-4421`. Semantic search is stronger for natural language formulations such as "why writes get slower during replica failover" or "what protects against stale cache reads after deployment."

The query planner computes three initial signals:
- Lexical relevance score.
- Semantic similarity score.
- Metadata affinity score based on filters like product area and document recency.

Candidates from both lexical and semantic paths are merged into a single pool. A reranker then evaluates the candidates using heading importance, section type, freshness, and evidence density. Evidence density refers to whether the chunk contains concrete mechanisms, thresholds, caveats, or causal statements rather than generic overview prose.

## 7. Query Execution Flow
When a user submits a question, the Query Coordinator performs the following sequence:
1. Normalize the query by lowercasing, trimming whitespace, and extracting possible identifiers.
2. Detect intent such as architecture explanation, operational troubleshooting, incident recap, or configuration lookup.
3. Apply access scope filters based on user identity and team membership.
4. Retrieve lexical and semantic candidates.
5. Rerank the merged pool.
6. Compose an answer from the top evidence chunks.
7. Return citations, confidence indicators, and suggested follow-up questions.

Atlas aims for sub-900 millisecond median retrieval time on mid-sized corpora under normal load. The answer synthesis step is allowed a slightly higher latency budget when streaming is enabled, but the first evidence chunk should be available quickly to reassure the user that the system is grounded.

## 8. Query Planner Details
The query planner has a lightweight intent classifier. It uses a rules-first approach before invoking heavier models. Questions containing verbs like "compare", "trade off", or "difference" are likely routed to comparison prompts. Questions containing "why", "cause", or "happens when" favor chunks with causal language. Questions containing "steps", "runbook", or "recover" boost operational procedure sections.

The planner also performs entity extraction. For example:
- "QCP" expands to "Query Coordinator Plane" when the acronym dictionary supports that mapping.
- "reindex storm" maps to the indexing incident class.
- "blue green" and "canary" both raise deployment-strategy features.

If entity extraction produces high-confidence service names, the retrieval system boosts chunks tagged with those services. This improves precision on documents that repeat generic terms like "gateway", "worker", or "pipeline".

## 9. Reranking Heuristics
Reranking is critical because the first-pass retrievers over-return broad overview sections. Atlas uses a weighted reranker with interpretable features:

- Heading match score.
- Query term proximity.
- Presence of causal phrases such as "because", "results in", and "falls back to".
- Presence of hard numbers such as latency thresholds or memory limits.
- Section type bonus for runbooks, ADRs, and incident retrospectives when the question implies troubleshooting.
- Freshness bonus for time-sensitive operational policies.

Chunks receive a `support_strength` label of `high`, `medium`, or `low`. High-support chunks typically contain mechanisms and constraints together, for example: "During replica failover, write acknowledgements are temporarily gated behind quorum reelection, which increases median commit latency by 25 to 40 percent for approximately 90 seconds."

## 10. Answer Composition Policy
Atlas does not attempt to write free-form answers from memory. The composer is instructed to synthesize only from retrieved evidence. Every answer contains:
- A direct answer in plain technical language.
- A short explanation of the mechanism.
- A "why this matters" line if the query is operational or architectural.
- Source snippets or citations to the underlying sections.

If evidence is weak or contradictory, the answer must say so explicitly. The system prefers a cautious answer with visible uncertainty over a confident but unsupported summary.

## 11. Performance Engineering
Performance work focused on three hot paths: chunk lookup, reranking, and repeated-query reuse. Atlas introduced a two-level cache:

- Query fingerprint cache for normalized questions with short time-to-live.
- Evidence cache for popular chunks used across many related questions.

Cache invalidation is tied to document version changes. When a source document is updated, all cached answers referencing the previous version are marked stale. This prevents subtle errors where an answer remains fast but wrong after a runbook edit.

In benchmarking on a 42,000-section corpus:
- Median retrieval latency improved from 780 ms to 470 ms after hybrid retrieval optimization.
- P95 response latency fell from 2.1 s to 1.3 s after evidence caching and reranker pruning.
- Top-5 evidence relevance improved by 23 percent after section-type-aware reranking.

The platform documentation often cites a "40 percent latency reduction" claim. That figure refers specifically to the retrieval phase after chunking and reranking optimizations were introduced in release `AKF-2.3`.

## 12. Failure Modes and Recovery
Atlas is designed to degrade gracefully. Known failure scenarios include:

### 12.1 Vector Index Degradation
If the vector index becomes unavailable, Atlas falls back to lexical retrieval only. Recall drops on conceptual questions, but identifier-based lookups still work. The UI surfaces a reduced-confidence banner in this mode.

### 12.2 Registry Lag
If document metadata replication lags, recently updated docs may appear stale. To reduce risk, the Query Coordinator refuses to mix new vector records with old metadata snapshots beyond a five-minute skew threshold.

### 12.3 Cache Poisoning
If a cache entry is computed from incomplete evidence during a partial outage, later users could receive a misleading answer. Atlas tags cache entries with retrieval mode and evidence completeness. Answers derived during degraded retrieval are never promoted into the long-lived cache tier.

### 12.4 Ingestion Storms
Large-scale repository migrations can produce tens of thousands of `document.changed` events in a short period. Atlas protects the system with backpressure queues, per-tenant quotas, and a deferred embedding lane. During storms, ingestion freshness may slow, but query serving remains protected.

## 13. Security and Governance
Atlas supports role-based access control and document-level authorization. Sensitive operational runbooks can be indexed without being globally visible. The ingestion service attaches security labels at source time, and retrieval filters them before ranking.

The platform also stores audit records for:
- User question text.
- Retrieved source IDs.
- Answer confidence level.
- Model version or retrieval policy version.
- Whether the result was served from cache.

Auditability is especially important for regulated environments where teams must explain why a user saw a specific recommendation.

## 14. Observability Model
Key metrics include:
- `atlas_query_latency_ms`
- `atlas_retrieval_candidate_count`
- `atlas_rerank_duration_ms`
- `atlas_cache_hit_ratio`
- `atlas_grounded_answer_rate`
- `atlas_doc_freshness_lag_seconds`

On-call engineers monitor dashboards split by tenant, query intent, and retrieval mode. A drop in grounded answer rate often signals a chunking regression or a metadata mismatch rather than a language model problem.

The recommended alert thresholds are:
- P95 query latency above 2500 ms for 10 minutes.
- Cache hit ratio below 0.20 for 30 minutes on mature tenants.
- Grounded answer rate below 0.85 after a retriever deploy.
- Freshness lag above 1800 seconds for high-priority sources.

## 15. Case Study: Replica Failover Incident
In incident `INC-4421`, users reported that write-heavy dashboards became sluggish during a regional failover test. Investigation showed that the replication control service enforced conservative quorum reelection before acknowledging writes. During the 90-second reelection window, median commit latency rose by 25 to 40 percent and the tail latency doubled for bursty traffic.

A weak search system returned generic "database scaling" documents, which slowed diagnosis. Atlas retrieved the precise incident review and the ADR describing quorum behavior because both contained causal language, timing details, and the phrase "write acknowledgement gating". This case became the canonical benchmark for causal technical questions.

## 16. Case Study: Reindex Storm After Documentation Migration
During a migration from wiki exports to repository-backed Markdown, the ingestion plane received approximately 180,000 section updates in under two hours. Backpressure controls kept query latency stable, but document freshness lag increased to 47 minutes for low-priority teams. The postmortem recommended dynamic tenant quotas and a deferred embedding lane for bulk migrations. Those controls were added in release `AKF-2.5`.

## 17. Architecture Decision Record Summary
ADR-014 established that Atlas would use hybrid retrieval rather than vector-only retrieval. The main reasons were:
- Engineers ask many identifier-heavy questions.
- Incident reviews contain exact error strings that semantic embeddings may blur.
- Operational trust increases when exact evidence can be surfaced immediately.

ADR-019 later formalized heading-aware chunking after experiments showed that trade-off sections and warning blocks were frequently separated under fixed-size chunking. This ADR is often cited when explaining why Atlas preserves document structure so aggressively.

## 18. Project Presentation Notes
When presenting Atlas as a personal project, the strongest narrative is:
- Start with the user pain: technical docs are dense and keyword search misses intent.
- Explain the design choice: chunk by meaning and structure, then combine lexical plus semantic retrieval.
- Show the product value: lower latency, better evidence quality, and clearer answer grounding.
- End with operational maturity: degraded modes, security filters, and measurable benchmarks.

The project feels strongest when the demo highlights not only the answer, but also the retrieved evidence, confidence level, and system behavior under failure scenarios.

## 19. Sample Questions the System Should Answer Well
- Why did retrieval latency improve by about 40 percent in release AKF-2.3?
- What happens when the vector index is unavailable?
- Why were write-heavy dashboards slower during the replica failover test?
- How does Atlas handle ingestion storms during large document migrations?
- Why is heading-aware chunking better than fixed-size chunking for architecture docs?
- What metrics should on-call engineers watch after a retriever deployment?

## 20. Closing Notes
Atlas Knowledge Fabric is intended as a demonstration of retrieval quality, grounded answer composition, and engineering communication. The system is strongest when it clearly connects user questions to specific evidence and makes trade-offs visible rather than hidden.
