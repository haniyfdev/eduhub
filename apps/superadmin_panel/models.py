from django.db import models
from apps.base import BaseModel


class SuperadminLog(BaseModel):
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='superadmin_logs')
    action = models.CharField(max_length=255)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'superadmin_logs'

    def __str__(self):
        return f"{self.user} — {self.action}"
