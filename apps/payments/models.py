from django.db import models
from apps.base import BaseModel


class Payment(BaseModel):
    PAYMENT_TYPE_CHOICES = [
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('transfer', 'Transfer'),
    ]

    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='payments')
    student = models.ForeignKey('students.Student', on_delete=models.CASCADE, related_name='payments')
    group = models.ForeignKey('groups.Group', on_delete=models.CASCADE, related_name='payments')
    course = models.ForeignKey('courses.Course', on_delete=models.CASCADE, related_name='payments')
    discount = models.ForeignKey(
        'discounts.Discount', on_delete=models.SET_NULL, null=True, blank=True, related_name='payments'
    )
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    payment_type = models.CharField(max_length=10, choices=PAYMENT_TYPE_CHOICES)
    note = models.TextField(null=True, blank=True)
    paid_at = models.DateTimeField()

    class Meta:
        db_table = 'payments'

    def __str__(self):
        return f"{self.student} — {self.amount} — {self.paid_at}"
