from django.db import models
from apps.base import BaseModel


class Notification(BaseModel):
    TYPE_CHOICES = [
        ('sms', 'SMS'),
        ('call', 'Call'),
        ('telegram', 'Telegram'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
    ]

    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='notifications')
    recipient_phone = models.CharField(max_length=20)
    message = models.TextField()
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notifications'

    def __str__(self):
        return f"{self.recipient_phone} — {self.type} — {self.status}"


class SmsTemplate(BaseModel):
    TRIGGER_CHOICES = [
        ('debt_reminder', 'Qarzdorlik eslatmasi'),
        ('payment_confirmed', "To'lov tasdiqi"),
        ('lesson_reminder', 'Dars eslatmasi'),
        ('course_started', 'Kurs boshlanishi'),
        ('overdue_debt', "Muddati o'tgan qarz"),
        ('custom', 'Boshqa'),
    ]

    company = models.ForeignKey(
        'companies.Company', on_delete=models.CASCADE,
        related_name='sms_templates', null=True, blank=True,
    )
    name = models.CharField(max_length=100)
    body = models.TextField()
    trigger = models.CharField(max_length=30, choices=TRIGGER_CHOICES, default='custom')
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sms_templates'

    def __str__(self):
        return self.name


class Announcement(BaseModel):
    title = models.CharField(max_length=200)
    body = models.TextField()
    created_by = models.ForeignKey(
        'users.User', on_delete=models.CASCADE,
        related_name='announcements'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'announcements'
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class AnnouncementRead(BaseModel):
    announcement = models.ForeignKey(
        Announcement, on_delete=models.CASCADE,
        related_name='reads'
    )
    user = models.ForeignKey(
        'users.User', on_delete=models.CASCADE,
        related_name='announcement_reads'
    )
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'announcement_reads'
        unique_together = ['announcement', 'user']
