from django.db import models
from apps.base import BaseModel


class SuperadminLog(BaseModel):
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='superadmin_logs')
    action = models.CharField(max_length=255)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'superadmin_logs'

    def __str__(self):
        return f"{self.user} — {self.action}"


class SubscriptionPlan(models.Model):
    price = models.DecimalField(max_digits=15, decimal_places=2)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='plan_updates',
    )

    class Meta:
        db_table = 'subscription_plan'

    def __str__(self):
        return f"Plan: {self.price}"


class CompanySubscriptionDebt(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('partial', 'Partial'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
    ]

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='subscription_debts',
    )
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'company_subscription_debts'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.company.name} — {self.period_start} — {self.status}"


class CompanySubscriptionPayment(models.Model):
    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='subscription_payments',
    )
    debt = models.ForeignKey(
        CompanySubscriptionDebt,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments',
    )
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    paid_at = models.DateTimeField(auto_now_add=True)
    recorded_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recorded_subscription_payments',
    )

    class Meta:
        db_table = 'company_subscription_payments'
        ordering = ['-paid_at']

    def __str__(self):
        return f"{self.company.name} — {self.amount}"
