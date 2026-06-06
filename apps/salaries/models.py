from django.db import models
from apps.base import BaseModel


class TeacherSalary(BaseModel):
    STATUS_CHOICES = [
        ('unpaid',  'Unpaid'),
        ('partial', 'Partial'),
        ('paid',    'Paid'),
    ]

    company           = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='teacher_salaries')
    teacher           = models.ForeignKey('teachers.Teacher', on_delete=models.CASCADE, related_name='salaries')
    group             = models.ForeignKey('groups.Group', on_delete=models.CASCADE, null=True, blank=True, related_name='teacher_salaries')
    month             = models.DateField()
    due_date          = models.DateField(null=True, blank=True)
    base_amount       = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    kpi_amount        = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_amount      = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    calculated_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    paid_amount       = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    carry_over        = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    status            = models.CharField(max_length=10, choices=STATUS_CHOICES, default='unpaid')
    is_paid           = models.BooleanField(default=False)
    paid_at           = models.DateTimeField(null=True, blank=True)
    archive_billing_type = models.CharField(max_length=20, null=True, blank=True)
    note              = models.TextField(null=True, blank=True)
    created_at        = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'teacher_salaries'
        unique_together = [('teacher', 'group', 'month')]

    def __str__(self):
        return f"{self.teacher} — {self.month}"


class TeacherWorkLog(BaseModel):
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='teacher_work_logs')
    teacher = models.ForeignKey('teachers.Teacher', on_delete=models.CASCADE, related_name='work_logs')
    lesson = models.ForeignKey('lessons.Lesson', on_delete=models.CASCADE, related_name='work_logs')
    hours = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    students_count = models.IntegerField()
    logged_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'teacher_work_logs'

    def __str__(self):
        return f"{self.teacher} — {self.lesson}"


class StaffSalary(BaseModel):
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='staff_salaries')
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='staff_salaries')
    month = models.DateField()
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    kpi_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    paid_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'staff_salaries'

    def __str__(self):
        return f"{self.user} — {self.month}"


class StaffKpiRule(BaseModel):
    METRIC_CHOICES = [
        ('attendance_rate', 'Attendance Rate'),
        ('payment_collected', 'Payment Collected'),
        ('student_enrolled', 'Student Enrolled'),
    ]
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('manager', 'Manager'),
        ('any', 'Any'),
    ]

    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='kpi_rules')
    name = models.CharField(max_length=255)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    metric = models.CharField(max_length=30, choices=METRIC_CHOICES)
    threshold = models.DecimalField(max_digits=15, decimal_places=2)
    bonus_amount = models.DecimalField(max_digits=15, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=[('active', 'Active'), ('archived', 'Archived')],
        default='active',
    )
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'staff_kpi_rules'

    def __str__(self):
        return f"{self.company} — {self.name}"
