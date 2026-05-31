from django.db import models
from apps.base import BaseModel


class Teacher(BaseModel):
    SALARY_TYPE_CHOICES = [
        ('fixed', 'Fixed'),
        ('percent', 'Percent'),
        ('per_student', 'Per Student'),
    ]

    user = models.OneToOneField('users.User', on_delete=models.CASCADE, related_name='teacher')
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='teachers')
    subject = models.CharField(max_length=100, blank=True, default='')
    birth_date = models.DateField(null=True, blank=True)
    salary_type = models.CharField(max_length=20, choices=SALARY_TYPE_CHOICES)
    fixed_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    salary_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    per_student_amt = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    kpi_bonus = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[('active', 'Active'), ('frozen', 'Frozen'), ('archived', 'Archived')],
        default='active',
    )
    hired_at = models.DateField()
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'teachers'

    def __str__(self):
        return self.user.get_full_name()
