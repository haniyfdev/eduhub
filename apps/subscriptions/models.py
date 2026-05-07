from django.db import models
from apps.base import BaseModel


class Subscription(BaseModel):
    PLAN_CHOICES = [
        ('basic', 'Basic'),
        ('pro', 'Pro'),
        ('enterprise', 'Enterprise'),
    ]
    BILLING_TYPE_CHOICES = [
        ('per_student', 'Per Student'),
        ('flat', 'Flat'),
    ]
    INTERVAL_CHOICES = [
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
    ]
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]

    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='subscriptions')
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES)
    billing_type = models.CharField(max_length=20, choices=BILLING_TYPE_CHOICES)
    price_per_unit = models.DecimalField(max_digits=15, decimal_places=2)
    interval = models.CharField(max_length=20, choices=INTERVAL_CHOICES)
    students_count = models.IntegerField(null=True, blank=True)
    amount_billed = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    started_at = models.DateField()
    expires_at = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)

    class Meta:
        db_table = 'subscriptions'

    def __str__(self):
        return f"{self.company} — {self.plan} ({self.status})"
