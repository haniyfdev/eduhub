from django.db import models
from apps.base import BaseModel


class Award(BaseModel):
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='awards')
    title = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    image_url = models.CharField(max_length=500, null=True, blank=True)
    issued_to = models.ForeignKey('students.Student', on_delete=models.CASCADE, related_name='awards')
    issued_at = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'awards'

    def __str__(self):
        return f"{self.title} → {self.issued_to}"
