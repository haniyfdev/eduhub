from django.db import models
from apps.base import BaseModel


class Discount(BaseModel):
    TYPE_CHOICES = [
        ('percent', 'Percent'),
        ('fixed', 'Fixed'),
    ]

    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='discounts')
    course = models.ForeignKey(
        'courses.Course', on_delete=models.SET_NULL, null=True, blank=True, related_name='discounts'
    )
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    value = models.DecimalField(max_digits=15, decimal_places=2)
    condition = models.TextField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[('active', 'Active'), ('archived', 'Archived')],
        default='active',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'discounts'

    def __str__(self):
        return self.name
