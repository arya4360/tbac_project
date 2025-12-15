"""Promote verified prompts into the labeled dataset (prompt_labels.csv).

Usage:
  python3 scripts/promote_verified.py [--dry-run]

This script reads data/verified_prompts.csv and for each row appends a labeled
pair to data/prompt_labels.csv (using app.core.data.add_labeled_prompt) if not
already present. Use --dry-run to see what would be promoted without modifying files.
"""
import csv
import argparse
from pathlib import Path
import subprocess
import sys

DATA_DIR = Path(__file__).resolve().parent.parent / 'data'
VERIFIED_FP = DATA_DIR / 'verified_prompts.csv'


def main(dry_run: bool = False):
    if not VERIFIED_FP.exists():
        print('No verified_prompts.csv found at', VERIFIED_FP)
        return

    try:
        from app.core.data import add_labeled_prompt
    except Exception:
        print('Could not import app.core.data.add_labeled_prompt; run from project root with PYTHONPATH set')
        return

    to_promote = []
    with open(VERIFIED_FP, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            prompt = row.get('prompt')
            task = row.get('task')
            if not prompt or not task:
                continue
            to_promote.append((prompt.strip(), task.strip()))

    if not to_promote:
        print('No entries to promote')
        return

    for prompt, task in to_promote:
        print(('DRY:' if dry_run else 'PROMOTING:'), f'"{prompt}" -> {task}')
        if not dry_run:
            try:
                add_labeled_prompt(prompt, task)
            except Exception:
                print('Failed to promote:', prompt)

    # After promoting, optionally build embeddings to include new labels
    if not dry_run:
        print('\nBuilding embeddings to include promoted labels...')
        try:
            res = subprocess.run([sys.executable, 'scripts/build_embeddings.py'], check=False)
            if res.returncode == 0:
                print('Embedding build completed successfully.')
            else:
                print('Embedding build failed with exit code', res.returncode)
        except Exception as e:
            print('Failed to run build_embeddings.py:', str(e))

    print('Done')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--dry-run', action='store_true', help='Show promotions without writing')
    args = p.parse_args()
    main(dry_run=args.dry_run)
