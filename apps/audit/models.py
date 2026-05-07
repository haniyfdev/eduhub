from django.db import models
from apps.base import BaseModel


class AuditLog(BaseModel):
    ACTION_CHOICES = [
        ('created', 'Created'),
        ('updated', 'Updated'),
        ('deleted', 'Deleted'),
    ]

    company = models.ForeignKey(
        'companies.Company', on_delete=models.CASCADE, null=True, blank=True, related_name='audit_logs'
    )
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='audit_logs')
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=100)
    object_id = models.UUIDField()
    old_data = models.JSONField(null=True, blank=True)
    new_data = models.JSONField(null=True, blank=True)
    description = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'audit_logs'

    def __str__(self):
        return f"{self.action} {self.model_name} by {self.user}"
