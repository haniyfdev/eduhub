import uuid
from django.db import models
from apps.base import BaseModel


class CompanySettings(BaseModel):
    BILLING_TYPE_CHOICES = [
        ('monthly', 'Monthly'),
        ('per_lesson', 'Per Lesson'),
        ('upfront', 'Upfront'),
    ]
    ABSENT_POLICY_CHOICES = [
        ('ignore', 'Ignore'),
        ('deduct', 'Deduct from Debt'),
        ('penalty', 'Add Penalty'),
    ]
    CONTRACT_BREAK_CHOICES = [
        ('full', 'Full Salary'),
        ('prorate', 'Prorated Salary'),
        ('none', 'No Salary'),
    ]

    company = models.OneToOneField(
        'Company',
        on_delete=models.CASCADE,
        related_name='settings',
    )
    billing_type = models.CharField(max_length=20, choices=BILLING_TYPE_CHOICES, default='monthly')
    absent_policy = models.CharField(max_length=20, choices=ABSENT_POLICY_CHOICES, default='ignore')
    teacher_contract_break_policy = models.CharField(max_length=20, choices=CONTRACT_BREAK_CHOICES, default='full')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'company_settings'

    def __str__(self):
        return f"Settings for {self.company}"


class Company(BaseModel):
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, null=True, blank=True)
    address = models.CharField(max_length=500, null=True, blank=True)
    branch_of = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='branches',
    )
    description = models.TextField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[('active', 'Active'), ('archived', 'Archived')],
        default='active',
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'companies'

    def __str__(self):
        return self.name
