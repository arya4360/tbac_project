from .models import User, Task
from pathlib import Path
import json
from datetime import datetime

# Core personas (per spec)
USER_DB = {
    # Engineering - Alex: builds and ships product features, full repo access
    'eng01': User(
        id='eng01',
        name='Alex',
        team='Engineering',
        permissions={
            'GitHub': 'write',        # read & write
            'FileSystem': 'read_write',
            'Deployment': 'deploy',
        }
    ),

    # IT - Priya: handles ITSM tickets, infra scripts, troubleshooting with limited engineering access
    'it01': User(
        id='it01',
        name='Priya',
        team='IT',
        permissions={
            'GitHub': 'read',         # read-only repo access
            'FileSystem': 'read',     # access to IT folder only (enforced by FILESYSTEM_POLICY)
            'Deployment': 'deploy',
        }
    ),

    # Sales - Marco: sales collateral and proposals only
    'sales01': User(
        id='sales01',
        name='Marco',
        team='Sales',
        permissions={
            'GitHub': 'none',
            'FileSystem': 'read',     # access to Sales folder only
            'CRM': 'write',
        }
    ),
}

# Filesystem folder-level policy: map folder name -> allowed user ids
# Enforce in tool_manager when file path contains the folder name (simple policy)
FILESYSTEM_POLICY = {
    'Engineering': ['eng01'],
    'IT': ['it01'],
    'Sales': ['sales01'],
}

# Task policies mapping business tasks to the minimum required tool-level permissions
TASK_POLICY_DB = {
    # Engineering tasks
    'Feature_Development': Task(name='Feature_Development', required_tools={'GitHub': 'write'}),
    'Production_Support': Task(name='Production_Support', required_tools={'GitHub': 'read', 'FileSystem': 'read'}),

    # IT tasks
    'Incident_Resolution': Task(name='Incident_Resolution', required_tools={'GitHub': 'read', 'FileSystem': 'read'}),
    'Infrastructure_Maintenance': Task(name='Infrastructure_Maintenance', required_tools={'Deployment': 'deploy', 'FileSystem': 'read'}),

    # Sales tasks
    'Lead_Generation': Task(name='Lead_Generation', required_tools={'CRM': 'write'}),
    'Proposal_Development': Task(name='Proposal_Development', required_tools={'FileSystem': 'read'}),
}

# Reference prompts used by the semantic router / keyword router to classify user prompts into tasks
REFERENCE_PROMPTS = {
    'Feature_Development': [
        'Write new component',
        'Fix bug',
        'Commit change',
        'Push a new README file to the main branch.',
        'Create a new API endpoint and commit the implementation',
    ],

    'Production_Support': [
        'Investigate why the service crashed',
        'Check deployment logs for the last service incident',
        'Investigate incident logs',
        'Restart the failing service and collect logs'
    ],

    'Incident_Resolution': [
        'Troubleshoot system logs',
        'Investigate incident logs',
    ],

    'Infrastructure_Maintenance': [
        'Run maintenance scripts on the server',
        'Perform infrastructure upgrade',
        'Apply security patches to servers',
    ],

    'Lead_Generation': [
        'Generate a list of leads for the EMEA region',
        'Find potential customers for product X'
    ],

    'Proposal_Development': [
        'Prepare a proposal document for customer',
        'Assemble sales collateral and slides for the RFP'
    ]
}

# --- Centralized data directory: project-root `data/` ---
# e.g. /path/to/tbac_project/data
APP_DATA_DIR = Path(__file__).resolve().parent.parent.parent / 'data'
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Paths for persisted embedding assets and CSVs (single source of truth)
REF_EMB_FILE = APP_DATA_DIR / 'reference_embeddings.npy'
REF_STR_FILE = APP_DATA_DIR / 'reference_strings.json'
PROMPT_LABELS_CSV = APP_DATA_DIR / 'prompt_labels.csv'
FAILURE_PROMPTS_CSV = APP_DATA_DIR / 'failure_prompts.csv'
VERIFIED_PROMPTS_CSV = APP_DATA_DIR / 'verified_prompts.csv'


def get_reference_items():
    """Return a flat list of reference items (dicts with 'task' and 'text').

    Uses the canonical REFERENCE_PROMPTS and the single `data/prompt_labels.csv`.

    Labeled prompts (from PROMPT_LABELS_CSV) are returned first so they take
    precedence over the built-in REFERENCE_PROMPTS when performing substring
    matching. This prevents canonical references from shadowing curated labels.
    """
    items = []

    # 1) Add labeled prompts (if available) to increase reference coverage and
    #    make them take precedence over the built-in REFERENCE_PROMPTS.
    labels_csv = PROMPT_LABELS_CSV
    if labels_csv.exists():
        import csv
        with open(labels_csv, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # guard against malformed rows
                if 'prompt' in row and 'task' in row and row['prompt'] and row['task']:
                    items.append({'task': row['task'], 'text': row['prompt']})

    # 2) Add canonical reference prompts after labeled prompts so they serve as
    #    a fallback when no labeled example exists.
    for task, refs in REFERENCE_PROMPTS.items():
        for r in refs:
            items.append({'task': task, 'text': r})

    return items


def record_routing_result(prompt: str, success: bool, task: str = None, source: str = 'router'):
    try:
        import csv
        ts = datetime.utcnow().isoformat()
        if not success:
            fp = FAILURE_PROMPTS_CSV
            # avoid duplicate prompts in failure log (check first column)
            already = False
            if fp.exists():
                with open(fp, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    for row in reader:
                        if len(row) > 0 and row[0] == prompt:
                            already = True
                            break
            if not already:
                with open(fp, 'a', encoding='utf-8', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([prompt, source, ts])
        else:
            vp = VERIFIED_PROMPTS_CSV
            # ensure header exists
            if not vp.exists():
                with open(vp, 'w', encoding='utf-8', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['prompt', 'task', 'source', 'ts'])
            # avoid duplicate prompts in verified log (match on prompt)
            already = False
            with open(vp, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('prompt') == prompt:
                        already = True
                        break
            if not already:
                with open(vp, 'a', encoding='utf-8', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([prompt, task or '', source, ts])
    except Exception:
        pass


def add_labeled_prompt(prompt: str, task: str):
    """Append a labeled prompt to PROMPT_LABELS_CSV if not already present.

    Creates the CSV with header if it does not exist and avoids exact duplicates.
    """
    labels_fp = PROMPT_LABELS_CSV
    try:
        import csv
        # ensure file exists with header
        if not labels_fp.exists():
            with open(labels_fp, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['prompt', 'task'])
        # check for exact duplicate
        exists = False
        with open(labels_fp, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('prompt') == prompt and row.get('task') == task:
                    exists = True
                    break
        if not exists:
            with open(labels_fp, 'a', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([prompt, task])
    except Exception:
        pass
