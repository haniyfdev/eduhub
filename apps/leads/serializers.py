from apps.students.serializers import StudentSerializer, StudentCreateSerializer
from .models import Lead


class LeadSerializer(StudentSerializer):
    class Meta(StudentSerializer.Meta):
        model = Lead


class LeadCreateSerializer(StudentCreateSerializer):
    class Meta(StudentCreateSerializer.Meta):
        model = Lead
