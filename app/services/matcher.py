"""Aho-Corasick matcher module.

Keeps the automaton and matching logic isolated so the router stays small
and other matching implementations can be swapped in later.
"""
from collections import deque
from typing import List, Optional, Dict, Any

import json
import hashlib
from pathlib import Path

import numpy as np

class AhoCorasickMatcher:
    def __init__(self):
        # nodes: list of {'next':{ch:idx}, 'fail':int, 'outputs':[pattern]}
        self._nodes = [{'next': {}, 'fail': 0, 'outputs': []}]
        self.pattern_to_task: Dict[str, Any] = {}

    def build(self, items: List[dict]):
        """Build the automaton from items. Each item is expected to have 'text' and 'task'."""
        # reset
        self._nodes = [{'next': {}, 'fail': 0, 'outputs': []}]
        self.pattern_to_task = {}

        for it in items:
            pat = (it.get('text') or '').strip().lower()
            if not pat:
                continue
            current = 0
            for ch in pat:
                nxt = self._nodes[current]['next'].get(ch)
                if nxt is None:
                    nxt = len(self._nodes)
                    self._nodes[current]['next'][ch] = nxt
                    self._nodes.append({'next': {}, 'fail': 0, 'outputs': []})
                current = nxt
            self._nodes[current]['outputs'].append(pat)
            if pat not in self.pattern_to_task:
                self.pattern_to_task[pat] = it.get('task')

        # build failure links
        q = deque()
        for ch, node_idx in list(self._nodes[0]['next'].items()):
            self._nodes[node_idx]['fail'] = 0
            q.append(node_idx)

        while q:
            r = q.popleft()
            for ch, s in list(self._nodes[r]['next'].items()):
                q.append(s)
                f = self._nodes[r]['fail']
                while f and ch not in self._nodes[f]['next']:
                    f = self._nodes[f]['fail']
                self._nodes[s]['fail'] = self._nodes[f]['next'].get(ch, 0)
                self._nodes[s]['outputs'] += self._nodes[self._nodes[s]['fail']]['outputs']

    def find_best_match(self, lprompt: str) -> Optional[str]:
        """Return the longest pattern found in lprompt, or None if none found."""
        if not lprompt or not self._nodes:
            return None
        current = 0
        best = None
        for ch in lprompt:
            while current and ch not in self._nodes[current]['next']:
                current = self._nodes[current]['fail']
            current = self._nodes[current]['next'].get(ch, 0)
            outs = self._nodes[current]['outputs']
            if outs:
                for pat in outs:
                    if best is None or len(pat) > len(best):
                        best = pat
        return best


class EmbeddingMatcher:
    """Matcher that uses persisted reference embeddings for semantic matching.

    Expects embeddings saved by `scripts/build_embeddings.py` at the canonical
    `REF_EMB_FILE` and `REF_STR_FILE` locations (see app.core.data). If the
    files aren't available the matcher gracefully degrades (find_best_match
    returns None) and the router will fall back to substring matching.
    """
    def __init__(self):
        self.pattern_to_task: Dict[str, Any] = {}
        self._texts: List[str] = []
        self._emb: Optional[np.ndarray] = None  # shape (n_refs, dim), normalized
        self._model = None

    def _fake_query_embedding(self, text: str, dim: int) -> np.ndarray:
        # deterministic pseudo-embedding using SHA256; not semantically meaningful
        h = hashlib.sha256(text.encode('utf-8')).digest()
        arr = np.frombuffer(h, dtype=np.uint8).astype(np.float32)
        if arr.size < dim:
            # tile to required length
            arr = np.tile(arr, int(np.ceil(dim / arr.size)))[:dim]
        else:
            arr = arr[:dim]
        v = arr - arr.mean()
        nrm = np.linalg.norm(v)
        return (v / max(nrm, 1e-12)).astype(np.float32)

    def build(self, items: List[dict]):
        """Try to load persisted embeddings; fall back to mapping texts->tasks.

        If persisted embeddings are present, load them and the corresponding
        reference strings JSON. Otherwise, keep a mapping of patterns to tasks
        so the matcher can still be queried (but semantic matching won't be
        available).
        """
        # default mapping from provided items
        self.pattern_to_task = {}
        for it in items:
            t = (it.get('text') or '').strip().lower()
            if not t:
                continue
            if t not in self.pattern_to_task:
                self.pattern_to_task[t] = it.get('task')

        # attempt to load persisted embeddings from app.core.data paths
        try:
            from app.core.data import REF_EMB_FILE, REF_STR_FILE
            emb_fp = Path(REF_EMB_FILE)
            str_fp = Path(REF_STR_FILE)
            if emb_fp.exists() and str_fp.exists():
                embs = np.load(str(emb_fp))
                with open(str_fp, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                # Expect loaded to be list of {'task','text'} in same order as embs
                texts = []
                for it in loaded:
                    txt = (it.get('text') or '').strip().lower()
                    texts.append(txt)
                    if txt not in self.pattern_to_task:
                        self.pattern_to_task[txt] = it.get('task')
                self._texts = texts
                arr = np.asarray(embs, dtype=np.float32)
                # normalize rows for cosine via dot-product
                norms = np.linalg.norm(arr, axis=1, keepdims=True)
                norms[norms == 0] = 1.0
                arr = arr / norms
                self._emb = arr
                return
        except Exception:
            # any error here just means embeddings aren't available at runtime
            self._emb = None
            return

    def _ensure_model(self, dim: int):
        # lazily attempt to load sentence-transformers model
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
            # prefer compact model; loading might be slow but only once
            self._model = SentenceTransformer('all-MiniLM-L6-v2')
        except Exception:
            self._model = None

    def find_best_match(self, lprompt: str) -> Optional[str]:
        """Return the text of the best matched reference (by cosine similarity)
        or None if embeddings or model are not available.
        """
        if not lprompt or self._emb is None or self._emb.size == 0:
            return None
        # compute query embedding
        dim = int(self._emb.shape[1])
        self._ensure_model(dim)
        if self._model is not None:
            try:
                q = self._model.encode([lprompt], convert_to_numpy=True, normalize_embeddings=True)
                q = q.reshape(-1).astype(np.float32)
            except Exception:
                q = self._fake_query_embedding(lprompt, dim)
        else:
            q = self._fake_query_embedding(lprompt, dim)

        # compute cosine similarities via dot product (rows already normalized)
        scores = self._emb.dot(q)
        idx = int(np.argmax(scores))
        if np.isfinite(scores[idx]):
            return self._texts[idx]
        return None


def build_matcher_from_items(items: List[dict], use_embeddings: bool = True):
    """Factory that returns either an embedding-based matcher (if requested)
    or the default Aho-Corasick matcher.
    """
    if use_embeddings:
        em = EmbeddingMatcher()
        em.build(items)
        # if embeddings weren't loaded, em._emb will be None; caller can fall back
        # to substring matcher when find_best_match returns None
        return em

    m = AhoCorasickMatcher()
    m.build(items)
    return m
