from django.db import models
from apps.base import BaseModel


class Course(BaseModel):
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='courses')
    teachers = models.ManyToManyField('teachers.Teacher', blank=True, related_name='courses')
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    price = models.DecimalField(max_digits=15, decimal_places=2)
    duration_months = models.IntegerField()
    duration_hours = models.DecimalField(max_digits=4, decimal_places=1)
    status = models.CharField(
        max_length=20,
        choices=[('active', 'Active'), ('archived', 'Archived')],
        default='active',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'courses'

    def __str__(self):
        return self.name
