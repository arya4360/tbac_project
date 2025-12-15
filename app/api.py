# Try to import DRF symbols but provide minimal fallbacks when DRF is not available
try:
    from rest_framework.views import APIView
    from rest_framework.response import Response
    from rest_framework import status
except Exception:
    # Lightweight fallbacks used when running tests without DRF installed.
    class APIView:
        pass

    class Response(dict):
        def __init__(self, data=None, status=None, *args, **kwargs):
            super().__init__(data or {})
            self.status_code = status

    class _Status:
        HTTP_200_OK = 200
        HTTP_400_BAD_REQUEST = 400
        HTTP_403_FORBIDDEN = 403
        HTTP_404_NOT_FOUND = 404
        HTTP_500_INTERNAL_SERVER_ERROR = 500

    status = _Status()


from app.core.models import AgentResponse
from app.core.data import USER_DB
from app.core.approvals import APPROVALS, approve_approval
from app.services import router, agent
from app.core import security
import uuid
from datetime import datetime


class QueryAPIView(APIView):
    """Django REST endpoint for processing prompt requests following the TBAC flow."""
    def post(self, request):
        trace_id = request.headers.get('X-Trace-Id') or str(uuid.uuid4())
        data = request.data or {}
        user_id = data.get('user_id')
        prompt = data.get('prompt')
        if not user_id or not isinstance(prompt, str):
            return Response({'status': 'error', 'message': 'user_id and prompt required', 'trace_id': trace_id}, status=status.HTTP_400_BAD_REQUEST)

        user = USER_DB.get(user_id)
        if not user:
            return Response({'status': 'error', 'message': 'Unknown user', 'trace_id': trace_id}, status=status.HTTP_404_NOT_FOUND)

        # Stage 1: semantic routing
        r = router.route_prompt(prompt)

        # If router couldn't find a task, return a clear error
        if not r or r.get('task') is None:
            return Response({'status': 'error', 'message': r.get('error', 'No route found'), 'trace_id': trace_id}, status=status.HTTP_400_BAD_REQUEST)

        task = r.get('task')

        # P.E.P 1: task-level authorization
        if not security.check_task_authorization(user_id, task):
            return Response({'status': 'denied', 'message': 'User not authorized for task', 'trace_id': trace_id}, status=status.HTTP_403_FORBIDDEN)

        # Stage 2: execute task with agent
        resp = agent.execute_task(user_id, prompt, task)
        http_status = status.HTTP_200_OK if resp.status == 'ok' else status.HTTP_403_FORBIDDEN if resp.status == 'denied' else status.HTTP_400_BAD_REQUEST
        payload = resp.dict()
        payload['trace_id'] = trace_id
        return Response(payload, status=http_status)


class ApprovalsAPIView(APIView):
    """Approve or query approval requests in the persistent APPROVALS store.

    POST body: { 'approval_id': str, 'approver_id': str }
    """
    def post(self, request):
        approval_id = request.data.get('approval_id')
        approver_id = request.data.get('approver_id')
        if not approval_id or not approver_id:
            return Response({'status': 'error', 'message': 'approval_id and approver_id required'}, status=status.HTTP_400_BAD_REQUEST)
        appr = APPROVALS.get(approval_id)
        if not appr:
            return Response({'status': 'error', 'message': 'Unknown approval id'}, status=status.HTTP_404_NOT_FOUND)
        ok = approve_approval(approval_id, approver_id)
        if not ok:
            return Response({'status': 'error', 'message': 'Failed to approve'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response({'status': 'ok', 'approval_id': approval_id, 'message': 'Approved'})
