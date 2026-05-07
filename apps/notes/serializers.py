from rest_framework import serializers
from .models import StudentNote


class StudentNoteSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source='author.get_full_name', read_only=True)

    class Meta:
        model = StudentNote
        fields = ('id', 'student', 'author', 'author_name', 'note', 'created_at')
        read_only_fields = ('id', 'student', 'author', 'created_at')


class StudentNoteCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentNote
        fields = ('id', 'note')
        read_only_fields = ('id',)
