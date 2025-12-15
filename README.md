# TBAC GenAI Router (Django)

A small, testable demonstration of a Task-Based Access Control (TBAC) GenAI router implemented in Django.
This repo shows a simple router that maps user prompts to tasks using either persisted embeddings or fast substring matching. The router is intentionally small and pluggable so matching strategies can be swapped without changing orchestration or enforcement logic.

Highlights
- Clear separation of concerns: router orchestration, matcher implementation, data layer, and tool manager.
- Fast multi-pattern substring matching using Aho–Corasick (in `app/services/matcher.py`).
- Asynchronous recording of routing results to avoid blocking requests (ThreadPoolExecutor).
- Compatibility fallback to a simple substring scan when a matcher is unavailable.

Repository layout (important files)
- `app/core/data.py` — data access, canonical reference prompts, approvals persistence.
- `app/services/router.py` — routing orchestration, caching, scoring, and async recording.
- `app/services/matcher.py` — pluggable matcher implementations (Aho–Corasick provided).
- `app/services/agent.py` — builds ToolCall(s) from a prompt+task.
- `app/services/tool_manager.py` — authoritative execution with P.E.P.2 enforcement.
- `scripts/build_embeddings.py` — optional script to build and persist semantic embeddings.
- `demo_cli.py` — simple CLI to exercise routing and agent flows.
- `app/docs/architecture.md` — high-level architecture diagram (Mermaid).
- `tests/` — pytest suite covering routing and flows.

Quick concepts
- Router API (public):

    from app.services.router import route_prompt

    result = route_prompt("show me the sales report for last quarter")
    # result == {"task": "report.sales", "score": 0.12, "error": None}  # example

- Matching strategy: the router loads canonical reference prompts (from REFERENCE_PROMPTS + `data/prompt_labels.csv`) and builds an Aho–Corasick automaton for fast substring detection. It returns the longest matched pattern and computes a simple length-based score: score = len(matched_pattern) / len(prompt). The match is accepted only if score >= threshold (default 0.55).

Running the project (dev)
- Install dependencies (use your virtualenv):

    pip install -r requirements.txt

- Run tests:

    pytest -q

- Run demo CLI:

    python3 demo_cli.py

Embedding build (optional, for semantic routing)
- To build persisted embeddings (optional):

    pip install "sentence-transformers" numpy
    python3 scripts/build_embeddings.py

- If embeddings and an ANN index are added later, router will prefer semantic matching; otherwise it uses substring matching.

Architecture & diagram
- See `app/docs/architecture.md` for a Mermaid diagram that shows the router, matcher, data layer, and recorder. Open with VS Code Markdown preview (Mermaid enabled) or paste into a Mermaid live editor.

Operational notes & next steps
- Hot-reload: Currently the router caches reference items and matcher in-process. To pick up updates to `data/prompt_labels.csv` you can restart the process. If you need live reload, add a small reload API that calls the router's init/rebuild logic.
- Recorder: Recording is asynchronous (ThreadPoolExecutor). For production consider a durable queue or a larger/bounded worker pool and graceful shutdown.
- Matching strategies: `app/services/matcher.py` is intentionally isolated — to try a new approach (embedding-based ANN, regex, ML model) implement a compatible matcher class and return it from `build_matcher_from_items`.
- Threshold and scoring: The default threshold (0.55) is conservative for the simple length-based score. Tune it or replace scoring with semantic similarity when embeddings are used.

Contributing
- Add tests for new matcher behavior in `tests/`.
- If you add an external dependency (e.g., faiss, sentence-transformers), update `requirements.txt` and document usage in this README.

Contact / support
- If you need a reload endpoint, help adding a durable recorder, or a semantic matcher + ANN integration, I can implement the next piece.
