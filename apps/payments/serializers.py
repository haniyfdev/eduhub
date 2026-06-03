from decimal import Decimal
from django.utils import timezone
from rest_framework import serializers
from .models import Payment
from apps.debts.models import Debt


class PaymentSerializer(serializers.ModelSerializer):
    student_id = serializers.CharField(source='group_student.student.id', read_only=True)
    student_name = serializers.SerializerMethodField()
    student_phone = serializers.CharField(source='group_student.student.phone', read_only=True)
    course_name = serializers.CharField(source='group_student.group.course.name', read_only=True)
    group_display = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = (
            'id', 'company', 'group_student',
            'student_id', 'student_name', 'student_phone',
            'group_display', 'course_name',
            'discount', 'amount', 'payment_type', 'note', 'paid_at',
        )
        read_only_fields = ('id', 'company', 'paid_at')

    def get_student_name(self, obj):
        s = obj.group_student.student
        return f"{s.first_name} {s.last_name}"

    def get_group_display(self, obj):
        g = obj.group_student.group
        return f"{g.number}{(g.gender_type or '').upper()}"


class PaymentCreateSerializer(serializers.Serializer):
    group_student_id = serializers.UUIDField()
    discount_id = serializers.UUIDField(required=False, allow_null=True)
    requested_amount = serializers.DecimalField(max_digits=15, decimal_places=2, min_value=Decimal('0.01'))
    payment_type = serializers.ChoiceField(choices=['cash', 'card', 'transfer'])
    note = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, data):
        from apps.groups.models import GroupStudent
        company = self.context['company']
        try:
            gs = GroupStudent.objects.select_related(
                'student', 'group__course'
            ).get(id=data['group_student_id'], group__company=company)
            data['group_student'] = gs
        except GroupStudent.DoesNotExist:
            raise serializers.ValidationError({'group_student_id': 'Not found'})

        final_amount = data['requested_amount']
        discount = None
        if data.get('discount_id'):
            from apps.discounts.models import Discount
            try:
                discount = Discount.objects.get(id=data['discount_id'], company=company)
                if discount.type == 'percent':
                    final_amount = data['requested_amount'] * (1 - discount.value / 100)
                else:
                    final_amount = data['requested_amount'] - discount.value
            except Discount.DoesNotExist:
                pass

        data['final_amount'] = final_amount
        data['discount'] = discount

        try:
            debt = Debt.objects.get(group_student=gs)
            if final_amount > debt.amount:
                raise serializers.ValidationError({'amount': "To'lov summasi qarzdan oshib ketdi"})
        except Debt.DoesNotExist:
            pass

        return data

    def create(self, validated_data):
        company = self.context['company']
        gs = validated_data['group_student']

        payment = Payment.objects.create(
            company=company,
            group_student=gs,
            discount=validated_data.get('discount'),
            amount=validated_data['final_amount'],
            payment_type=validated_data['payment_type'],
            note=validated_data.get('note', ''),
            paid_at=timezone.now(),
        )

        try:
            debt = Debt.objects.get(group_student=gs)
            debt.amount -= validated_data['final_amount']
            if debt.amount <= 0:
                debt.status = 'paid'
                debt.amount = Decimal('0')
            else:
                debt.status = 'partial'
            debt.save()
        except Debt.DoesNotExist:
            pass

        return payment
