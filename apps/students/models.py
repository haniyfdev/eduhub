from django.db import models
from apps.base import BaseModel


class Student(BaseModel):
    REFERRAL_CHOICES = [
        ('banner', 'Banner'),
        ('friend', 'Friend'),
        ('parent', 'Parent'),
        ('social_media', 'Social Media'),
        ('other', 'Other'),
    ]
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('trial', 'Trial'),
        ('archived', 'Archived'),
        ('frozen', 'Frozen'),
    ]

    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='students')
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    second_phone = models.CharField(max_length=20, null=True, blank=True)
    course = models.ForeignKey(
        'courses.Course', on_delete=models.SET_NULL, null=True, blank=True, related_name='students'
    )
    birth_date = models.DateField(null=True, blank=True)
    referral_source = models.CharField(max_length=20, choices=REFERRAL_CHOICES, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    lead = models.OneToOneField(
        'leads.Lead', on_delete=models.SET_NULL, null=True, blank=True, related_name='student'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'students'

    def __str__(self):
        return f"{self.first_name} {self.last_name}"
