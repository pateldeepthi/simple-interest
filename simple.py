from flask import Flask, render_template, request, jsonify, make_response
import io
import csv
from datetime import datetime

app = Flask(__name__, static_folder='static', template_folder='templates')


def _parse_float(value, default=0.0, name=None):
    """Parse value as float. Treat empty strings or None as default. Raise ValueError for invalid non-empty values."""
    if value is None:
        return default
    if isinstance(value, str) and value.strip() == '':
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid numeric input for {name or 'value'}")


def _parse_int(value, default=0, name=None):
    if value is None:
        return default
    if isinstance(value, str) and value.strip() == '':
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid integer input for {name or 'value'}")


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/calc', methods=['POST'])
def calculate():
    data = request.get_json(silent=True) or request.form or {}
    try:
        principal = _parse_float(data.get('principal', 0), default=0.0, name='principal')
        rate = _parse_float(data.get('rate', 0), default=0.0, name='rate')
        time = _parse_float(data.get('time', 0), default=0.0, name='time')
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    simple_interest = (principal * rate * time) / 100
    total_amount = principal + simple_interest

    return jsonify({'simple_interest': round(simple_interest, 2), 'total_amount': round(total_amount, 2)})


def add_months(start_date, months):
    """Return a date months after start_date (keeps end-of-month behaviour)."""
    year = start_date.year + (start_date.month - 1 + months) // 12
    month = (start_date.month - 1 + months) % 12 + 1
    # days in month, handle leap-year for February
    mdays = [31, 29 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    day = min(start_date.day, mdays[month - 1])
    return datetime(year, month, day).date()


@app.route('/api/simple_loan', methods=['POST'])
def simple_loan():
    """Compute a simple-interest loan amortization schedule and optionally return CSV.

    Expected inputs (JSON or form):
      - principal: float
      - annual_rate: percent (e.g., 6 for 6%)
      - term_years: float
      - payments_per_year: int (default 12)
      - start_date: YYYY-MM-DD (optional, default today)
      - export: 'csv' or 'json' (default 'json')
      - include_schedule: true/false (default true)
    """
    data = request.get_json(silent=True) or request.form or {}
    try:
        principal = _parse_float(data.get('principal', 0), default=0.0, name='principal')
        annual_rate = _parse_float(data.get('annual_rate', data.get('rate', 0)), default=0.0, name='annual_rate')
        term_years = _parse_float(data.get('term_years', data.get('time', 0)), default=0.0, name='term_years')
        payments_per_year = _parse_int(data.get('payments_per_year', 12), default=12, name='payments_per_year')
        start_date_str = data.get('start_date')
        export = data.get('export', 'json')
        include_schedule = str(data.get('include_schedule', 'true')).lower() in ('true', '1', 'yes')
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    n_payments = int(round(term_years * payments_per_year))
    if n_payments <= 0:
        return jsonify({'error': 'Term must be positive'}), 400

    periodic_rate = (annual_rate / 100.0) / payments_per_year
    # Fixed payment (level-payment amortization). If zero rate, divide principal equally.
    if periodic_rate == 0:
        payment = round(principal / n_payments, 2)
    else:
        payment = round(principal * (periodic_rate) / (1 - (1 + periodic_rate) ** (-n_payments)), 2)

    # Parse start date
    if start_date_str:
        try:
            start_date = datetime.fromisoformat(start_date_str).date()
        except ValueError:
            return jsonify({'error': 'Invalid start_date format, use YYYY-MM-DD'}), 400
    else:
        start_date = datetime.today().date()

    balance = principal
    schedule = []
    total_interest = 0.0

    for i in range(1, n_payments + 1):
        interest = round(balance * periodic_rate, 2)
        principal_paid = round(payment - interest, 2)
        # On the last payment, adjust to clear the remaining balance (avoid rounding residue)
        if i == n_payments:
            principal_paid = round(balance, 2)
            payment_amount = round(principal_paid + interest, 2)
            balance = 0.0
        else:
            payment_amount = payment
            balance = round(balance - principal_paid, 2)

        total_interest += interest
        pay_date = add_months(start_date, i - 1)
        schedule.append({
            'payment_no': i,
            'date': pay_date.isoformat(),
            'payment': round(payment_amount, 2),
            'interest': interest,
            'principal': principal_paid,
            'balance': round(balance, 2)
        })

    total_payment = round(principal + total_interest, 2)

    result = {
        'payment': round(payment, 2),
        'total_interest': round(total_interest, 2),
        'total_payment': total_payment,
    }
    if include_schedule:
        result['schedule'] = schedule

    if str(export).lower() == 'csv':
        si = io.StringIO()
        cw = csv.writer(si)
        cw.writerow(['payment_no', 'date', 'payment', 'interest', 'principal', 'balance'])
        for r in schedule:
            cw.writerow([r['payment_no'], r['date'], f"{r['payment']:.2f}", f"{r['interest']:.2f}", f"{r['principal']:.2f}", f"{r['balance']:.2f}"])
        output = make_response(si.getvalue())
        output.headers['Content-Disposition'] = 'attachment; filename=simple_loan_schedule.csv'
        output.headers['Content-Type'] = 'text/csv'
        return output

    return jsonify(result)


if __name__ == '__main__':
    # Run without the debug reloader so the process stays stable when
    # launched from scripts or Start-Process.
    app.run(host='127.0.0.1', port=5000, debug=False)
