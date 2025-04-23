from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import os
import json
from werkzeug.utils import secure_filename
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from PIL import Image  # For image cropping
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
import io
from flask import make_response

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///budget_tracker.db'
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['UPLOAD_FOLDER'] = 'static/profile_images'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Initialize Flask-Login
login_manager = LoginManager(app)
login_manager.login_view = 'login'  # Specify the login view

# User model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    profile_image = db.Column(db.String(120), nullable=True)

# Budget model
class Budget(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    total_budget = db.Column(db.Float, nullable=False)
    remaining_budget = db.Column(db.Float, nullable=False)

# Transaction model
class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.String(10), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    type = db.Column(db.String(10), nullable=False)  # 'income' or 'expense'
    category = db.Column(db.String(50), nullable=True)

# PreviousBudget model
class PreviousBudget(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    total_budget = db.Column(db.Float, nullable=False)
    remaining_budget = db.Column(db.Float, nullable=True)
    expenses = db.Column(db.String(500), nullable=False)  # JSON string of expenses
    date = db.Column(db.String(10), nullable=False)

# Load user callback for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Create database
def create_database():
    if not os.path.exists('instance'):
        os.makedirs('instance')
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    with app.app_context():
        db.create_all()

create_database()

# Check if file is allowed
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Crop image to fit circular profile
def crop_image(image_path):
    img = Image.open(image_path)
    width, height = img.size
    size = min(width, height)
    left = (width - size) / 2
    top = (height - size) / 2
    right = (width + size) / 2
    bottom = (height + size) / 2
    img = img.crop((left, top, right, bottom))
    img.thumbnail((100, 100))  # Resize to fit profile image
    img.save(image_path)

# Inject current_user into all templates
@app.context_processor
def inject_user():
    return dict(current_user=current_user)

# Routes
@app.route('/')
@login_required
def index():
    user_id = current_user.id
    budget = Budget.query.filter_by(user_id=user_id).first()
    transactions = Transaction.query.filter_by(user_id=user_id).order_by(Transaction.date.desc()).limit(5).all()

    total_income = db.session.query(db.func.sum(Transaction.amount)).filter_by(user_id=user_id, type='income').scalar() or 0
    total_expenses = db.session.query(db.func.sum(Transaction.amount)).filter_by(user_id=user_id, type='expense').scalar() or 0

    return render_template('index.html', budget=budget, transactions=transactions, total_income=total_income, total_expenses=total_expenses)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()

        if not user or not check_password_hash(user.password, password):
            flash('Invalid email or password', 'danger')
            # Return the same page with flashed messages
            return render_template('login.html', 
                                keep_form_data=True,
                                email=email), 401  # HTTP Unauthorized

        login_user(user)
        return redirect(url_for('index'))

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        # Check if username or email already exists
        existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
        if existing_user:
            flash('Username or email already exists. Please choose another.', 'danger')
            return redirect(url_for('register'))

        # Create new user
        new_user = User(username=username, email=email, password=generate_password_hash(password))
        db.session.add(new_user)
        db.session.commit()

        # Clear any existing budget and transactions for the new user
        Budget.query.filter_by(user_id=new_user.id).delete()
        Transaction.query.filter_by(user_id=new_user.id).delete()
        PreviousBudget.query.filter_by(user_id=new_user.id).delete()
        db.session.commit()

        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

@app.route('/profile')
@login_required
def profile():
    user_id = current_user.id
    user = User.query.get(user_id)
    budget = Budget.query.filter_by(user_id=user_id).first()
    return render_template('profile.html', user=user, budget=budget)


@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        flash('Password reset instructions have been sent to your email.', 'success')
        return redirect(url_for('login'))
    return render_template('forgot_password.html')

@app.route('/set_budget', methods=['POST'])
@login_required
def set_budget():
    data = request.get_json()
    total_budget = data['total_budget']
    user_id = current_user.id

    budget = Budget.query.filter_by(user_id=user_id).first()
    if budget:
        budget.total_budget = total_budget
        budget.remaining_budget = total_budget
    else:
        budget = Budget(user_id=user_id, total_budget=total_budget, remaining_budget=total_budget)
        db.session.add(budget)

    db.session.commit()
    return {'success': True}

@app.route('/add_expense', methods=['POST'])
@login_required
def add_expense():
    data = request.get_json()
    description = data['description']
    amount = float(data['amount'])
    category = data['category']
    date = datetime.now().strftime('%Y-%m-%d')
    user_id = current_user.id

    budget = Budget.query.filter_by(user_id=user_id).first()
    if budget and budget.remaining_budget >= amount:
        budget.remaining_budget -= amount
    else:
        return {'success': False, 'message': 'Expense exceeds remaining budget!'}

    transaction = Transaction(user_id=user_id, date=date, description=description, amount=amount, type='expense', category=category)
    db.session.add(transaction)
    db.session.commit()

    return {'success': True}

@app.route('/summary')
@login_required
def summary():
    user_id = current_user.id
    transactions = Transaction.query.filter_by(user_id=user_id, type='expense').order_by(Transaction.date.desc()).all()
    budget = Budget.query.filter_by(user_id=user_id).first()
    return render_template('summary.html', transactions=transactions, budget=budget)

@app.route('/faq')
@login_required
def faq():
    return render_template('faq.html')

@app.route('/previous_records')
@login_required
def previous_records():
    user_id = current_user.id
    previous_budgets = PreviousBudget.query.filter_by(user_id=user_id).order_by(PreviousBudget.date.desc()).all()
    return render_template('previous_records.html', previous_budgets=previous_budgets)

@app.route('/change_email', methods=['POST'])
@login_required
def change_email():
    data = request.get_json()
    new_email = data['email']
    user_id = current_user.id

    user = User.query.get(user_id)
    if user:
        user.email = new_email
        db.session.commit()
        return {'success': True}
    else:
        return {'success': False, 'message': 'User not found.'}

@app.route('/change_password', methods=['POST'])
@login_required
def change_password():
    data = request.get_json()
    new_password = data['password']
    user_id = current_user.id

    user = User.query.get(user_id)
    if user:
        user.password = generate_password_hash(new_password)
        db.session.commit()
        return {'success': True}
    else:
        return {'success': False, 'message': 'User not found.'}

        
@app.route('/delete_account', methods=['POST'])
@login_required
def delete_account():
    user_id = current_user.id
    user = User.query.get(user_id)
    if user:
        # Clear all user data
        Budget.query.filter_by(user_id=user_id).delete()
        Transaction.query.filter_by(user_id=user_id).delete()
        PreviousBudget.query.filter_by(user_id=user_id).delete()
        
        # Delete user and commit
        db.session.delete(user)
        db.session.commit()
        
        # Clear session completely
        logout_user()
        session.clear()
        
        return {
            'success': True,
            'redirect_url': url_for('register')
        }
    return {'success': False}

    
@app.route('/reset_budget', methods=['POST'])
@login_required
def reset_budget():
    user_id = current_user.id
    budget = Budget.query.filter_by(user_id=user_id).first()
    
    if budget:
        # 1. Archive current budget data
        expenses = Transaction.query.filter_by(user_id=user_id, type='expense').all()
        expense_data = {
            category: sum(t.amount for t in expenses if t.category == category) 
            for category in ['Entertainment', 'Food', 'Travel', 'Electronics', 'Rent', 'Other']
        }
        
        previous_budget = PreviousBudget(
            user_id=user_id,
            total_budget=budget.total_budget,
            remaining_budget=budget.remaining_budget,
            expenses=json.dumps(expense_data),
            date=datetime.now().strftime('%Y-%m-%d')
        )
        db.session.add(previous_budget)
        
        # 2. Clear ALL transactions
        Transaction.query.filter_by(user_id=user_id).delete()
        
        # 3. Reset budget to zero
        budget.total_budget = 0
        budget.remaining_budget = 0
        db.session.commit()
        
        # Return JSON response for AJAX handling
        return {
            'success': True,
            'redirect_url': url_for('index')
        }
    
    return {'success': False}

@app.route('/delete_record/<int:record_id>', methods=['POST'])
@login_required
def delete_record(record_id):
    record = PreviousBudget.query.get(record_id)
    if record:
        db.session.delete(record)
        db.session.commit()
        return {'success': True}
    else:
        return {'success': False, 'message': 'Record not found.'}

@app.route('/upload_profile_image', methods=['POST'])
@login_required
def upload_profile_image():
    if 'file' not in request.files:
        return {'success': False, 'message': 'No file uploaded'}

    file = request.files['file']
    if file.filename == '':
        return {'success': False, 'message': 'No file selected'}

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # Update user's profile image in DB
        user = User.query.get(current_user.id)
        if user:
            user.profile_image = filename
            db.session.commit()
            return {
                'success': True,
                'message': 'Profile image updated!',
                'image_url': url_for('static', filename=f'profile_images/{filename}')
            }
        else:
            return {'success': False, 'message': 'User not found'}
    else:
        return {'success': False, 'message': 'Invalid file type'}
@app.route('/generate_report')
@login_required
def generate_report():
    user_id = current_user.id
    
    # Get current budget data
    budget = Budget.query.filter_by(user_id=user_id).first()
    
    # Get expense summary and calculate totals
    expenses = Transaction.query.filter_by(user_id=user_id, type='expense').all()
    expense_summary = {}
    total_spent = 0
    for expense in expenses:
        if expense.category not in expense_summary:
            expense_summary[expense.category] = 0
        expense_summary[expense.category] += expense.amount
        total_spent += expense.amount
    
    # Get previous records and calculate spent amounts
    previous_records = PreviousBudget.query.filter_by(user_id=user_id).order_by(PreviousBudget.date.desc()).all()
    processed_records = []
    for record in previous_records:
        record_data = json.loads(record.expenses)
        total_record_spent = sum(float(amount) for amount in record_data.values())
        processed_records.append({
            'date': record.date,
            'total_budget': record.total_budget,
            'remaining_budget': record.remaining_budget,
            'spent': total_record_spent
        })
    
    # Create PDF
    response = make_response()
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=budget_report.pdf'
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name='PurpleTitle',
        parent=styles['Heading2'],
        textColor=colors.white,
        backColor='#4a148c',
        alignment=1,  # center
        spaceAfter=20
    ))
    styles.add(ParagraphStyle(
        name='PurpleSubtitle',
        parent=styles['Heading3'],
        textColor='#4a148c',
        alignment=1,  # center
        spaceAfter=10
    ))
    styles.add(ParagraphStyle(
        name='BudgetSummary',
        parent=styles['Normal'],
        alignment=1,  # center
        fontSize=12,
        spaceAfter=20
    ))
    
    elements = []
    
    # Report title
    elements.append(Paragraph("Report of your budget so far", styles['PurpleTitle']))
    
    # Current Budget Summary
    if budget:
        elements.append(Paragraph(
            f"Total Budget: ₹{budget.total_budget:,.2f} | Spent: ₹{total_spent:,.2f} | Remaining: ₹{budget.remaining_budget:,.2f}",
            styles['BudgetSummary']
        ))
    
    # Expenditure Summary
    elements.append(Paragraph("Expenditure Summary", styles['PurpleSubtitle']))
    
    # Create summary table
    summary_data = [["Category", "Total Amount (₹)"]]
    for category, amount in expense_summary.items():
        summary_data.append([category, f"₹{amount:,.2f}"])
    
    summary_table = Table(summary_data)
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), '#4a148c'),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(summary_table)
    
    # Page break for previous records
    elements.append(PageBreak())
    
    # Previous Records
    elements.append(Paragraph("Previous Records", styles['PurpleSubtitle']))
    
    # Create previous records table with spent amounts
    records_data = [["Date", "Total Budget", "Spent", "Remaining"]]
    for record in processed_records:
        records_data.append([
            record['date'],
            f"₹{float(record['total_budget']):,.2f}",
            f"₹{record['spent']:,.2f}",
            f"₹{float(record['remaining_budget']):,.2f}" if record['remaining_budget'] else "N/A"
        ])
    
    records_table = Table(records_data)
    records_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), '#4a148c'),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(records_table)
    
    # Footer with current date
    elements.append(Paragraph(
        datetime.now().strftime("%Y-%m-%d %H:%M:%S (%A)"),
        ParagraphStyle(
            name='Footer',
            parent=styles['Normal'],
            alignment=1,  # center
            spaceBefore=20
        )
    ))
    
    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    response.data = pdf
    
    return response
    
if __name__ == '__main__':
    app.run(debug=True)



