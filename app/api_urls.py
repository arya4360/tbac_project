from django.urls import path
from app.api import QueryAPIView, ApprovalsAPIView

urlpatterns = [
    path('v1/query/', QueryAPIView.as_view(), name='query'),
    path('v1/approvals/', ApprovalsAPIView.as_view(), name='approvals'),
]
