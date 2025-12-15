from django.db import models


class Approval(models.Model):
    approval_id = models.CharField(max_length=64, unique=True)
    requested_by = models.CharField(max_length=64)
    tool = models.CharField(max_length=64)
    action = models.CharField(max_length=128)
    params = models.JSONField(null=True, blank=True)
    status = models.CharField(max_length=32, default='pending')
    requested_at = models.DateTimeField(auto_now_add=True)
    approved_by = models.CharField(max_length=64, null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Approval({self.approval_id}, {self.status})"


class AuditEntry(models.Model):
    ts = models.DateTimeField(auto_now_add=True)
    user = models.CharField(max_length=64)
    tool = models.CharField(max_length=64)
    action = models.CharField(max_length=128)
    params = models.JSONField(null=True, blank=True)
    decision = models.CharField(max_length=32)
    message = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"AuditEntry({self.pk}, {self.user}, {self.decision})"
