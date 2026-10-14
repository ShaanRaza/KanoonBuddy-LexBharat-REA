import{j as e,P as i,M as a}from"./index-Ac-JwDP4.js";import{A as s,G as r,u as n,v as o,w as l,r as c,Z as d,N as u}from"./icons-CYH3BR3F.js";import{L as t}from"./react-vendor-9b-Fppbo.js";import"./modulepreload-polyfill-B5Qt9EMX.js";import"./mermaid-Iu9CgLAS.js";import"./motion-DRT_oqBn.js";const h=`
# V2 Research Pipeline — Architecture

## 1. Architecture Overview

The V2 research pipeline is a **14-state deterministic state machine** that combines HyDE-enhanced vector search, citation graph traversal, statute-anchored retrieval, authority-weighted reranking, and LLM-powered composition with tool calling. LLM calls are used for query planning (HyDE), extraction, and composition — **never for routing decisions**.

The pipeline spans **19 files** organized in 5 layers.

### Layer Map

| Layer | Files | Purpose |
|-------|-------|---------|
| **Orchestration** | \`orchestratorV2.js\`, \`runResearchV2.js\` | 14-state machine + SSE streaming loop |
| **Search** | \`vectorSearchV2.js\`, \`citationGraphDAO.js\` | HyDE dual-embedding search, citation graph walk, statute GIN retrieval |
| **Processing** | \`queryExpander.js\`, \`composerV2.js\`, \`citationRanker.js\`, \`sufficiencyScorer.js\`, \`authorityGate.js\`, \`legalLookupService.js\` | Query expansion, ranking, scoring, tool-enabled composition |
| **Data / Registry** | \`canonicalTopicRegistry.js\`, \`topicAccessors.js\`, \`topics/index.js\`, \`legalCodeAliases.js\`, \`statuteIntentRegistry.js\` | 130 topics, statute mappings, 70+ intent rules |
| **Verification** | \`verification/index.js\`, \`verification/citationGate.js\`, \`claimVerifier.js\` | Citation gate, doctrine guard, hallucination detection, claim verification |

### File Dependency Graph

\`\`\`mermaid
graph TD
    RUN["runResearchV2.js<br/><i>Entry Point + SSE</i>"] --> ORCH["orchestratorV2.js<br/><i>14-State Machine</i>"]
    RUN --> COMP["composerV2.js<br/><i>Tool-enabled</i>"]
    RUN --> VERIFY["verification/index.js"]
    RUN --> CV["claimVerifier.js<br/><i>Claim verification</i>"]

    ORCH --> QE["queryExpander.js<br/><i>Synonyms + BNS mapping</i>"]
    ORCH --> VSEARCH["vectorSearchV2.js<br/><i>HyDE + Kanoon + RRF</i>"]
    ORCH --> CGDAO["citationGraphDAO.js<br/><i>Graph walk + statute GIN</i>"]
    ORCH --> RANK["citationRanker.js<br/><i>Authority + validity rerank</i>"]
    ORCH --> AUTH_GATE["authorityGate.js<br/><i>SC/HC/Tribunal filter</i>"]
    ORCH --> SUFF["sufficiencyScorer.js<br/><i>Tier 1 + Tier 2 heuristic</i>"]
    ORCH --> TA["topicAccessors.js"]
    ORCH --> SIR["statuteIntentRegistry.js<br/><i>70+ rules</i>"]

    VSEARCH --> QPMULTI["queryPlannerMulti<br/><i>Kanoon keyword queries</i>"]
    VSEARCH --> HYDE["generateHypotheticalHolding<br/><i>HyDE SC holding</i>"]
    VSEARCH --> EMBED["embeddingService<br/><i>Voyage law-2</i>"]
    VSEARCH --> FUSION["fusionService<br/><i>RRF 60/40</i>"]
    VSEARCH --> KANOON["kanoonAdapter<br/><i>Indian Kanoon API</i>"]

    CGDAO --> DB_CE["citation_edges table<br/><i>Treatment semantics</i>"]
    CGDAO --> DB_JSONB["judgments.cite_list<br/><i>JSONB from Kanoon</i>"]
    CGDAO --> DB_GIN["judgments.statutes[]<br/><i>GIN index</i>"]

    COMP --> LOOKUP["legalLookupService.js<br/><i>9 tool types</i>"]

    RANK --> VALID["validityEnrichment.js"]

    VERIFY --> CGATE["citationGate.js"]
    VERIFY --> DGUARD["doctrineGuard.js"]

    TA --> CTR["canonicalTopicRegistry.js<br/><i>130 topics</i>"]
    QE --> LCA["legalCodeAliases.js<br/><i>400+ mappings</i>"]

    style RUN fill:#fef3c7,stroke:#d97706
    style ORCH fill:#fef3c7,stroke:#d97706
    style VSEARCH fill:#dbeafe,stroke:#2563eb
    style CGDAO fill:#dbeafe,stroke:#2563eb
    style COMP fill:#dbeafe,stroke:#2563eb
    style RANK fill:#dbeafe,stroke:#2563eb
    style SUFF fill:#dbeafe,stroke:#2563eb
    style AUTH_GATE fill:#dbeafe,stroke:#2563eb
    style QE fill:#dbeafe,stroke:#2563eb
    style LOOKUP fill:#dbeafe,stroke:#2563eb
    style CV fill:#dbeafe,stroke:#2563eb
    style QPMULTI fill:#e0e7ff,stroke:#4f46e5
    style HYDE fill:#e0e7ff,stroke:#4f46e5
    style EMBED fill:#e0e7ff,stroke:#4f46e5
    style FUSION fill:#e0e7ff,stroke:#4f46e5
    style KANOON fill:#e0e7ff,stroke:#4f46e5
    style DB_CE fill:#e0e7ff,stroke:#4f46e5
    style DB_JSONB fill:#e0e7ff,stroke:#4f46e5
    style DB_GIN fill:#e0e7ff,stroke:#4f46e5
    style CTR fill:#dcfce7,stroke:#16a34a
    style TA fill:#dcfce7,stroke:#16a34a
    style LCA fill:#dcfce7,stroke:#16a34a
    style SIR fill:#dcfce7,stroke:#16a34a
    style VERIFY fill:#fce7f3,stroke:#db2777
    style CGATE fill:#fce7f3,stroke:#db2777
    style DGUARD fill:#fce7f3,stroke:#db2777
    style VALID fill:#fce7f3,stroke:#db2777
\`\`\`

**Legend:** Yellow = Orchestration, Blue = Processing, Indigo = External/DB Modules, Green = Data/Registry, Pink = Verification/Safety

---

## 2. Main Research Flow (14-State Machine)

The orchestrator runs a deterministic state machine. The primary (fast) path completes in 9 states. If Tier 1 sufficiency recommends enhancement, 4 additional states run (Kanoon enhance + re-extract + re-compose).

\`\`\`mermaid
graph TD
    INIT["INIT"] --> QE["QUERY_EXPAND<br/><i>Synonym + statute section expansion</i>"]
    QE --> SR["STATUTE_RESOLVE<br/><i>4-stage statute lookup</i>"]
    SR --> CD["CASE_DISCOVERY<br/><i>HyDE + pgvector + Kanoon + force-include</i>"]
    CD --> GE["GRAPH_EXPAND<br/><i>Citation graph walk + statute GIN</i>"]
    GE --> CR["CITATION_RERANK<br/><i>Authority + validity scoring</i>"]
    CR --> AC["AUTHORITY_CHECK<br/><i>SC/HC/Tribunal gate</i>"]
    AC --> T1["TIER1_SUFFICIENCY<br/><i>Heuristic (no LLM)</i>"]

    T1 --> DC["DRAFT_COMPOSE<br/><i>Extract + compose + verify</i>"]

    DC -->|"sufficient"| DONE["DONE<br/><i>Confidence scoring</i>"]
    DC -->|"insufficient"| KE["KANOON_ENHANCE<br/><i>Indian Kanoon deep search</i>"]

    KE --> EX["EXTRACT<br/><i>Batch ratio decidendi extraction</i>"]
    EX --> T2["TIER2_SUFFICIENCY<br/><i>Post-extract heuristic</i>"]
    T2 --> FC["FINAL_COMPOSE<br/><i>Enhanced composition + verify</i>"]
    FC --> DONE

    style INIT fill:#f3f4f6,stroke:#6b7280
    style QE fill:#dbeafe,stroke:#2563eb
    style SR fill:#dbeafe,stroke:#2563eb
    style CD fill:#dbeafe,stroke:#2563eb
    style GE fill:#dbeafe,stroke:#2563eb
    style CR fill:#fef3c7,stroke:#d97706
    style AC fill:#fef3c7,stroke:#d97706
    style T1 fill:#fef3c7,stroke:#d97706
    style DC fill:#dcfce7,stroke:#16a34a
    style KE fill:#e0e7ff,stroke:#4f46e5
    style EX fill:#e0e7ff,stroke:#4f46e5
    style T2 fill:#e0e7ff,stroke:#4f46e5
    style FC fill:#e0e7ff,stroke:#4f46e5
    style DONE fill:#d1fae5,stroke:#059669
\`\`\`

### SSE Phase Mapping

| State | SSE Phase | Thinking Message |
|-------|-----------|-----------------|
| QUERY_EXPAND | \`vector\` | "Identifying **key legal concepts**..." |
| STATUTE_RESOLVE | \`vector\` | "Resolving **statute sections**..." |
| CASE_DISCOVERY | \`vector\` | "Searching **Supreme Court judgments**..." |
| GRAPH_EXPAND | \`vector\` | "Expanding via **citation graph & statutes**..." |
| CITATION_RERANK | \`vector\` | "Ranking by **authority & citations**..." |
| AUTHORITY_CHECK | \`vector\` | "Filtering **authoritative sources**..." |
| TIER1_SUFFICIENCY | \`vector\` | "Checking **source sufficiency**..." |
| DRAFT_COMPOSE | \`compose\` | "Composing **legal analysis**..." |
| KANOON_ENHANCE | \`enhance\` | "Enhancing from **Indian Kanoon**..." |
| EXTRACT | \`enhance\` | "Extracting **ratio decidendi**..." |
| TIER2_SUFFICIENCY | \`enhance\` | "Verifying **completeness**..." |
| FINAL_COMPOSE | \`final\` | "Finalizing **research memo**..." |

### Phase Progression

\`\`\`
init → vector → compose → [enhance → final] → done
\`\`\`

The \`enhance → final\` segment only runs when TIER1_SUFFICIENCY recommends Kanoon enhancement (insufficient coverage, freshness required, or missing SC authority).

---

## 3. QUERY_EXPAND — Deterministic Query Enrichment

The QUERY_EXPAND state (\`queryExpander.js\`) enriches the user's query **before** vector search to improve recall. Entirely deterministic — no LLM call.

### Expansion Types

| Type | What It Does | Example |
|------|-------------|---------|
| **Synonym injection** | Adds legal synonyms | "bail" → "bail OR anticipatory bail OR default bail" |
| **Statute section mapping** | IPC ↔ BNS, CrPC ↔ BNSS, IEA ↔ BSA | "Section 302 IPC" → adds "Section 103 BNS" |
| **Landmark anchoring** | Injects known landmark case names | "anticipatory bail" → adds "Sibbia" |
| **BNS context injection** | Adds description for new code sections | "BNS 101" → adds "murder, culpable homicide" context |

### BNS/IPC Bidirectional Mapping

400+ section mappings from \`legalCodeAliases.js\`:
- IPC → BNS (forward): \`{ '302': { section: '103', desc: 'Murder' } }\`
- BNS → IPC (reverse): auto-generated
- CrPC ↔ BNSS, IEA ↔ BSA: same pattern

**Output:** \`context.expandedQuery\` (enriched query string) + \`context.queryExpansions\` (list of applied expansions)

---

## 4. STATUTE_RESOLVE — 4-Stage Statute Lookup

Resolves statute references in the user's question to authoritative text from the statute database. Runs 4 stages in sequence, each progressively broader.

\`\`\`mermaid
graph LR
    S0["Stage 0<br/><b>Bare Code Detection</b><br/><i>'What is BNS?'</i>"] --> S1["Stage 1<br/><b>Explicit Refs</b><br/><i>getBNSSectionContext()</i>"]
    S1 --> S1B["Stage 1b<br/><b>Fallback Refs</b><br/><i>extractSectionReferences()</i>"]
    S1B --> S2["Stage 2<br/><b>Auto-pair Equivalents</b><br/><i>IPC 302 -> BNS 103</i>"]
    S2 --> S3["Stage 3<br/><b>Semantic Resolve</b><br/><i>Only if no refs found</i>"]

    style S0 fill:#fef3c7,stroke:#d97706
    style S1 fill:#dbeafe,stroke:#2563eb
    style S1B fill:#dbeafe,stroke:#2563eb
    style S2 fill:#dcfce7,stroke:#16a34a
    style S3 fill:#dcfce7,stroke:#16a34a
\`\`\`

| Stage | Trigger | Function | Example |
|-------|---------|----------|---------|
| **0: Bare code** | Query is just a code name | Regex: \`/^(bns|bnss|bsa|ipc|crpc|iea)$/i\` | "What is BNS?" → overview with top 5 key sections |
| **1: Explicit refs** | Section number found in query | \`getBNSSectionContext()\` | "Section 302 IPC" → full section text |
| **1b: Fallback refs** | Stage 1 missed some patterns | \`extractSectionReferences()\` | "S.438 CrPC" → parsed as CrPC:438 |
| **2: Auto-pair** | Stage 1/1b found a ref with a known equivalent | \`statuteService.lookupSection()\` | IPC 302 found → auto-adds BNS 103 |
| **3: Semantic** | No refs from stages 0-2 | \`statuteSemanticResolver.resolve()\` | "dowry death punishment" → IPC 304B |

### Confidence Thresholds

| Confidence | Range | Behavior |
|-----------|-------|----------|
| **Auto-inject** | >= 0.75 | Injected as "Relevant statute text" |
| **Maybe-inject** | 0.55 - 0.75 | Injected as "Likely relevant statute section" |
| **Skip** | < 0.55 | Not injected |

**Cap:** Maximum 3 sections per query, sorted by confidence.

**Output:** \`context.statuteContext\` — array of \`{act_code, section_number, section_text, equivalent_code, confidence, reason}\` objects. Consumed by GRAPH_EXPAND (for statute-anchored retrieval) and composerV2 (for authoritative statute text in prompts).

---

## 5. CASE_DISCOVERY — HyDE-Enhanced Multi-Channel Search

CASE_DISCOVERY (\`vectorSearchV2.js\`) is the primary search state. It runs 3 search channels in parallel, then enriches with force-include landmarks.

\`\`\`mermaid
graph TD
    START["CASE_DISCOVERY"] --> PLAN["Step 1: queryPlannerMulti<br/><i>Generate Kanoon keyword queries</i>"]
    PLAN --> PAR["Parallel Execution"]

    PAR --> HYDE["Channel A: HyDE Search<br/><i>LLM generates hypothetical SC holding<br/>→ dual-embedding → RRF fusion</i>"]
    PAR --> KAN["Channel B: Indian Kanoon<br/><i>Up to 3 sequential keyword queries<br/>500ms delay between (rate limit)</i>"]

    HYDE --> MERGE["Merge & Dedup"]
    KAN --> MERGE

    MERGE --> FORCE["Force-Include Landmarks<br/><i>canonicalTopicRegistry force_include<br/>e.g. anticipatory bail → Sibbia</i>"]
    FORCE --> FALLBACK{"Weak results?<br/><i>< 3 hits</i>"}
    FALLBACK -->|"Yes"| LANDMARK["Landmark Fallback<br/><i>Top 10 SC cases by landmark_score</i>"]
    FALLBACK -->|"No"| OUT["context.vectorHits"]
    LANDMARK --> OUT

    style START fill:#f3f4f6,stroke:#6b7280
    style PLAN fill:#fef3c7,stroke:#d97706
    style PAR fill:#dbeafe,stroke:#2563eb
    style HYDE fill:#dbeafe,stroke:#2563eb
    style KAN fill:#dbeafe,stroke:#2563eb
    style MERGE fill:#fef3c7,stroke:#d97706
    style FORCE fill:#dcfce7,stroke:#16a34a
    style LANDMARK fill:#dcfce7,stroke:#16a34a
    style OUT fill:#d1fae5,stroke:#059669
\`\`\`

### HyDE (Hypothetical Document Embeddings) Pipeline

HyDE bridges the query-document semantic gap. User queries are short questions; corpus documents are long judgment texts. HyDE generates a hypothetical SC holding whose embedding is closer to the actual judgment embeddings.

\`\`\`
1. LLM generates hypothetical SC holding (GPT-4.1-mini, ~200 tokens)
2. Two embeddings generated in parallel (Voyage law-2, 1024 dims):
   - Query embedding: from expandedQuery
   - HyDE embedding: from hypothetical holding
3. Two vector searches in parallel (pgvector, topK=38 each):
   - Query search: finds cases semantically close to the question
   - HyDE search: finds cases semantically close to a plausible holding
4. RRF fusion: query 60% + HyDE 40% → top 25 merged results
\`\`\`

If HyDE generation fails (LLM error/timeout), falls back to single \`hybridSearch(expandedQuery, topK=25)\`.

### Kanoon Channel

\`queryPlannerMulti()\` generates up to 3 keyword queries with types (\`broad\`, \`statute\`, \`landmark\`). Queries run sequentially with 500ms delay (Kanoon API rate limit, returns 403 on concurrent). Each returns max 6 results.

Kanoon results are deduped against vector results by \`docId\`. New hits are appended with \`kanoonQueryType\` tag. High-value results are queued for auto-indexing into the corpus via \`kanoonIndexer\`.

### Force-Include Injection

After search completes, \`getForceIncludeDocIds(question)\` checks the canonical topic registry for must-have landmark cases that may have been missed by embedding similarity.

Example: Query about "anticipatory bail" → force-includes Gurbaksh Singh Sibbia (docId 1308768) if not already in results. These are injected with \`score: 0.95\` and \`finalScore: 1.0+\` to guarantee they survive reranking.

---

## 6. GRAPH_EXPAND — Citation Graph Walk + Statute-Anchored Retrieval

GRAPH_EXPAND (\`citationGraphDAO.js\`) discovers cases that semantic search misses — cases connected through citation relationships or shared statute references, not semantic similarity.

\`\`\`mermaid
graph TD
    START["GRAPH_EXPAND"] --> SEEDS["Top 5 vector hits as seeds"]
    START --> REFS["Statute refs from STATUTE_RESOLVE"]

    SEEDS --> PAR["Parallel Execution"]
    REFS --> PAR

    PAR --> WALK["walkGraph(seeds)<br/><i>BFS depth=1, JSONB primary<br/>citation_edges enrichment</i>"]
    PAR --> STATUTE["findCasesByStatute(refs)<br/><i>GIN index on judgments.statutes[]<br/>Alias-aware ILIKE patterns</i>"]

    WALK --> MERGE["discoverRelated()<br/><i>Dedup by docId<br/>Merge provenance<br/>Multi-source hits ranked first</i>"]
    STATUTE --> MERGE

    MERGE --> FILTER["Filter: exclude existing vectorHits"]
    FILTER --> OUT["Append to context.vectorHits<br/><i>Up to 15 new cases</i>"]

    style START fill:#f3f4f6,stroke:#6b7280
    style SEEDS fill:#fef3c7,stroke:#d97706
    style REFS fill:#fef3c7,stroke:#d97706
    style PAR fill:#dbeafe,stroke:#2563eb
    style WALK fill:#dbeafe,stroke:#2563eb
    style STATUTE fill:#dbeafe,stroke:#2563eb
    style MERGE fill:#fef3c7,stroke:#d97706
    style FILTER fill:#fef3c7,stroke:#d97706
    style OUT fill:#d1fae5,stroke:#059669
\`\`\`

### Graph Walk (\`walkGraph\`)

Uses a BFS traversal with two data sources running in parallel per hop:

| Source | Coverage | Data |
|--------|----------|------|
| **JSONB cite_list/cited_by_list** (primary) | 98%+ of corpus | From Kanoon API, capped at 50 entries per case. Join key: \`(elem->>'tid')::text\` |
| **citation_edges table** (enrichment) | 20% of corpus | Treatment semantics: followed, distinguished, overruled. Polarity + severity + confidence |

Each discovered case carries provenance: \`{ minHop, via: [seedDocId], edgePolarities: {positive, neutral, negative} }\`

### Statute-Anchored Retrieval (\`findCasesByStatute\`)

Queries the GIN index on \`judgments.statutes[]\`. Handles the mismatch between query abbreviations and corpus full names:

\`\`\`
Input: {code: 'CrPC', section: '438'}
Aliases: ['CrPC', 'Cr.P.C', 'Criminal Procedure', 'Code of Criminal Procedure']
DB format: "Section 438 of the Code of Criminal Procedure Code, 1973"

Generated patterns (per alias):
  %Section 438 of%CrPC%
  %Section 438 in%CrPC%
  %Section 438(%CrPC%
  %CrPC%Section 438 %
  %CrPC%section 438(%
  ... (same for each alias)
\`\`\`

Patterns use word-boundary-safe matching to prevent false positives (Section 32 matching Section 320).

### Non-Fatal Design

GRAPH_EXPAND is wrapped in try/catch. If it fails (DB timeout, connection error), the pipeline continues to CITATION_RERANK with only the vector search results. No research is blocked.

---

## 7. CITATION_RERANK — Authority + Validity Scoring

Re-ranks all hits (vector + graph + statute) using a composite score that balances semantic similarity against legal authority.

\`\`\`mermaid
graph LR
    SEM["Semantic Score<br/><b>50%</b><br/><i>Vector similarity</i>"] --> FINAL["Final Score"]
    AUTH["Authority Score<br/><b>50%</b><br/><i>Court + citations + landmark</i>"] --> FINAL
    VAL["Validity Multiplier<br/><i>Overruled = 0.3x</i>"] --> FINAL

    FINAL["finalScore =<br/>(semantic x 0.5 + authority x 0.5)<br/>x validity"]

    style SEM fill:#dbeafe,stroke:#2563eb
    style AUTH fill:#fef3c7,stroke:#d97706
    style VAL fill:#fce7f3,stroke:#db2777
    style FINAL fill:#d1fae5,stroke:#059669
\`\`\`

### Authority Score Breakdown

| Component | Weight | Source |
|-----------|--------|--------|
| Court level | 40% | SC=2.0, HC=1.0, Tribunal=0.5, District=0.3 |
| Citation boost (sigmoid) | 40% | \`1 / (1 + exp(-0.8 x (log10(citations) - 2)))\` |
| Landmark score | 20% | Normalized to 0-1 (max 200) |

### Sigmoid Citation Curve

| Citations | log10 | Boost |
|-----------|-------|-------|
| 10 | 1.0 | ~0.31 |
| 100 | 2.0 | ~0.50 |
| 1,000 | 3.0 | ~0.69 |
| 10,000 | 4.0 | ~0.83 |

> **Key insight:** Pure semantic similarity ranked Sibbia (8,067 citations) at #62. With authority weighting, it ranks #1.

### Validity Multiplier

| Status | Multiplier | Trigger |
|--------|-----------|---------|
| Good law / unknown | 1.0 | Default — unknown validity is NOT penalized |
| Overruled | 0.3 | \`validity.isOverruled === true\` OR \`validity.score === 0\` |
| Weak | 0.7 | Multiple negative treatments in citation_edges |

### Kanoon Semantic Floor

Kanoon results have no embedding similarity (keyword-only). Without a floor, they would always rank last. The floor scales with authority:

| Court Level | Citations | Pseudo-Semantic Score |
|-------------|-----------|----------------------|
| SC | >= 5000 | 0.55 |
| SC | >= 1000 | 0.45 |
| SC | >= 100 | 0.35 |
| SC | < 100 | 0.25 |
| HC | >= 500 | 0.30 |
| Others | any | 0.15 |

### Force-Include Preservation

Cases injected as \`force_include\` (from canonicalTopicRegistry) are NOT re-scored. Their original \`finalScore: 1.0+\` is preserved to guarantee they stay at the top of results.

---

## 8. AUTHORITY_CHECK — SC/HC/Tribunal Gate

Filters hits into "streamable" (shown to user immediately) and "held back" (kept for internal use but not displayed).

| Court Level | Rule | Rationale |
|-------------|------|-----------|
| **Supreme Court** | Always pass | Binding precedent |
| **Constitution/Full Bench** | Always pass | Multi-judge authority |
| **High Court** | landmarkScore >= 70 | Only widely-cited HC cases |
| **Tribunal** | Hold back | Not streamed to user |
| **District Court** | Hold back | Not streamed to user |

Held-back cases are **not discarded** — they remain in \`context.heldBackHits\` for composition context.

### Minimum Authority Check

After filtering, checks if there's sufficient authority to anchor the response:
- **Pass:** >= 1 SC case, OR >= 2 landmark HC cases (score >= 90)
- **Fail:** Response will still be composed, but flagged as low-authority

---

## 9. TIER1_SUFFICIENCY — Heuristic Sufficiency (No LLM)

Tier 1 sufficiency is a pure heuristic — no LLM call. It decides whether the draft answer needs Kanoon enhancement.

### Fast Path Criteria

All must be true for the fast path:
- \`hits.length >= 3\` (minimum total hits)
- \`scHits.length >= 1\` if topic requires SC authority
- \`landmarks.length >= 2\` (cases with landmarkScore >= 70)
- \`highRelevance.length >= 2\` (cases with similarity >= 0.5)

### Kanoon Enhancement Triggers

| Trigger | Reason |
|---------|--------|
| Not fast enough | Fails one of the 4 criteria above |
| SC required but missing | Topic like "fundamental rights" or "bail" needs SC |
| Freshness required | BNS/BNSS/BSA topics — corpus may be stale |

### Topic-Specific Requirements

**SC Required Topics:** constitution, fundamental rights, article 21, article 14, article 19, bail, anticipatory bail, habeas corpus, writ, death penalty, reservation, basic structure

**Freshness Topics:** BNS, BNSS, BSA, 2023/2024 amendment, data protection, DPDP

---

## 10. DRAFT_COMPOSE — Extract + Compose + Verify

The draft composition runs inside \`runResearchV2.js\` (not the orchestrator). It combines extraction, composition, and verification in a single flow.

### Step 1: Smart Extraction

\`\`\`mermaid
graph TD
    HITS["Top 12 streamable hits"] --> CHECK{"Has good summary?<br/><i>summary > 100 chars<br/>OR holdings[] > 0</i>"}
    CHECK -->|"Yes"| PREINDEX["Pre-indexed Extract<br/><i>Direct conversion, NO LLM</i>"]
    CHECK -->|"No"| LLM["LLM Batch Extraction<br/><i>extractCasesBatch()<br/>1 call for up to 8 cases</i>"]
    PREINDEX --> MERGE["Combined Extracts"]
    LLM --> MERGE

    style HITS fill:#f3f4f6,stroke:#6b7280
    style PREINDEX fill:#d1fae5,stroke:#059669
    style LLM fill:#dbeafe,stroke:#2563eb
    style MERGE fill:#d1fae5,stroke:#059669
\`\`\`

Pre-indexed cases (with good summaries/holdings from the corpus pipeline) skip LLM extraction entirely. This dramatically reduces latency for well-indexed cases.

### Step 2: Composition with Tool Calling

The composer (\`composerV2.js\`) generates the legal analysis. In non-draft mode, it has access to 9 tool types via \`legalLookupService.js\`:

| Tool | Purpose | Example |
|------|---------|---------|
| \`statute\` | Look up statute section text | \`{ act: "IPC", section: "302" }\` |
| \`case_section\` | Find cases citing a section | \`{ section: "302", act: "IPC" }\` |
| \`definition\` | Legal term from statutes | \`{ term: "culpable homicide" }\` |
| \`precedent\` | Leading cases on a topic | \`{ topic: "anticipatory bail" }\` |
| \`section_search\` | Search sections by keyword | \`{ keyword: "murder" }\` |
| \`compare_codes\` | Old vs new code comparison | \`{ oldCode: "IPC", newCode: "BNS", section: "302" }\` |
| \`punishment\` | Punishment for an offense | \`{ offense: "murder" }\` |
| \`case_status\` | Check if case is overruled | \`{ docId: "12345" }\` |
| \`find_related\` | Citation graph neighbors | \`{ docId: "12345" }\` |

Max 4 tool calls per composition. Each result capped at 3000 characters.

### Step 3: Verification Pipeline

Post-composition verification runs in 4 stages with **fail-open** design.

\`\`\`mermaid
graph TD
    INPUT["Composed Response<br/><i>answer + cases</i>"] --> S1["Stage 1: Query Classification<br/><i>extractLegalIssueVector()</i>"]

    S1 --> SHOULD{"Should verify?"}
    SHOULD -->|"Low confidence<br/>+ not strict mode"| SKIP["Skip verification<br/>Return original"]
    SHOULD -->|"Yes"| S2["Stage 2: Citation Gate<br/><i>applyCitationGate()</i>"]

    S2 --> S25["Stage 2.5: Hallucination Detection<br/><i>DocId grounding check</i>"]

    S25 --> S3["Stage 3: Doctrine Guard<br/><i>applyDoctrineGuard()</i>"]

    S3 --> S4["Stage 4: Response Assembly"]

    S4 --> OUTPUT["Verified Response"]

    ERR["Error at any stage"] -.->|"Fail-open"| FALLBACK["Return original response"]

    style INPUT fill:#f3f4f6,stroke:#6b7280
    style OUTPUT fill:#d1fae5,stroke:#059669
    style SKIP fill:#fef3c7,stroke:#d97706
    style FALLBACK fill:#fee2e2,stroke:#dc2626
    style ERR fill:#fee2e2,stroke:#dc2626
\`\`\`

### Citation Gate Scoring

| Component | Weight | Source |
|-----------|--------|--------|
| Domain match | 15% | Criminal / Civil / Constitutional |
| Statute match | 30% | Does cited statute match query statute? |
| Topic match | 30% | Fuzzy matching via Fuse.js |
| Legal test match | 25% | Does the legal test align? |

---

## 11. Enhancement Path (KANOON_ENHANCE → EXTRACT → TIER2 → FINAL_COMPOSE)

When TIER1_SUFFICIENCY recommends enhancement, these 4 additional states run:

### KANOON_ENHANCE

Uses \`queryPlanner()\` to generate a targeted Kanoon search query based on gaps identified by sufficiency. Fetches up to 10 results. New hits queued for auto-indexing.

### EXTRACT

Fetches full judgment text from Kanoon API (parallel HTTP, not LLM). Then batch-extracts ratio decidendi using LLM (1 call for up to 5 cases). Merges with existing extracts.

### TIER2_SUFFICIENCY

Post-extract heuristic check:
- **Sufficient:** >= 2 extracts with meaningful holdings AND (>= 1 SC if SC required)
- **Insufficient:** Flags but proceeds to composition anyway

### FINAL_COMPOSE

Same composition pipeline as DRAFT_COMPOSE but with the enriched extract set. Uses tool calling. Followed by the same verification pipeline.

---

## 12. Magic Numbers Registry

### orchestratorV2.js

| Constant | Value | Purpose |
|----------|-------|---------|
| Max iterations | 20 | Safety limit for state machine loop |
| Top seeds for GRAPH_EXPAND | 5 | Vector hits used as citation graph seeds |
| Graph expand limit | 15 | Max new cases from graph + statute |
| Max statute context | 3 | Cap on injected statute sections |
| Bare code key terms | 5 | "murder, theft, bail, cheating, rape" |

### vectorSearchV2.js

| Constant | Value | Purpose |
|----------|-------|---------|
| HyDE over-fetch multiplier | 1.5x | topK * 1.5 for RRF fusion input |
| RRF query weight | 0.60 | Weight for query embedding results |
| RRF HyDE weight | 0.40 | Weight for HyDE embedding results |
| Final topK | 25 | Max merged results after RRF |
| Max Kanoon queries | 3 | Keyword queries from queryPlannerMulti |
| Max Kanoon results/query | 6 | Results per Kanoon query |
| Kanoon delay | 500ms | Rate limit delay between queries |
| Landmark fallback threshold | < 3 | Trigger if fewer than 3 hits |
| Landmark fallback minScore | 100 | Minimum landmark_score for fallback cases |

### citationGraphDAO.js

| Constant | Value | Purpose |
|----------|-------|---------|
| Default walk depth | 1 | BFS hops from seeds |
| Default walk limit | 30 | Max cases per walk |
| Statute search limit | 15 | Max cases from GIN index |
| Statute aliases | 28 acts | IPC, BNS, CrPC, BNSS, CPC, Evidence Act, etc. |
| Court rank | SC=3, HC=2, TRIBUNAL=1, DISTRICT=0 | Consistent across all functions |

### citationRanker.js

| Constant | Value | Purpose |
|----------|-------|---------|
| Semantic weight | 0.50 | Weight of vector similarity |
| Authority weight | 0.50 | Weight of authority score |
| Court weight factor | 0.40 | % of authority from court level |
| Citation factor | 0.40 | % of authority from citations |
| Landmark factor | 0.20 | % of authority from landmark score |
| Sigmoid slope | 0.80 | Steepness of citation curve |
| Sigmoid midpoint | 2.0 | Center (log10(100) = 2) |
| Max landmark score | 200 | Normalization ceiling |
| Overruled penalty | 0.30 | Multiplier for confirmed overruled |
| Weak penalty | 0.70 | Multiplier for weak cases |
| Kanoon semantic floor | 0.15 | Base minimum for Kanoon results |

### runResearchV2.js

| Constant | Value | Purpose |
|----------|-------|---------|
| Max iterations | 20 | Loop safety limit |
| Top hits for extraction | 12 | Cases sent to extraction |
| casesOnly max | 15 | Max cases returned in casesOnly mode |
| Good summary threshold | 100 chars | Min length to skip LLM extraction |
| Max extraction batch | 8 | Cases sent to LLM extractor |
| Rerank timeout | 3000ms | Timeout for validity enrichment |

### composerV2.js

| Constant | Value | Purpose |
|----------|-------|---------|
| Max tokens | 2500 | Token limit for composition |
| Temperature | 0.3 | LLM temperature |
| Max tool calls | 4 | Legal lookup calls per composition |
| Tool types | 9 | statute, case_section, definition, precedent, section_search, compare_codes, punishment, case_status, find_related |

### sufficiencyScorer.js

| Constant | Value | Purpose |
|----------|-------|---------|
| Min hits for fast | 3 | Minimum total hits |
| Min landmarks | 2 | Minimum landmark cases (score >= 70) |
| Min high-relevance | 2 | Minimum hits with similarity >= 0.5 |
| Min SC (if required) | 1 | At least 1 SC for SC-required topics |

---

## 13. SSE Event Reference

All events include \`apiVersion: "2.0"\` and \`timestamp\`.

| Event | Phase | Payload |
|-------|-------|---------|
| \`start\` | init | \`{ question, phase: "init" }\` |
| \`phase\` | varies | \`{ phase, state }\` — sent on phase transitions |
| \`thinking\` | varies | \`{ content, state }\` — markdown thinking messages |
| \`progress\` | varies | \`{ agent, message }\` — sub-agent progress |
| \`partial_results\` | compose | \`{ cases[], heldBackCount, tentative }\` |
| \`content\` | compose | \`{ text }\` — streaming answer chunks |
| \`draft_answer\` | compose | \`{ answer, cases[], confidence, draft, _verification }\` |
| \`final_answer\` | final | \`{ answer, cases[], confidence, draft: false }\` |
| \`complete\` | done | \`{ duration, casesOnly }\` |
| \`error\` | error | \`{ message, state, recoverable }\` |

---

## 14. External Service Dependencies

| Service | Used By | Timeout | Fallback |
|---------|---------|---------|----------|
| **OpenAI GPT-4.1-mini** | composerV2, extractor, HyDE generation | Model default | Deterministic fallback |
| **Voyage law-2** | embeddingService (query + HyDE embeddings) | Model default | No vector search |
| **Indian Kanoon API** | kanoonAdapter (keyword search + doc fetch) | 5000ms | Skip, proceed with vector results |
| **PostgreSQL (pgvector)** | Vector search, statute GIN, citation_edges, JSONB cite_list | Connection pool | Error state |
| **Anthropic Claude** | Optional via provider flag | Model default | Falls back to OpenAI |

### Parallel Isolation

Each external call is independently try/caught:
- GRAPH_EXPAND failure = fail-open, pipeline continues without graph results
- HyDE LLM failure = falls back to single hybridSearch (no dual-embedding)
- Kanoon failure = skipped, no retry
- Validity enrichment timeout (3000ms) = neutral validity (no penalty)
- Citation graph walk failure = silently returns empty set
- Statute GIN failure = returns empty, graph walk results stand alone
- Extraction failure for one case = doesn't fail the batch
- Verification failure at any stage = fail-open, returns unverified response

---

## 15. Error Handling Patterns

| Pattern | Where | Behavior |
|---------|-------|----------|
| **Fail-open** | GRAPH_EXPAND, verification, citation graph | Errors return safe defaults |
| **Graceful degradation** | HyDE, Kanoon, validity | Falls back to simpler search |
| **Max iterations** | State machine loop (20) | Forces ERROR state |
| **Client disconnect** | \`isConnected()\` check per state | Graceful stop |
| **Extraction isolation** | Per-case extraction | Individual failures don't block batch |
| **Timeout caps** | Validity (3s), lookup (5s) | Falls back to neutral/skip |
| **Pre-indexed optimization** | Extraction | Cases with good summaries skip LLM |
| **Force-include preservation** | Citation reranker | Injected cases bypass re-scoring |

---

## 16. Feature Flags & Toggles

### Verification Config (\`verification/index.js\`)

| Flag | Default | Effect |
|------|---------|--------|
| \`enableCitationGate\` | true | Topic-based citation filtering |
| \`enableDoctrineGuard\` | true | Doctrine violation detection |
| \`enableHallucinationDetection\` | true | DocId grounding check |
| \`strictMode\` | false | Verify even low-confidence queries |
| \`passUnknownCases\` | true | Pass through cases not in index |
| \`checkTreatment\` | true | Check case treatment status |

### Composition Flags

| Flag | Source | Effect |
|------|--------|--------|
| \`LEGAL_LOOKUP_TOOL_ENABLED\` | featureFlags.js | Enable tool calling in composition |
| \`casesOnly\` | runResearchV2 option | Short-circuit after TIER1_SUFFICIENCY — returns cases only, skips composition |
| \`provider\` | options | "openai" or "anthropic" |

### casesOnly Short-Circuit

When \`casesOnly: true\`, the pipeline exits after TIER1_SUFFICIENCY:
\`\`\`
INIT → QUERY_EXPAND → STATUTE_RESOLVE → CASE_DISCOVERY → GRAPH_EXPAND
→ CITATION_RERANK → AUTHORITY_CHECK → TIER1_SUFFICIENCY → [return top 15 cases]
\`\`\`
No extraction, no composition, no verification. Used by the "Case Search" UI mode.

---

## 17. Database Schema Dependencies

### Tables Used

| Table | Used By | Index |
|-------|---------|-------|
| \`judgments\` | All search + retrieval | \`idx_judgments_embedding_ivfflat\` (vector), \`idx_judgments_statutes_gin\` (GIN) |
| \`citation_edges\` | GRAPH_EXPAND, citationGraphDAO | Unique on \`(from_doc_id, to_doc_id, treatment_type)\` |
| \`statute_sections\` | STATUTE_RESOLVE, legalLookupService | Act code + section number |

### Key Judgment Columns

| Column | Type | Used For |
|--------|------|----------|
| \`doc_id\` | VARCHAR(50) | Primary key, Indian Kanoon document ID |
| \`embedding\` | vector(1024) | Voyage law-2 embedding for vector search |
| \`court_level\` | VARCHAR(20) | SC/HC/TRIBUNAL/DISTRICT — authority gate + reranking |
| \`cited_by_count\` | INTEGER | Citation boost in reranker |
| \`landmark_score\` | REAL | Authority + force-include threshold |
| \`bench_strength\` | VARCHAR(30) | CONSTITUTION_BENCH passes authority gate |
| \`topics\` | TEXT[] | Topic matching for force-include |
| \`statutes\` | TEXT[] | GIN-indexed for statute-anchored retrieval |
| \`cite_list\` | JSONB | Array of \`{tid, title}\` — outgoing citation graph |
| \`cited_by_list\` | JSONB | Array of \`{tid, title}\` — incoming citation graph |
| \`summary\` | TEXT | Pre-indexed extraction (skip LLM if > 100 chars) |
| \`holdings\` | JSONB | Pre-indexed holdings (skip LLM if present) |
| \`search_vector\` | tsvector | BM25 full-text search |
| \`validity_score\` | REAL | Good law assessment (NULL = unassessed) |

---

## 18. Testing & Benchmarks

### DAO Test Suite (38 tests)

\`backend/scripts/test-citation-dao.js\` — validates citationGraphDAO against live DB:

| Group | Tests | Validates |
|-------|-------|-----------|
| **A: Statute Anchoring** | 14 | \`findCasesByStatute()\` — CrPC 438, Evidence Act 32, IPC 300, CrPC 167, CrPC 41, IPC 34, IPC 149 |
| **B: Citation Gravity** | 8 | \`walkGraph()\` — BFS from Sibbia, Puttaswamy, Joginder, Pakala, Shreya |
| **C: JSONB Integrity** | 6 | \`getCitedCases()\` / \`getCitingCases()\` — join key, NULL safety, sort order |
| **D: Hybrid Discovery** | 6 | \`discoverRelated()\` — statute + graph union, provenance merge |
| **E: Negative Sanity** | 4 | Cross-topic pollution prevention |

### Benchmark Integration

The benchmark runner (\`runner.js\`) calls \`runResearchV2Sync()\` which exercises the full 14-state pipeline:

\`\`\`
runner.js → runResearchV2Sync() → runResearchV2() → orchestrator loop
  INIT → QUERY_EXPAND → STATUTE_RESOLVE → CASE_DISCOVERY → GRAPH_EXPAND
  → CITATION_RERANK → AUTHORITY_CHECK → TIER1_SUFFICIENCY → DRAFT_COMPOSE → DONE
  [if enhanced: → KANOON_ENHANCE → EXTRACT → TIER2_SUFFICIENCY → FINAL_COMPOSE → DONE]
\`\`\`

650 test cases across 71 categories, evaluated on: case recall, topic coverage, citation quality, principle coverage, guardrail compliance, overruling accuracy.
`,C=()=>e.jsx(i,{children:e.jsxs("div",{className:"min-h-screen bg-gradient-to-b from-gray-50 to-white",children:[e.jsx("div",{className:"bg-white border-b border-gray-200",children:e.jsxs("div",{className:"max-w-6xl mx-auto px-4 py-6",children:[e.jsxs(t,{to:"/admin/blog",className:"inline-flex items-center gap-2 text-gray-600 hover:text-gray-900 mb-4 transition-colors",children:[e.jsx(s,{className:"w-4 h-4"}),e.jsx("span",{children:"Back to Admin"})]}),e.jsxs("div",{className:"flex items-center gap-4",children:[e.jsx("div",{className:"p-3 bg-gradient-to-br from-emerald-100 to-emerald-50 rounded-xl",children:e.jsx(r,{className:"w-8 h-8 text-emerald-700"})}),e.jsxs("div",{children:[e.jsx("h1",{className:"text-2xl font-bold text-gray-900 tracking-tight",children:"V2 Research Pipeline"}),e.jsx("p",{className:"text-gray-600 mt-1",children:"14-state deterministic machine with HyDE search, citation graph, statute GIN, and claim verification"})]})]})]})}),e.jsxs("div",{className:"max-w-6xl mx-auto px-4 py-8",children:[e.jsxs("div",{className:"grid grid-cols-2 md:grid-cols-4 gap-4 mb-8",children:[e.jsxs("div",{className:"bg-white border border-gray-200 rounded-xl p-4 flex items-center gap-3",children:[e.jsx("div",{className:"p-2 bg-amber-100 rounded-lg",children:e.jsx(n,{className:"w-5 h-5 text-amber-700"})}),e.jsxs("div",{children:[e.jsx("div",{className:"text-sm font-medium text-gray-900",children:"19 Files"}),e.jsx("div",{className:"text-xs text-gray-500",children:"5 Layers"})]})]}),e.jsxs("div",{className:"bg-white border border-gray-200 rounded-xl p-4 flex items-center gap-3",children:[e.jsx("div",{className:"p-2 bg-blue-100 rounded-lg",children:e.jsx(o,{className:"w-5 h-5 text-blue-700"})}),e.jsxs("div",{children:[e.jsx("div",{className:"text-sm font-medium text-gray-900",children:"14 States"}),e.jsx("div",{className:"text-xs text-gray-500",children:"Deterministic Machine"})]})]}),e.jsxs("div",{className:"bg-white border border-gray-200 rounded-xl p-4 flex items-center gap-3",children:[e.jsx("div",{className:"p-2 bg-green-100 rounded-lg",children:e.jsx(l,{className:"w-5 h-5 text-green-700"})}),e.jsxs("div",{children:[e.jsx("div",{className:"text-sm font-medium text-gray-900",children:"130 Topics"}),e.jsx("div",{className:"text-xs text-gray-500",children:"Canonical Registry"})]})]}),e.jsxs("div",{className:"bg-white border border-gray-200 rounded-xl p-4 flex items-center gap-3",children:[e.jsx("div",{className:"p-2 bg-purple-100 rounded-lg",children:e.jsx(c,{className:"w-5 h-5 text-purple-700"})}),e.jsxs("div",{children:[e.jsx("div",{className:"text-sm font-medium text-gray-900",children:"38 DAO Tests"}),e.jsx("div",{className:"text-xs text-gray-500",children:"Golden-25 Suite"})]})]})]}),e.jsxs("div",{className:"bg-gradient-to-r from-gray-900 to-gray-800 rounded-2xl p-6 mb-8 text-white",children:[e.jsxs("div",{className:"flex items-center gap-2 mb-4",children:[e.jsx(d,{className:"w-5 h-5 text-emerald-400"}),e.jsx("h2",{className:"text-lg font-semibold",children:"Pipeline at a Glance"})]}),e.jsxs("div",{className:"grid grid-cols-2 md:grid-cols-6 gap-4",children:[e.jsxs("div",{className:"text-center",children:[e.jsx("div",{className:"text-2xl font-bold text-emerald-400",children:"4"}),e.jsx("div",{className:"text-xs text-gray-400",children:"Search Channels"})]}),e.jsxs("div",{className:"text-center",children:[e.jsx("div",{className:"text-2xl font-bold text-amber-400",children:"9"}),e.jsx("div",{className:"text-xs text-gray-400",children:"Composer Tools"})]}),e.jsxs("div",{className:"text-center",children:[e.jsx("div",{className:"text-2xl font-bold text-blue-400",children:"28"}),e.jsx("div",{className:"text-xs text-gray-400",children:"Statute Aliases"})]}),e.jsxs("div",{className:"text-center",children:[e.jsx("div",{className:"text-2xl font-bold text-purple-400",children:"400+"}),e.jsx("div",{className:"text-xs text-gray-400",children:"Code Mappings"})]}),e.jsxs("div",{className:"text-center",children:[e.jsx("div",{className:"text-2xl font-bold text-pink-400",children:"650"}),e.jsx("div",{className:"text-xs text-gray-400",children:"Benchmark Tests"})]}),e.jsxs("div",{className:"text-center",children:[e.jsx("div",{className:"text-2xl font-bold text-cyan-400",children:"Fail-Open"}),e.jsx("div",{className:"text-xs text-gray-400",children:"Safety Design"})]})]})]})]}),e.jsx("div",{className:"max-w-6xl mx-auto px-4 pb-16",children:e.jsx("div",{className:"bg-white border border-gray-200 rounded-2xl shadow-sm overflow-hidden",children:e.jsx("div",{className:"p-8 md:p-12",children:e.jsx(a,{content:h})})})}),e.jsx("div",{className:"border-t border-gray-200 bg-gray-50",children:e.jsx("div",{className:"max-w-6xl mx-auto px-4 py-8",children:e.jsxs("div",{className:"flex items-center justify-between",children:[e.jsxs("div",{className:"flex items-center gap-2 text-gray-600",children:[e.jsx(u,{className:"w-4 h-4"}),e.jsx("span",{className:"text-sm",children:"Last updated: February 2026"})]}),e.jsxs("div",{className:"flex items-center gap-4",children:[e.jsx(t,{to:"/admin/blog",className:"text-sm text-gray-600 hover:text-gray-900 transition-colors",children:"Admin Blog"}),e.jsx(t,{to:"/admin/architecture",className:"text-sm text-gray-600 hover:text-gray-900 transition-colors",children:"System Architecture"})]})]})})})]})});export{C as default};
