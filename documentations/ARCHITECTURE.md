# Shopping Copilot Architecture

The current implementation is deterministic and entirely offline. Startup builds
an in-memory SQLite FTS5 product index, normalized exact-evidence table,
category-membership table, and weak quality features from the 50,000-row catalog.
Each `respond()` call extracts evaluator-supported category, constraint,
correction, and no-preference evidence into isolated session state. Current-turn
and resolved-state BM25 routes are combined with category-scoped exact evidence,
a category fallback, a weak profile fallback, deterministic tie-breaking, and
bounded exploration of previously unseen recommendations. Clarification begins
broadly and moves to typed attributes after a decline. Dense recall, semantic
paraphrase handling, an explicit intent router, information-gain questions, and
LLM reranking are not implemented and remain gated experiments.

## Implementation status — 30 August 2026

| Component | Status | Current behavior |
|---|---|---|
| Offline catalog preparation | Implemented | FTS5 fields, exact evidence, category membership, quality tie-break |
| Session state | Implemented | Category, constraints, declined attributes, question counts, prior recommendations |
| Sparse multi-route retrieval | Implemented | Current message and accumulated-state BM25 routes |
| Exact structured route | Implemented | Normalized evidence matched within the resolved coarse category |
| Rank fusion and reranking | Implemented | Rank-based route scores, exact-hit/intersection boosts, quality and stable-ID ties |
| Boundary and override handling | Implemented | Declined attributes are retired; pre-correction recommendations become eligible again |
| Clarification | Partial | Broad `other` questions followed by a fixed typed sequence; not information gain |
| Intent router and typed hard/soft ops | Planned | Current parser recognizes the official simulator templates only |
| Dense or semantic retrieval | Planned | No embeddings or vector database |
| LLM parsing or reranking | Planned | No model calls, tokens, credentials, network, or API cost |

The diagram below is the target architecture. The table above is the source of
truth for what is implemented today.

```mermaid
flowchart TB
    %% ===== Core pipeline =====
    subgraph CORE["Core Pipeline — always-on, deterministic, in-memory"]
        direction TB

        RESET(["reset(session_id, user_profile)"])
        ENTRY(["respond(session_id, user_message, turn, top_k)"])

        subgraph S1["1. Session State Compiler"]
            PARSE["Parse message into typed evidence"]
            OPS["Apply ops: add / negate / replace / no_preference"]
            SESSION[("Bounded per-session state")]
        end

        subgraph S2["2. Retrieval Strategy"]
            ROUTER{"Inferred intent"}
            BUY["Buying — precision track"]
            BROWSE["Browsing — recall track"]
            OVER["Override — erase then rewrite"]
            BOUND["Boundary — record no-preference"]
        end

        subgraph S3["3. Candidate Generation (lexical + structured)"]
            RCUR["Current-turn fielded BM25"]
            RSTATE["Resolved-state fielded BM25"]
            RSTRUCT["Structured category / attribute route"]
            POOL[("Bounded candidate union")]
        end

        subgraph S4["4. Fusion + Constraint-Aware Rerank"]
            FUSE["Reciprocal Rank Fusion"]
            HARD["Hard-constraint eligibility + penalty"]
            SCORE["Relevance + soft preference + weak profile + quality"]
            TIE["Stable parent_asin tie-break"]
        end

        subgraph S5["5. Clarification Policy"]
            INFO["Expected information gain"]
            ASK["Highest-value attribute or None"]
        end

        subgraph S6["6. Compose & Validate"]
            COMPOSE["Compose natural message"]
            VALID["Contract + ID validation"]
            FALLBACK["Deterministic fallback"]
        end

        RESET -->|"store profile"| SESSION
        ENTRY --> PARSE
        PARSE --> OPS
        OPS --> SESSION
        SESSION -.->|"prior state"| PARSE
        SESSION --> ROUTER
        ROUTER --> BUY
        ROUTER --> BROWSE
        ROUTER --> OVER
        ROUTER --> BOUND
        BUY --> RCUR
        BUY --> RSTATE
        BUY --> RSTRUCT
        BROWSE --> RCUR
        BROWSE --> RSTRUCT
        OVER --> RSTATE
        BOUND --> RSTRUCT
        SESSION -.->|"active constraints"| RSTATE
        RCUR --> POOL
        RSTATE --> POOL
        RSTRUCT --> POOL
        POOL --> FUSE
        FUSE --> HARD
        HARD --> SCORE
        SCORE --> TIE
        SESSION -.->|"weak profile prior"| SCORE
        TIE --> INFO
        INFO --> ASK
        SESSION -.->|"asked / declined slots"| INFO
        TIE --> COMPOSE
        ASK --> COMPOSE
        COMPOSE --> VALID
        VALID -.->|"invalid or exception"| FALLBACK
        FALLBACK --> VALID
        VALID --> OUT(["message, ask_attribute, top-k recommendations, usage"])
    end

    %% ===== Gated extensions =====
    subgraph EXT["Extensions — adopted only on measured gain"]
        RDENSE["Frozen dense recall"]
        LLMR["LLM semantic rerank / parse"]
    end
    RDENSE -.->|"extra candidates (gated)"| POOL
    LLMR -.->|"adjusted scores (gated)"| SCORE

    %% ===== Foundations =====
    subgraph FOUND["Foundations"]
        subgraph CAT["Catalog Preparation — once per Agent"]
            CNORM["Normalize searchable fields"]
            CSPARSE["Fielded sparse indexes"]
            CSTRUCT["Structured attribute maps"]
            CVOCAB["Vocabulary + aliases"]
            CQUAL["Quality features"]
            CIDS["Valid parent_asin set"]
            CNORM --> CSPARSE
            CNORM --> CSTRUCT
            CNORM --> CQUAL
            CNORM --> CIDS
            CSTRUCT --> CVOCAB
        end

        subgraph EVAL["Offline Evaluation — never at runtime"]
            EV["Official evaluator + held-out split"]
            TUNE["Promote weights and thresholds"]
        end
        EV --> TUNE
    end

    CSPARSE -.->|"read-only"| RCUR
    CSPARSE -.->|"read-only"| RSTATE
    CSTRUCT -.->|"read-only"| RSTRUCT
    CVOCAB -.->|"read-only"| PARSE
    CQUAL -.->|"read-only"| SCORE
    CIDS -.->|"read-only"| VALID
    TUNE -.->|"promoted config only"| FUSE
    TUNE -.->|"promoted config only"| INFO
```
