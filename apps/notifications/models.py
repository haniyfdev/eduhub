from django.db import models
from apps.base import BaseModel


class Notification(BaseModel):
    TYPE_CHOICES = [
        ('sms', 'SMS'),
        ('call', 'Call'),
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
    TYPE_CHOICES = [
        ('debt', 'Debt'),
        ('welcome', 'Welcome'),
        ('reminder', 'Reminder'),
        ('custom', 'Custom'),
    ]

    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='sms_templates')
    name = models.CharField(max_length=255)
    body = models.TextField()
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
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
