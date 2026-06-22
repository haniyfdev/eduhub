from decimal import Decimal
from django.db.models import Sum


def get_refund_candidate_info(gs):
    """For a left GroupStudent with no existing Refund, compute total_paid,
    earned_amount and refund_amount (earned/refund are None for manual
    billing — admin must enter manually). Returns None if this group_student
    is not actually a refund candidate (still enrolled, already has a
    Refund, no payment to refund, or no overpayment).

    Shared by RefundViewSet.candidates and PaymentSerializer's
    refund_candidate flag, so both surfaces agree on the same numbers.
    """
    from apps.debts.models import Debt
    from apps.debts.services import compute_billing_breakdown
    from apps.payments.models import Payment
    from .models import Refund

    if gs.status != 'left' or gs.left_at is None:
        return None
    if Refund.objects.filter(group_student=gs).exists():
        return None

    debt = Debt.objects.filter(group_student=gs).order_by('-billing_month', '-due_date').first()
    month_start = debt.billing_month if debt and debt.billing_month else gs.left_at.date().replace(day=1)

    total_paid = Payment.objects.filter(
        group_student=gs,
        paid_at__year=month_start.year,
        paid_at__month=month_start.month,
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    if total_paid <= 0:
        return None

    billing_type = gs.archive_billing_type or 'manual'
    breakdown = None

    if billing_type == 'manual':
        earned_amount = None
        refund_amount = None
    else:
        breakdown = compute_billing_breakdown(gs, debt)
        breakdown.pop('month_start', None)
        breakdown.pop('end_date', None)
        earned_amount = Decimal(str(breakdown['calculated_amount'] or 0))
        refund_amount = total_paid - earned_amount
        if refund_amount <= 0:
            return None

    return {
        'debt':          debt,
        'total_paid':    total_paid,
        'earned_amount': earned_amount,
        'refund_amount': refund_amount,
        'billing_type':  billing_type,
        'breakdown':     breakdown,
    }
