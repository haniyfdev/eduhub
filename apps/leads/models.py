from django.db import models
from apps.students.models import Student


class LeadManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(status__in=['pending', 'trial', 'ignored'])


class Lead(Student):
    objects = LeadManager()

    class Meta:
        proxy = True
        verbose_name = 'Lead'
        verbose_name_plural = 'Leads'
