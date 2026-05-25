from django.db import models
from apps.base import BaseModel


class Discount(BaseModel):
    company     = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='discounts')
    student     = models.ForeignKey('students.Student', on_delete=models.CASCADE, related_name='discounts')
    course      = models.ForeignKey('courses.Course', on_delete=models.CASCADE, related_name='discounts')
    percent     = models.PositiveIntegerField()
    months      = models.PositiveIntegerField()
    start_month = models.DateField()
    end_month   = models.DateField()
    created_by  = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, related_name='created_discounts')
    note        = models.TextField(null=True, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'discounts'

    def save(self, *args, **kwargs):
        from dateutil.relativedelta import relativedelta
        self.end_month = self.start_month + relativedelta(months=self.months)
        super().save(*args, **kwargs)

    def is_active_for_month(self, month_date):
        return self.start_month <= month_date <= self.end_month

    def __str__(self):
        return f"{self.student} — {self.percent}% ({self.months} oy)"
