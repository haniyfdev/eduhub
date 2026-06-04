from django.db import models
from apps.base import BaseModel


class Group(BaseModel):
    GENDER_TYPE_CHOICES = [
        ('a', 'Male'),
        ('b', 'Female'),
        ('c', 'Mixed'),
    ]

    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='groups')
    course = models.ForeignKey('courses.Course', on_delete=models.CASCADE, related_name='groups')
    teacher = models.ForeignKey('teachers.Teacher', on_delete=models.CASCADE, related_name='groups')
    number = models.PositiveIntegerField()
    gender_type = models.CharField(max_length=1, choices=GENDER_TYPE_CHOICES, null=True, blank=True)
    room = models.ForeignKey(
        'rooms.Room',
        on_delete=models.PROTECT,
        null=False, blank=False,
        related_name='groups',
    )
    schedule = models.CharField(max_length=200, null=True, blank=True)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[('active', 'Active'), ('archived', 'Archived'), ('frozen', 'Frozen')],
        default='active',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'groups'

    @property
    def display_name(self):
        return f"{self.number}{(self.gender_type or '').upper()}"

    def __str__(self):
        return self.display_name


class GroupStudent(BaseModel):
    STATUS_CHOICES = [
        ('trial',  'Trial'),
        ('active', 'Active'),
        ('frozen', 'Frozen'),
        ('left',   'Left'),
    ]

    student   = models.ForeignKey('students.Student', on_delete=models.CASCADE, related_name='group_memberships')
    group     = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='memberships')
    status    = models.CharField(max_length=20, choices=STATUS_CHOICES, default='trial')
    joined_at = models.DateTimeField()
    left_at   = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'group_students'

    def __str__(self):
        return f"{self.student} in {self.group}"
