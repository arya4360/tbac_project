import csv
from app.services import router
from app.core.data import PROMPT_LABELS_CSV


def test_router_on_labeled_dataset():
    # load labeled prompts
    data = []
    with open(PROMPT_LABELS_CSV, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            data.append((row['prompt'], row['task']))

    correct = 0
    for prompt, label in data:
        pred = router.route_prompt(prompt)
        # router.route_prompt now returns structured dict
        got = pred.get('task') if isinstance(pred, dict) else pred
        if got == label:
            correct += 1
    acc = correct / len(data)
    assert acc >= 0.7, f'router accuracy too low: {acc:.2f}'
