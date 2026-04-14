from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify
from flask_login import login_required
from app import db
from app.models import Bill, BillPayment, Bank
from app.forms import BillForm, BillPaymentForm
from datetime import date, datetime
from decimal import Decimal

bp = Blueprint('bills', __name__, url_prefix='/house/bills')


@bp.before_request
@login_required
def require_login():
    pass


def _populate_bill_form_choices(form):
    banks = Bank.query.filter_by(is_active=True).order_by(Bank.name).all()
    form.bank_id.choices = [(0, '— None —')] + [(b.id, b.name) for b in banks]


def _populate_payment_form_choices(form):
    banks = Bank.query.filter_by(is_active=True).order_by(Bank.name).all()
    form.bank_id.choices = [(0, '— None —')] + [(b.id, b.name) for b in banks]


# ---------------------------------------------------------------------------
# Dashboard — monthly bill tracker
# ---------------------------------------------------------------------------

@bp.route('/')
def index():
    today = date.today()
    year  = request.args.get('year',  type=int, default=today.year)
    month = request.args.get('month', type=int, default=today.month)

    # Clamp
    if month < 1:  month = 12; year -= 1
    if month > 12: month = 1;  year += 1

    # Prev / next month links
    prev_month = month - 1 or 12
    prev_year  = year - (1 if month == 1 else 0)
    next_month = month % 12 + 1
    next_year  = year + (1 if month == 12 else 0)

    bills = Bill.query.filter_by(is_active=True).order_by(Bill.sort_order, Bill.name).all()

    # Index existing payments for this month so we don't do N+1 queries
    payment_map = {}
    if bills:
        bill_ids = [b.id for b in bills]
        payments = BillPayment.query.filter(
            BillPayment.bill_id.in_(bill_ids),
            BillPayment.period_year == year,
            BillPayment.period_month == month,
            BillPayment.is_active == True,
        ).all()
        for p in payments:
            payment_map[p.bill_id] = p

    # Totals
    total_expected = sum(
        (payment_map[b.id].amount or Decimal('0'))
        for b in bills if b.id in payment_map and payment_map[b.id].amount
    )
    paid_count   = sum(1 for b in bills if b.id in payment_map and payment_map[b.id].is_paid)
    unpaid_count = len(bills) - paid_count

    banks = Bank.query.filter_by(is_active=True).order_by(Bank.name).all()

    return render_template('house/bills.html',
        bills=bills,
        payment_map=payment_map,
        year=year, month=month,
        prev_year=prev_year, prev_month=prev_month,
        next_year=next_year, next_month=next_month,
        total_expected=total_expected,
        paid_count=paid_count, unpaid_count=unpaid_count,
        banks=banks,
        today=today,
    )


# ---------------------------------------------------------------------------
# Record / update payment  (AJAX POST)
# ---------------------------------------------------------------------------

@bp.route('/<int:bill_id>/pay', methods=['POST'])
def record_payment(bill_id):
    bill = Bill.query.get_or_404(bill_id)
    data = request.get_json(force=True)

    year  = int(data.get('year',  date.today().year))
    month = int(data.get('month', date.today().month))

    payment = BillPayment.query.filter_by(
        bill_id=bill_id, period_year=year, period_month=month, is_active=True
    ).first()

    if payment is None:
        payment = BillPayment(bill_id=bill_id, period_year=year, period_month=month)
        db.session.add(payment)

    raw_amount = data.get('amount', '').strip()
    payment.amount       = Decimal(raw_amount) if raw_amount else None
    payment.is_paid      = bool(data.get('is_paid', False))
    payment.paid_date    = _parse_date(data.get('paid_date'))
    payment.bank_id      = int(data['bank_id']) if data.get('bank_id') and int(data['bank_id']) else None
    payment.check_number = data.get('check_number', '').strip() or None
    payment.notes        = data.get('notes', '').strip() or None

    db.session.commit()

    bank_name = payment.payment_bank.name if payment.bank_id and payment.payment_bank else None
    return jsonify({
        'ok': True,
        'payment_id': payment.id,
        'is_paid': payment.is_paid,
        'amount': str(payment.amount) if payment.amount is not None else '',
        'paid_date': payment.paid_date.isoformat() if payment.paid_date else '',
        'bank_name': bank_name or '',
        'check_number': payment.check_number or '',
    })


@bp.route('/payment/<int:payment_id>/delete', methods=['POST'])
def delete_payment(payment_id):
    payment = BillPayment.query.get_or_404(payment_id)
    payment.is_active = False
    db.session.commit()
    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# Bill CRUD
# ---------------------------------------------------------------------------

@bp.route('/add', methods=['GET', 'POST'])
def add_bill():
    form = BillForm()
    _populate_bill_form_choices(form)
    if form.validate_on_submit():
        bill = Bill(
            name           = form.name.data.strip(),
            provider       = form.provider.data.strip() or None,
            account_number = form.account_number.data.strip() or None,
            auto_pay       = form.auto_pay.data,
            bank_id        = form.bank_id.data if form.bank_id.data else None,
            notes          = form.notes.data.strip() or None,
        )
        db.session.add(bill)
        db.session.commit()
        flash(f'Bill "{bill.name}" added.', 'success')
        return redirect(url_for('bills.index'))
    return render_template('house/bill_form.html', form=form, bill=None)


@bp.route('/<int:bill_id>/edit', methods=['GET', 'POST'])
def edit_bill(bill_id):
    bill = Bill.query.get_or_404(bill_id)
    form = BillForm(obj=bill)
    _populate_bill_form_choices(form)
    if form.validate_on_submit():
        bill.name           = form.name.data.strip()
        bill.provider       = form.provider.data.strip() or None
        bill.account_number = form.account_number.data.strip() or None
        bill.auto_pay       = form.auto_pay.data
        bill.bank_id        = form.bank_id.data if form.bank_id.data else None
        bill.notes          = form.notes.data.strip() or None
        db.session.commit()
        flash(f'Bill "{bill.name}" updated.', 'success')
        return redirect(url_for('bills.index'))
    return render_template('house/bill_form.html', form=form, bill=bill)


@bp.route('/<int:bill_id>/delete', methods=['POST'])
def delete_bill(bill_id):
    bill = Bill.query.get_or_404(bill_id)
    bill.is_active = False
    db.session.commit()
    flash(f'Bill "{bill.name}" removed.', 'success')
    return redirect(url_for('bills.index'))


# ---------------------------------------------------------------------------
# Bill detail — full payment history
# ---------------------------------------------------------------------------

@bp.route('/<int:bill_id>')
def bill_detail(bill_id):
    bill = Bill.query.get_or_404(bill_id)
    payments = BillPayment.query.filter_by(
        bill_id=bill_id, is_active=True
    ).order_by(
        BillPayment.period_year.desc(), BillPayment.period_month.desc()
    ).all()

    total_paid = sum(
        (p.amount for p in payments if p.is_paid and p.amount), Decimal('0')
    )
    return render_template('house/bill_detail.html',
        bill=bill, payments=payments, total_paid=total_paid)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None
