# Track 4 — Shopping Copilot: AI Conversational Search and Recommendations

_TikTok TechJam 2026 · Source: https://bytedance.larkoffice.com/wiki/DNtSwxgeciCS2nkiUefc5qqtnkf_

> Technical Workshop Webinar with Q&A was held on 28 Aug, 4:00 to 4:45pm.
> Webinar Recording: #4 Shopping Copilot: AI Conversational Search and Recommendations.mp4

## 4.1 Background

Traditional e-commerce search engines heavily rely on static keyword matching, failing to capture the fluid shifts of genuine consumer psychology and the distinction between open-ended browsing and high-intent buying. In modern conversational commerce, constructing an intelligent agent that leverages dynamic context programming is critical to bridging the gap between ambiguous user queries and complex product catalogs. Solving this challenge directly impacts core industrial metrics.

## 4.2 Problem Statement

Participants are challenged to architect an intelligent, next-generation shopping agent capable of navigating real-world customer dynamics. Moving beyond rigid search filters, the engineered system must demonstrate deep cognitive understanding, runtime architectural agility, and commercial efficiency using the provided Amazon dataset.

Specifically, the system should be built upon the following four core pillars:

**I. Core Architecture: Intent Routing & Hybrid Pipeline**

- Dual-Track Routing: Instantly detect the user's underlying intent—triggering a high-precision filter track for targeted "Buying" to lock hard constraints, and a diverse dense retrieval track for open-ended "Browsing" to unlock cross-category scenario matching.
- Pipeline Base: Construct an in-memory data stream featuring "Multi-Route Retrieval $\rightarrow$ LLM Semantic Ranking" (combining keyword, category, and vector similarity).

**II. Dialog Strategy: Multi-Turn Scenario Evolution**

- Dynamic State Machine: Build a robust conversational state tracker to gracefully handle dynamic Information Accumulation (incremental slots) and abrupt Intent Override (slot erasure and rewriting).
- Proactive Guidance: Trigger an immediate retrieval cutoff when facing Over-Generality (candidate pool overload) to actively generate structured, proactive clarification prompts that guide user convergence.

**III. Self-Evolution: Dynamic Context Programming**

- Runtime Adaptation: Leverage accumulated dialog history to perform Personalized Context Distillation, continuously updating short-term session states and long-term user profiles.
- Adaptive Orchestration: Utilize dynamic Context Programming to achieve runtime workflow re-orchestration and strategy alignment, ensuring the agent iteratively refines its own guidance logic.

**IV. Evaluation Matrix: Product & Efficiency Metrics**

Anchored on the final purchased record within the Amazon dataset, performance is quantified across three dimensions:

- Coverage (Hit Rate@K): Measures the catalog recall and boundary capability during the retrieval stage.
- Precision (MRR / Top-K Hit Rate): Evaluates the LLM's accuracy in pushing the exact purchased item to the absolute top of the recommendation list.
- Efficiency (MTTC - Mean Turns to Conversion): Heavy rewards systems that guide the user to the correct product in fewer interaction rounds, penalizing unnecessary conversational cognitive load.

## 4.3 Constraints & Scope

**In scope**

- Designing highly sensitive intent-detection modules to split traffic into "Buying" and "Browsing" tracks.
- Implementing heterogeneous retrieval routing (weights, custom dynamic truncation, and slot decay over time).
- Engineering runtime-adaptive memory layers for personalized context distillation.
- Fine-tuning prompt strategies or local scoring logic for the LLM ranking stage to compress decision paths.

**Out of scope**

- UI/UX Development (evaluated purely via automated backend APIs and headless pipelines).
- Training or full-parameter fine-tuning of base foundational LLMs.
- Deploying heavy external industrial vector DB clusters (must run entirely in-memory for light execution).
- Multi-Modal Processing (restricted strictly to text catalogs, structured metadata, and text dialogs).

**Limits**

- Max Turns: Hard limit of 10 turns per session (forced termination and zero score if exceeded).
- Catalog Mutation: The Amazon product dataset is strictly read-only; no structural mutations or mock ASIN injections are allowed.

**Allowed assumptions**

- Inputs are pre-cleaned text strings (no need to account for spelling correction, typos, or ASR noise).
- Product catalog, pricing, and category trees are static for the duration of the hackathon.
- Each session is simulated as an isolated single-user interaction (no multi-user concurrency stress needed).

