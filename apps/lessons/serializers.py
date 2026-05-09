from rest_framework import serializers
from .models import Lesson


class LessonSerializer(serializers.ModelSerializer):
    group_display = serializers.CharField(source='group.display_name', read_only=True)
    teacher_name = serializers.CharField(source='teacher.user.get_full_name', read_only=True)

    class Meta:
        model = Lesson
        fields = (
            'id', 'group', 'group_display', 'teacher', 'teacher_name',
            'topic', 'date', 'note', 'started_at', 'finished_at', 'status',
        )
        read_only_fields = ('id', 'teacher', 'started_at', 'finished_at')


class LessonCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lesson
        fields = ('id', 'group', 'topic', 'date', 'note')
        read_only_fields = ('id',)
