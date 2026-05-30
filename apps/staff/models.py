from django.db import models
from apps.base import BaseModel


STATUS_CHOICES = [
    ('active',   'Faol'),
    ('archived', 'Arxivlangan'),
]


class Staff(BaseModel):
    company       = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='staff_members')
    user          = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='staff_profile')
    salary_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    status        = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    notes         = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'staff'

    @property
    def full_name(self):
        return self.user.get_full_name()

    def __str__(self):
        return self.full_name


class StaffSalary(BaseModel):
    SALARY_STATUS_CHOICES = [
        ('unpaid',  'Unpaid'),
        ('partial', 'Partial'),
        ('paid',    'Paid'),
    ]

    staff             = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='salaries')
    company           = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='staff_member_salaries')
    month             = models.DateField()
    calculated_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_amount       = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    carry_over        = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    due_date          = models.DateField(null=True, blank=True)
    status            = models.CharField(max_length=10, choices=SALARY_STATUS_CHOICES, default='unpaid')
    is_paid           = models.BooleanField(default=False)
    paid_at           = models.DateTimeField(null=True, blank=True)
    note              = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'staff_member_salaries'
        unique_together = ['staff', 'month']

    @property
    def total_owed(self):
        return self.calculated_amount + self.carry_over - self.paid_amount

    def __str__(self):
        return f"{self.staff} — {self.month}"
