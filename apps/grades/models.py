from django.db import models
from apps.base import BaseModel


class Grade(BaseModel):
    lesson = models.ForeignKey('lessons.Lesson', on_delete=models.CASCADE, related_name='grades')
    student = models.ForeignKey('students.Student', on_delete=models.CASCADE, related_name='grades')
    score = models.DecimalField(max_digits=5, decimal_places=2)
    note = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'grades'

    def __str__(self):
        return f"{self.student} — {self.score}"
