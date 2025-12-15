# Router architecture (high level)

Below is a concise architecture diagram for the current implementation. The router stays small and orchestrates:
- data layer: `get_reference_items`, `record_routing_result`
- matcher module: `app.services.matcher` (Aho–Corasick)
- async recorder (ThreadPoolExecutor)

```mermaid
flowchart LR
  subgraph Clients
    C[Client / API caller]
  end

  subgraph RouterService[Router (app.services.router)]
    Router[Router]
    Init[_init_items]
    Matcher[Matcher (Aho–Corasick) in app.services.matcher]
    Fallback[Substring fallback]
    Recorder[Recorder (ThreadPoolExecutor)]
  end

  subgraph DataLayer[Data Layer]
    Reference[get_reference_items()
    record[record_routing_result()]
  end

  C -->|route_prompt(prompt)| Router
  Router -->|init_router -> _init_items| Init
  Init --> Reference
  Init -->|build_matcher_from_items(items)| Matcher

  Router -->|lowercase prompt| Matcher
  Router -->|if matcher unavailable| Fallback
  Matcher -->|matched_pattern| Router
  Router -->|_submit_record(...) (async)| Recorder
  Recorder -->|writes| record

  %% Optional future components
  subgraph Future
    Embeddings[Embeddings + ANN]
  end
  Router ---|can be swapped for| Embeddings
```

Legend
- Solid arrows: synchronous calls/return paths
- Dashed/notes: optional or future components

Notes
- Matching uses Aho–Corasick for fast multi-pattern substring search; router falls back to a simple substring loop if matcher fails.
- Recording is asynchronous via ThreadPoolExecutor to avoid blocking request latency.
- `threshold` scoring is length-based: score = len(matched_pattern)/len(prompt) and compared to configured threshold.

How to view
- In VS Code install "Markdown Preview Enhanced" or use an online Mermaid live editor to render the diagram.
