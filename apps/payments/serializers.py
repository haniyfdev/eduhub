from decimal import Decimal
from django.utils import timezone
from rest_framework import serializers
from .models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    course_name = serializers.CharField(source='course.name', read_only=True)
    group_display = serializers.CharField(source='group.display_name', read_only=True)

    class Meta:
        model = Payment
        fields = (
            'id', 'company', 'student', 'student_name', 'group', 'course', 'course_name',
            'discount', 'amount', 'payment_type', 'note', 'paid_at', 'group_display'
        )
        read_only_fields = ('id', 'company', 'amount', 'paid_at')

    def get_student_name(self, obj):
        return f"{obj.student.first_name} {obj.student.last_name}"


class PaymentCreateSerializer(serializers.Serializer):
    """
    Rule 3 — payments are immutable after creation.
    Business logic §1: validate ownership, apply discount, freeze amount, update debt, send SMS.
    """
    student_id = serializers.UUIDField()
    group_id = serializers.UUIDField()
    course_id = serializers.UUIDField()
    discount_id = serializers.UUIDField(required=False, allow_null=True)
    requested_amount = serializers.DecimalField(max_digits=15, decimal_places=2, min_value=Decimal('0.01'))
    payment_type = serializers.ChoiceField(choices=['cash', 'card', 'transfer'])
    note = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, data):
        from apps.students.models import Student
        from apps.groups.models import Group
        from apps.courses.models import Course
        from apps.discounts.models import Discount

        company = self.context['company']

        # Step 1 — validate all objects belong to same company
        try:
            data['student'] = Student.objects.get(id=data['student_id'], company=company)
        except Student.DoesNotExist:
            raise serializers.ValidationError({'student_id': 'Student not found in this company.'})

        try:
            data['group'] = Group.objects.get(id=data['group_id'], company=company)
        except Group.DoesNotExist:
            raise serializers.ValidationError({'group_id': 'Group not found in this company.'})

        try:
            data['course'] = Course.objects.get(id=data['course_id'], company=company)
        except Course.DoesNotExist:
            raise serializers.ValidationError({'course_id': 'Course not found in this company.'})

        # Step 2 — apply discount
        final_amount = data['requested_amount']
        discount = None
        if data.get('discount_id'):
            try:
                discount = Discount.objects.get(id=data['discount_id'], company=company)
            except Discount.DoesNotExist:
                raise serializers.ValidationError({'discount_id': 'Discount not found in this company.'})

            if discount.type == 'percent':
                final_amount = data['requested_amount'] * (1 - discount.value / 100)
            else:
                final_amount = data['requested_amount'] - discount.value

            if final_amount < 0:
                raise serializers.ValidationError({'discount_id': 'Discount results in a negative amount.'})

        data['final_amount'] = final_amount
        data['discount'] = discount
        return data

    def create(self, validated_data):
        from apps.debts.models import Debt
        from apps.notifications.tasks import send_payment_confirmation_sms

        company = self.context['company']

        # Step 3 — create immutable Payment record
        payment = Payment.objects.create(
            company=company,
            student=validated_data['student'],
            group=validated_data['group'],
            course=validated_data['course'],
            discount=validated_data.get('discount'),
            amount=validated_data['final_amount'],
            payment_type=validated_data['payment_type'],
            note=validated_data.get('note', ''),
            paid_at=timezone.now(),
        )

        # Step 4 — update Debt record
        try:
            debt = Debt.objects.get(student=validated_data['student'])
            debt.amount -= validated_data['final_amount']
            if debt.amount <= 0:
                debt.status = 'paid'
                debt.amount = Decimal('0')
            else:
                debt.status = 'partial'
            debt.save()
        except Debt.DoesNotExist:
            pass  # debt not yet assigned (first payment before billing cycle)

        # Step 5 — send confirmation SMS asynchronously (Rule 6)
        # try:
        #     send_payment_confirmation_sms.delay(
        #         str(validated_data['student'].id),
        #         str(validated_data['final_amount']),
        #     )
        # except Exception as e:
        #     pass

        try: # bu vaqtincha !
            send_payment_confirmation_sms.apply(
                args=[str(validated_data['student'].id), str(validated_data['final_amount'])],
            )
        except Exception:
            pass

        return payment