## 4.4 Available Resources & Data

Participants receive a frozen and reproducible competition kit derived from the Amazon Reviews 2023 dataset.

**Competition Data**

- A frozen catalog containing 50,000 products from the Amazon Reviews 2023 Clothing_Shoes_and_Jewelry category.
- 200 labeled public development sessions for local testing and iteration.
- 800 additional sessions retained privately by the organizer for final evaluation.
- Public and private evaluation sessions use separate users and target products.

**Participant Resources**

- A weak BM25 starter Agent implemented in Python.
- A deterministic local evaluator for Hit Rate@10, MRR, MTTC, Efficiency, and the combined TechnicalScore.
- A published Python Agent interface and machine-readable API contract.
- Evaluation configuration, reproducible baseline results, data documentation, and submission rules.
- A SHA256 checksum file for verifying the downloaded catalog.

Participants can modify or replace the starter Agent while continuing to use the official local evaluator. The participant kit supports keyword retrieval, rule-based methods, dense retrieval, hybrid retrieval, reranking, local models, and external model APIs.

The organizer does not provide hosted model access, API keys, model tokens, or third-party API credits. A paid LLM is not required to complete the challenge. Teams that choose to use external services are responsible for their own credentials, usage limits, and costs, and must not publish secrets in their repositories.

**Resources**

- Participant repository: https://github.com/TechJam2026/techjam-conversational-search
- Participant Kit Release: https://github.com/TechJam2026/techjam-conversational-search/releases/tag/participant-kit
- Original data source and documentation: https://amazon-reviews-2023.github.io/

The competition catalog and evaluation sessions are prepared and frozen by the organizer. Participants do not need to download or reconstruct the full upstream Amazon Reviews 2023 dataset.

## 4.5 Deliverables

1. **Written Project Description (via Devpost)**
   - Provide a clear written description of your project that includes:
     - How your solution addresses the problem statement
     - Development tools used (e.g. VSCode, Colab, Jupyter)
     - APIs used (e.g. OpenAI GPT-4o, Google Maps API)
     - Libraries and frameworks used (e.g. Hugging Face Transformers, PyTorch, scikit-learn, pandas)
     - Datasets and assets used (e.g. Google Local Reviews dataset, manually labelled data)
2. **Public Code/GitHub Repository**
   - Submit a link to a public Code/GitHub repository containing:
     - Well-structured, commented code covering all components of your solution
     - A README file that includes:
       - Project overview
       - Setup and installation instructions
       - Steps to reproduce your results
       - A brief reflection on your solution's limitations and what you would improve given more time
       - Team member contributions (if applicable, i.e. team participants, non-solo participants)
3. **Demo Video**
   - Submit a short video that:
     - Demonstrates your solution working end-to-end (e.g. inference results, dashboard, model predictions)
     - Is uploaded to YouTube and set to public visibility
     - Is linked in your Devpost description
     - Does not include third-party trademarks or copyrighted content without permission
   - Note for backend/NLP tracks: If a front-end interface is not applicable to your solution, a walkthrough video showing API usage, inference examples, or result analysis is accepted.

## 4.6 Judging Criteria

| Judging Criteria | Definition | Weight |
|------------------|------------|--------|
| Technical Execution | The solution demonstrates strong engineering fundamentals, such as well-structured code, thoughtful architecture, and effective use of APIs or models. The demo runs reliably, and the technical complexity reflects deliberate, capable decision-making. | 35% |
| Innovation & Problem Insight | The project demonstrates originality in both idea and approach. It stands out for the sharpness of its problem understanding — how clearly the team has framed the challenge, why it matters, and how directly the solution addresses it. | 20% |
| Impact & Relevance | The project has clear potential to deliver value to real users or stakeholders — with meaningful reach, tangible benefit, and relevance that goes beyond solving for the hackathon prompt alone. | 20% |
| Feasibility & Practicality | The solution is realistic and buildable beyond a prototype. The approach is technically and operationally sustainable — resource usage is proportionate, the architecture holds under real-world conditions, and the implementation is grounded rather than speculative. | 15% |
| Presentation & Communication | [Final Event Only]: The team communicates their work with clarity. The pitch tells a coherent story; from problem to solution to potential, and the team is able to respond to questions with depth, demonstrating genuine understanding of their own project. | 10% |
