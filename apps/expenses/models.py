from django.db import models
from apps.base import BaseModel


class Expense(BaseModel):
    CATEGORY_CHOICES = [
        ('rent', 'Rent'),
        ('utility', 'Utility'),
        ('tax', 'Tax'),
        ('fine', 'Fine'),
        ('discount', 'Discount'),
        ('teacher_salary', 'Teacher Salary'),
        ('staff_salary', 'Staff Salary'),
        ('other', 'Other'),
    ]
    SOURCE_CHOICES = [
        ('auto', 'Auto'),
        ('manual', 'Manual'),
    ]

    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='expenses')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    description = models.CharField(required=False, max_length=500)
    expense_date = models.DateField()
    reference_id = models.UUIDField(null=True, blank=True)
    created_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'expenses'

    def __str__(self):
        return f"{self.category} — {self.amount} ({self.expense_date})"
