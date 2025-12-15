"""Aho-Corasick matcher module.

Keeps the automaton and matching logic isolated so the router stays small
and other matching implementations can be swapped in later.
"""
from collections import deque
from typing import List, Optional, Dict, Any

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


def build_matcher_from_items(items: List[dict]) -> AhoCorasickMatcher:
    m = AhoCorasickMatcher()
    m.build(items)
    return m
