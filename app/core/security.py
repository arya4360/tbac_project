from .data import USER_DB, TASK_POLICY_DB, FILESYSTEM_POLICY
from pathlib import PurePosixPath


def check_task_authorization(user_id: str, task_name: str) -> bool:
    user = USER_DB.get(user_id)
    if not user:
        return False
    task = TASK_POLICY_DB.get(task_name)
    if not task:
        return False
    # Check each required tool permission
    for tool, level in task.required_tools.items():
        user_level = user.permissions.get(tool, 'none')
        if level == 'read' and user_level in ('read','read_write','write'):
            continue
        if level == 'write' and user_level in ('write','read_write'):
            continue
        if level == 'deploy' and user_level == 'deploy':
            continue
        return False
    return True


def check_filesystem_access(user_id: str, path: str) -> bool:
    """Simple folder-level enforcement with basic normalization and traversal protection.

    - Uses PurePosixPath to parse the provided path without touching the filesystem.
    - Rejects paths that contain parent-segment references ('..').
    - Expects the first path segment to be a folder listed in FILESYSTEM_POLICY.
    """
    if not path:
        return False
    try:
        p = PurePosixPath(path)
        parts = [part for part in p.parts if part not in ('/', '.')]
        # reject traversal
        if '..' in parts:
            return False
        if not parts:
            return False
        folder = parts[0]
        allowed = FILESYSTEM_POLICY.get(folder, [])
        return user_id in allowed
    except Exception:
        return False


def check_tool_authorization(user_id: str, tool_call) -> bool:
    """Policy Enforcement Point (tool-level) with least-privilege checks.

    Enhancements:
    - Action -> required permission mapping is stricter (migrate/rollback => deploy).
    - Parameter whitelisting per tool; unknown params are rejected.
    - Sensitive params require write-level permission.
    - Secrets access requires an explicit permission entry for 'Secrets'.
    - Filesystem path-level checks remain enforced via check_filesystem_access.

    tool_call is expected to have attributes: tool_name, action, parameters (may include 'path').
    """
    user = USER_DB.get(user_id)
    if not user:
        return False

    tool_name = getattr(tool_call, 'tool_name', None)
    action = getattr(tool_call, 'action', '') or ''
    params = getattr(tool_call, 'parameters', {}) or {}

    # Define per-tool allowed parameters and whether they are sensitive
    TOOL_PARAM_POLICY = {
        'GitHub': {'repo': {'sensitive': False}, 'content': {'sensitive': True}},
        'FileSystem': {'path': {'sensitive': False}, 'content': {'sensitive': True}},
        'Secrets': {'name': {'sensitive': False}},
        'CRM': {'lead': {'sensitive': False}},
        'DB': {'script': {'sensitive': True}, 'approval_id': {'sensitive': False}},
        'Deployment': {'env': {'sensitive': False}, 'approval_id': {'sensitive': False}},
    }

    # Filesystem path-level check
    if tool_name == 'FileSystem':
        path = params.get('path', '')
        if not check_filesystem_access(user_id, path):
            return False

    # Map action -> required permission level (least-privilege oriented)
    action_lower = action.lower()
    if any(tok in action_lower for tok in ('read', 'get', 'list', 'fetch')):
        required = 'read'
    elif any(tok in action_lower for tok in ('deploy', 'migrate', 'rollback')):
        # migrations/rollbacks are treated as deploy-level operations
        required = 'deploy'
    elif any(tok in action_lower for tok in ('delete', 'remove', 'destroy')):
        # destructive actions require write level (do not treat as read)
        required = 'write'
    else:
        # default to write for other mutating actions
        required = 'write'

    # Parameter-level checks: whitelist and sensitivity enforcement
    tool_policy = TOOL_PARAM_POLICY.get(tool_name)
    if tool_policy is not None:
        for p_key, p_val in params.items():
            if p_key not in tool_policy:
                # Unknown parameter supplied -> reject (least privilege)
                return False
            # if param is marked sensitive require write-level permission
            if tool_policy[p_key].get('sensitive'):
                user_level = user.permissions.get(tool_name, 'none')
                if user_level not in ('write', 'read_write'):
                    return False

    # Secrets tool requires explicit Secrets permission (read or write)
    if tool_name == 'Secrets':
        user_level = user.permissions.get('Secrets', 'none')
        if user_level not in ('read', 'write'):
            return False

    # Final permission check (map user_level to ability)
    user_level = user.permissions.get(tool_name, 'none')
    if required == 'read' and user_level in ('read', 'read_write', 'write'):
        return True
    if required == 'write' and user_level in ('write', 'read_write'):
        return True
    if required == 'deploy' and user_level == 'deploy':
        return True

    # Fallback deny
    return False
