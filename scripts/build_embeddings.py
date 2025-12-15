"""Build embeddings for reference prompts using sentence-transformers if available.

Outputs:
 - app/data/reference_embeddings.npy
 - app/data/reference_strings.json

Falls back to no-op if sentence-transformers not installed.
"""
import json
from pathlib import Path

try:
    from app.core.data import get_reference_items, REF_EMB_FILE, REF_STR_FILE, REFERENCE_PROMPTS
except Exception:
    # fall back to local paths if module import not available
    from pathlib import Path as _P
    REF_EMB_FILE = _P(__file__).resolve().parent.parent / 'data' / 'reference_embeddings.npy'
    REF_STR_FILE = _P(__file__).resolve().parent.parent / 'data' / 'reference_strings.json'

    # Try to add project root to sys.path and import app.core.data so we reuse canonical refs
    try:
        import sys
        proj_root = _P(__file__).resolve().parent.parent
        if str(proj_root) not in sys.path:
            sys.path.insert(0, str(proj_root))
        from app.core import data as _core_data
        # reuse functions/paths from app.core.data
        get_reference_items = _core_data.get_reference_items
        REF_EMB_FILE = getattr(_core_data, 'REF_EMB_FILE', REF_EMB_FILE)
        REF_STR_FILE = getattr(_core_data, 'REF_STR_FILE', REF_STR_FILE)
        REFERENCE_PROMPTS = getattr(_core_data, 'REFERENCE_PROMPTS', None)
    except Exception:
        # If importing the package still fails, use CSV/JSON or a small built-in set as fallback
        def get_reference_items():
            # Attempt to read labeled prompts from project data/prompt_labels.csv
            labels_fp = _P(__file__).resolve().parent.parent / 'data' / 'prompt_labels.csv'
            items = []
            if labels_fp.exists():
                try:
                    import csv
                    with open(labels_fp, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            if row.get('prompt') and row.get('task'):
                                items.append({'task': row.get('task'), 'text': row.get('prompt')})
                except Exception:
                    items = []

            # Next, try to read previously-saved canonical references from reference_strings.json
            try:
                ref_json_fp = _P(__file__).resolve().parent.parent / 'data' / 'reference_strings.json'
                if ref_json_fp.exists():
                    with open(ref_json_fp, 'r', encoding='utf-8') as f:
                        loaded = json.load(f)
                        if isinstance(loaded, list):
                            for it in loaded:
                                t = it.get('text') if isinstance(it, dict) else None
                                task = it.get('task') if isinstance(it, dict) else None
                                if t and task:
                                    items.append({'task': task, 'text': t})
            except Exception:
                pass

            # If no reference JSON and no CSV, fall back to REFERENCE_PROMPTS from app.core.data if present
            if not any(items):
                # if 'REFERENCE_PROMPTS' in globals() and REFERENCE_PROMPTS:
                rp = REFERENCE_PROMPTS
                for task, refs in rp.items():
                    for r in refs:
                        items.append({'task': task, 'text': r})

            return items

try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
except Exception:
    # If sentence-transformers isn't installed, provide a deterministic fallback
    print('sentence-transformers not installed; using deterministic fallback embeddings')
    SentenceTransformer = None
    import numpy as np
    import hashlib


def _fake_embeddings(texts, dim=384, dtype=np.float32):
    """Deterministic fallback embedding generator.

    For each text we seed a PRNG with the first 8 bytes of the sha256 hash of the
    text so the output is stable across runs and machines.
    """
    out = np.zeros((len(texts), dim), dtype=dtype)
    for i, t in enumerate(texts):
        h = hashlib.sha256((t or '').encode('utf-8')).digest()
        seed = int.from_bytes(h[:8], 'big') & 0xFFFFFFFF
        rng = np.random.RandomState(seed)
        vec = rng.normal(size=(dim,)).astype(dtype)
        # normalize
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        out[i] = vec
    return out


def main():
    items = get_reference_items()
    texts = [it['text'] for it in items]
    # prefer real model when available
    if SentenceTransformer is not None:
        model = SentenceTransformer('all-MiniLM-L6-v2')
        embs = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
    else:
        embs = _fake_embeddings(texts, dim=384)

    REF_EMB_FILE.parent.mkdir(parents=True, exist_ok=True)
    np.save(REF_EMB_FILE, embs)
    with open(REF_STR_FILE, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2)
    print('Wrote embeddings to', REF_EMB_FILE)


if __name__ == '__main__':
    main()
