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
    group_student = models.OneToOneField('groups.GroupStudent', on_delete=models.CASCADE, related_name='debt')
    amount          = models.DecimalField(max_digits=15, decimal_places=2)
    due_date        = models.DateField()
    status          = models.CharField(max_length=10, choices=STATUS_CHOICES)
    discount        = models.ForeignKey(
        'discounts.Discount', on_delete=models.SET_NULL, null=True, blank=True, related_name='debts',
    )
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    updated_at      = models.DateTimeField(auto_now=True)
    confirmed_at    = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'debts'

    def __str__(self):
        return f"{self.group_student} — {self.amount} ({self.status})"
