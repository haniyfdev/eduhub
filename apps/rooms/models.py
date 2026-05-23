from django.db import models
from apps.base import BaseModel


class Room(BaseModel):
    GENDER_CHOICES = [
        ('a', 'Bolalar'),
        ('b', 'Qizlar'),
        ('c', 'Aralash'),
    ]
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('archived', 'Archived'),
    ]

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='rooms',
    )
    name = models.IntegerField()
    gender_type = models.CharField(
        max_length=1,
        choices=GENDER_CHOICES,
        null=True, blank=True,
    )
    capacity = models.IntegerField(null=True, blank=True)
    floor = models.IntegerField(null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='active',
    )

    class Meta:
        db_table = 'rooms'
        unique_together = ['company', 'name']

    def __str__(self):
        return f"Xona {self.name}"
