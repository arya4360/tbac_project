from typing import Optional, List
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from app.core.data import get_reference_items, record_routing_result
from app.services.matcher import build_matcher_from_items

logger = logging.getLogger(__name__)

# Background recorder executor to avoid blocking the request path when logging
_RECORDER_EXECUTOR = ThreadPoolExecutor(max_workers=4)

def _submit_record(prompt, success, task, source='router'):
    """Submit recording of routing results to a background thread; exceptions are logged."""
    def _safe():
        try:
            record_routing_result(prompt, success=success, task=task, source=source)
        except Exception:
            logger.exception('Failed to record routing result')
    try:
        _RECORDER_EXECUTOR.submit(_safe)
    except Exception:
        logger.exception('Failed to submit routing record task')

# Minimal router:
# - Uses cached reference items (from REFERENCE_PROMPTS + prompt_labels.csv)
# - Substring matching only (no runtime embeddings or model usage)

DEFAULT_THRESHOLD = 0.55


class Router:
    def __init__(self):
        self.reference_items = None       # list of {'task','text'}
        self._init_done = False
        self._init_lock = threading.Lock()

        # matcher instance (kept small to allow swapping implementations later)
        self.matcher = None
        self._pattern_to_task = {}

    def _init_items(self):
        """Load reference items under lock and build matcher."""
        with self._init_lock:
            # if we've already loaded items and built matcher, nothing to do
            if self._init_done and self.reference_items is not None and self.matcher is not None:
                return
            logger.debug('Router: initializing reference items')
            items = get_reference_items()
            self.reference_items = items
            # build matcher from items (Aho-Corasick implementation lives in app.services.matcher)
            try:
                self.matcher = build_matcher_from_items(items)
                self._pattern_to_task = getattr(self.matcher, 'pattern_to_task', {}) or {}
            except Exception:
                logger.exception('Failed to build matcher; falling back to simple substring loop')
                self.matcher = None
                self._pattern_to_task = {}

            self._init_done = True
            logger.debug('Router: initialized %d reference items', len(items))

    def route_prompt(self, prompt: str, threshold: float = DEFAULT_THRESHOLD):
        """Return {'task', 'score', 'error'} using the configured matcher.
        Scoring: score = len(matched_pattern) / len(prompt); accepted if score >= threshold.
        """
        self._init_items()

        items = self.reference_items if self.reference_items is not None else get_reference_items()
        # cache if needed
        if self.reference_items is None:
            self.reference_items = items

        lprompt = (prompt or '').lower()

        # Prefer matcher if available; otherwise fall back to simple substring scan
        best_pat = None
        if self.matcher is not None:
            try:
                best_pat = self.matcher.find_best_match(lprompt)
            except Exception:
                logger.exception('Matcher failed; falling back to simple substring scan')
                best_pat = None

        if best_pat is None:
            # backward-compatible simple substring fallback
            for it in items:
                text = (it.get('text') or '').strip().lower()
                if not text:
                    continue
                if text in lprompt:
                    best_pat = text
                    break

        if best_pat:
            score = len(best_pat) / max(len(lprompt), 1)
            logger.debug('Router: best_pat=%r score=%s threshold=%s', best_pat, score, threshold)
            if score >= threshold:
                task = self._pattern_to_task.get(best_pat)
                _submit_record(prompt, True, task, source='router')
                return {'task': task, 'score': score, 'error': None}
            else:
                _submit_record(prompt, False, None, source='router')
                return {'task': None, 'score': score, 'error': 'no match (below threshold)'}

        _submit_record(prompt, False, None, source='router')
        return {'task': None, 'score': None, 'error': 'no match'}


# Singleton and simple init helper
_GLOBAL_ROUTER = Router()


def init_router(preload: bool = True, background: bool = True):
    if not preload:
        _GLOBAL_ROUTER._init_done = True
        return
    if _GLOBAL_ROUTER._init_done:
        return
    if background:
        t = threading.Thread(target=_GLOBAL_ROUTER._init_items, daemon=True)
        t.start()
    else:
        _GLOBAL_ROUTER._init_items()


# Compatibility flags (kept for tests)
_EMB_AVAILABLE = None
_INIT_DONE = False


def route_prompt(prompt: str) -> dict:
    # honor test-time flags (kept for compatibility with tests)
    forced_threshold = None
    if _EMB_AVAILABLE is False:
        # when tests disable embeddings, simply mark init done so router uses substring fallback
        _GLOBAL_ROUTER._init_done = True
        forced_threshold = 0.0
    if _INIT_DONE is True:
        _GLOBAL_ROUTER._init_done = True

    if not _GLOBAL_ROUTER._init_done:
        init_router(preload=True, background=True)
    try:
        if forced_threshold is not None:
            return _GLOBAL_ROUTER.route_prompt(prompt, threshold=forced_threshold)
        return _GLOBAL_ROUTER.route_prompt(prompt)
    except Exception:
        try:
            _submit_record(prompt, False, None, source='router')
        except Exception:
            logger.exception('Failed to record routing failure')
        return {'task': None, 'score': None, 'error': 'this feature is not available'}

