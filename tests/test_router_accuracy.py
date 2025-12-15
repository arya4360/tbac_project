from app.services import router


def _task_of(res):
    if isinstance(res, dict):
        return res.get('task')
    return res


def test_keyword_routing_simple_cases():
    cases = [
        ("Push a new README file to the main branch.", 'Feature_Development'),
        ("Check deployment logs for the last service incident.", 'Production_Support'),
        ("Run maintenance scripts on the server", 'Infrastructure_Maintenance'),
        ("Generate a list of leads for the EMEA region", 'Lead_Generation'),
    ]
    for prompt, expected in cases:
        got = router.route_prompt(prompt)
        got_task = _task_of(got)
        assert got_task == expected, f"Prompt '{prompt}' routed to {got_task}, expected {expected}"


def test_semantic_fallback_when_unavailable(monkeypatch):
    # simulate embeddings unavailable - patch the imported router module directly
    monkeypatch.setattr(router, '_EMB_AVAILABLE', False)
    monkeypatch.setattr(router, '_INIT_DONE', True)
    res = router.route_prompt('Fix bug in the payment component')
    assert _task_of(res) == 'Feature_Development'
