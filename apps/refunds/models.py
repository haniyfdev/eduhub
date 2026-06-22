from django.db import models
from apps.base import BaseModel


class Refund(BaseModel):
    STATUS_CHOICES = [
        ('pending',   'Pending'),
        ('confirmed', 'Confirmed'),
        ('paid',      'Paid'),
    ]

    company       = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='refunds')
    group_student = models.ForeignKey('groups.GroupStudent', on_delete=models.CASCADE, related_name='refunds')
    debt          = models.ForeignKey('debts.Debt', on_delete=models.SET_NULL, null=True, blank=True, related_name='refunds')
    original_paid = models.DecimalField(max_digits=12, decimal_places=2)
    earned_amount = models.DecimalField(max_digits=12, decimal_places=2)
    refund_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status        = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    confirmed_at  = models.DateTimeField(null=True, blank=True)
    paid_at       = models.DateTimeField(null=True, blank=True)
    note          = models.TextField(null=True, blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'refunds'

    def __str__(self):
        return f"{self.group_student} — refund {self.refund_amount} ({self.status})"
