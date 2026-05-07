from django.db import models
from apps.base import BaseModel


class Lesson(BaseModel):
    group = models.ForeignKey('groups.Group', on_delete=models.CASCADE, related_name='lessons')
    teacher = models.ForeignKey('teachers.Teacher', on_delete=models.CASCADE, related_name='lessons')
    topic = models.CharField(max_length=255)
    date = models.DateField()
    note = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'lessons'

    def __str__(self):
        return f"{self.topic} — {self.date}"
