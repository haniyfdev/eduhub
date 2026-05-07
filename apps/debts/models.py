from django.db import models
from apps.base import BaseModel


class Debt(BaseModel):
    STATUS_CHOICES = [
        ('unpaid', 'Unpaid'),
        ('partial', 'Partial'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
    ]

    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='debts')
    student = models.OneToOneField('students.Student', on_delete=models.CASCADE, related_name='debt')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    due_date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'debts'

    def __str__(self):
        return f"{self.student} — {self.amount} ({self.status})"
