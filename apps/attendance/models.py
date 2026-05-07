from django.db import models
from apps.base import BaseModel


class Attendance(BaseModel):
    STATUS_CHOICES = [
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('late', 'Late'),
    ]

    lesson = models.ForeignKey('lessons.Lesson', on_delete=models.CASCADE, related_name='attendances')
    student = models.ForeignKey('students.Student', on_delete=models.CASCADE, related_name='attendances')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    note = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'attendance'

    def __str__(self):
        return f"{self.student} — {self.lesson} — {self.status}"
