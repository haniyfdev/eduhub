from django.db import models
from apps.base import BaseModel


class StudentNote(BaseModel):
    student = models.ForeignKey('students.Student', on_delete=models.CASCADE, related_name='notes')
    author = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='student_notes')
    note = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'student_notes'

    def __str__(self):
        return f"Note for {self.student} by {self.author}"
