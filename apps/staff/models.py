from django.db import models
from apps.base import BaseModel

ROLE_CHOICES = [
    ('admin',       'Admin'),
    ('manager',     'Menejer'),
    ('accountant',  'Buxgalter'),
    ('security',    'Qorovul'),
    ('cleaner',     'Farrosh'),
    ('supply',      'Zavxoz'),
    ('other',       'Boshqa'),
]

CONTRACT_TYPE_CHOICES = [
    ('monthly',  'Oylik belgilangan'),
    ('contract', 'Shartnomaviy'),
]

STATUS_CHOICES = [
    ('active',   'Faol'),
    ('archived', 'Arxivlangan'),
]


class Staff(BaseModel):
    company        = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='staff_members')
    first_name     = models.CharField(max_length=100)
    last_name      = models.CharField(max_length=100)
    phone          = models.CharField(max_length=20)
    role           = models.CharField(max_length=20, choices=ROLE_CHOICES)
    contract_type  = models.CharField(max_length=20, choices=CONTRACT_TYPE_CHOICES, default='monthly')
    salary_amount  = models.DecimalField(max_digits=12, decimal_places=2)
    contract_months = models.IntegerField(null=True, blank=True)
    contract_start = models.DateField(null=True, blank=True)
    contract_end   = models.DateField(null=True, blank=True)
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    hired_at       = models.DateField(auto_now_add=True)
    notes          = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'staff'

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

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
    status            = models.CharField(max_length=10, choices=SALARY_STATUS_CHOICES, default='unpaid')
    is_paid           = models.BooleanField(default=False)
    paid_at           = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'staff_member_salaries'
        unique_together = ['staff', 'month']

    @property
    def total_owed(self):
        return self.calculated_amount + self.carry_over - self.paid_amount

    def __str__(self):
        return f"{self.staff} — {self.month}"
