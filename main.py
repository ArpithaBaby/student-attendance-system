import os
from datetime import date, datetime
from dotenv import load_dotenv
from flask import Flask, render_template, request, session, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, login_user, logout_user, LoginManager, login_required, current_user

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'default_student_mgmt_secret_key_123')

# Database configuration
DB_USER = os.getenv('DB_USER', 'root')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'student')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '3306')
DB_NAME = os.getenv('DB_NAME', 'attendance')

app.config['SQLALCHEMY_DATABASE_URI'] = f"mysql+mysqlconnector://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = "Please log in to access this system."
login_manager.login_message_category = "warning"


# ==========================================
# Models
# ==========================================

class Test(db.Model):
    __tablename__ = 'test'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100))


class Department(db.Model):
    __tablename__ = 'department'
    cid = db.Column(db.Integer, primary_key=True, autoincrement=True)
    branch = db.Column(db.String(100), unique=True, nullable=False)


class Course(db.Model):
    __tablename__ = 'course'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    course_code = db.Column(db.String(50), nullable=False)
    course_name = db.Column(db.String(100), nullable=False)
    branch = db.Column(db.String(50), nullable=False)
    sem = db.Column(db.Integer, default=3, nullable=False)


class Attendence(db.Model):
    __tablename__ = 'attendence'
    aid = db.Column(db.Integer, primary_key=True, autoincrement=True)
    rollno = db.Column(db.String(100))
    attendance = db.Column(db.Integer())


class AttendanceRecord(db.Model):
    __tablename__ = 'attendance_record'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    rollno = db.Column(db.String(50), nullable=False, index=True)
    course_code = db.Column(db.String(50), nullable=True, index=True)  # e.g. 'COA', 'OOPS', 'FLAT'
    date = db.Column(db.String(20), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False)  # 'Present' or 'Absent'
    notes = db.Column(db.String(100), nullable=True)


class Trig(db.Model):
    __tablename__ = 'trig'
    tid = db.Column(db.Integer, primary_key=True, autoincrement=True)
    rollno = db.Column(db.String(100))
    action = db.Column(db.String(100))
    timestamp = db.Column(db.String(100))


class User(UserMixin, db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(1000), nullable=False)


class Student(db.Model):
    __tablename__ = 'student'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    rollno = db.Column(db.String(50), unique=True, nullable=False)
    sname = db.Column(db.String(50), nullable=False)
    sem = db.Column(db.Integer, nullable=False)
    gender = db.Column(db.String(50))
    branch = db.Column(db.String(50))
    email = db.Column(db.String(50))
    number = db.Column(db.String(12))
    address = db.Column(db.String(100))


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ==========================================
# Attendance Calculation Helper Functions
# ==========================================

def get_student_attendance_stats(rollno, filter_course=None):
    """
    Computes attendance stats for a student.
    If filter_course is provided, computes specifically for that subject.
    Also returns subject_breakdown across all courses.
    """
    all_records = AttendanceRecord.query.filter_by(rollno=rollno).all()

    # Filtered records if course is requested
    if filter_course:
        target_records = [r for r in all_records if r.course_code == filter_course]
    else:
        target_records = all_records

    total_classes = len(target_records)
    present_count = sum(1 for r in target_records if r.status == 'Present')
    absent_count = sum(1 for r in target_records if r.status == 'Absent')

    if total_classes > 0:
        percentage = round((present_count / total_classes) * 100, 1)
    else:
        legacy = Attendence.query.filter_by(rollno=rollno).first()
        if legacy and legacy.attendance is not None and not filter_course:
            percentage = float(legacy.attendance)
            total_classes = 100
            present_count = int(percentage)
            absent_count = 100 - present_count
        else:
            percentage = 0.0

    if percentage >= 75:
        status_color = "success"
        status_text = "Eligible"
    elif percentage >= 60:
        status_color = "warning"
        status_text = "Average"
    else:
        status_color = "danger"
        status_text = "Shortage (<75%)"

    # Compute breakdown per subject
    courses_present = set(r.course_code for r in all_records if r.course_code)
    # If student belongs to a branch, also include all registered branch courses
    student = Student.query.filter_by(rollno=rollno).first()
    if student:
        branch_courses = Course.query.filter_by(branch=student.branch, sem=student.sem).all()
        for bc in branch_courses:
            courses_present.add(bc.course_code)

    subject_breakdown = []
    for c_code in sorted(courses_present):
        c_records = [r for r in all_records if r.course_code == c_code]
        c_total = len(c_records)
        c_present = sum(1 for r in c_records if r.status == 'Present')
        c_absent = sum(1 for r in c_records if r.status == 'Absent')
        c_pct = round((c_present / c_total * 100), 1) if c_total > 0 else 0.0

        if c_pct >= 75:
            c_color = "success"
        elif c_pct >= 60:
            c_color = "warning"
        else:
            c_color = "danger"

        # Lookup course title
        course_obj = Course.query.filter_by(course_code=c_code).first()
        c_name = course_obj.course_name if course_obj else c_code

        subject_breakdown.append({
            'code': c_code,
            'name': c_name,
            'total': c_total,
            'present': c_present,
            'absent': c_absent,
            'percentage': c_pct,
            'color': c_color
        })

    return {
        'total_classes': total_classes,
        'present_count': present_count,
        'absent_count': absent_count,
        'percentage': percentage,
        'status_color': status_color,
        'status_text': status_text,
        'records': target_records,
        'subject_breakdown': subject_breakdown
    }


def sync_legacy_attendance(rollno, percentage):
    """Keep legacy Attendence table in sync with calculated percentage"""
    legacy = Attendence.query.filter_by(rollno=rollno).first()
    if legacy:
        legacy.attendance = int(round(percentage))
    else:
        new_att = Attendence(rollno=rollno, attendance=int(round(percentage)))
        db.session.add(new_att)
    db.session.commit()


# ==========================================
# Application Routes (Protected with Login)
# ==========================================

@app.route('/')
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))

    student_count = Student.query.count()
    dept_count = Department.query.count()
    course_count = Course.query.count()
    attendance_records_count = AttendanceRecord.query.count()

    # Calculate overall eligibility counts and average attendance
    all_students = Student.query.all()
    eligible_count = 0
    shortage_count = 0
    total_pct_sum = 0
    for s in all_students:
        stats = get_student_attendance_stats(s.rollno)
        if stats['percentage'] >= 75:
            eligible_count += 1
        else:
            shortage_count += 1
        total_pct_sum += stats['percentage']

    avg_college_attendance = round(total_pct_sum / len(all_students), 1) if all_students else 0.0

    # Department breakdown with student and course counts
    departments = Department.query.order_by(Department.branch).all()
    dept_stats = []
    for d in departments:
        s_count = Student.query.filter_by(branch=d.branch).count()
        c_count = Course.query.filter_by(branch=d.branch).count()
        dept_stats.append({
            'branch': d.branch,
            'student_count': s_count,
            'course_count': c_count
        })

    # Recent attendance sessions
    recent_records = AttendanceRecord.query.order_by(AttendanceRecord.id.desc()).limit(8).all()
    recent_sessions = []
    for r in recent_records:
        st = Student.query.filter_by(rollno=r.rollno).first()
        recent_sessions.append({
            'date': r.date,
            'course': r.course_code or 'General',
            'rollno': r.rollno,
            'name': st.sname if st else 'N/A',
            'branch': st.branch if st else 'N/A',
            'status': r.status
        })

    return render_template('index.html',
                           student_count=student_count,
                           dept_count=dept_count,
                           course_count=course_count,
                           attendance_records_count=attendance_records_count,
                           eligible_count=eligible_count,
                           shortage_count=shortage_count,
                           avg_college_attendance=avg_college_attendance,
                           dept_stats=dept_stats,
                           recent_sessions=recent_sessions)


@app.route('/studentdetails')
@login_required
def studentdetails():
    students = Student.query.order_by(Student.rollno).all()
    students_with_stats = []
    for s in students:
        stats = get_student_attendance_stats(s.rollno)
        students_with_stats.append({
            'student': s,
            'stats': stats
        })
    return render_template('studentdetails.html', students=students_with_stats, query=students)


# ==========================================
# Consolidated Admin Panel Routes
# ==========================================

@app.route('/admin')
@login_required
def admin():
    tab = request.args.get('tab', 'student')
    departments = Department.query.order_by(Department.branch).all()
    courses = Course.query.order_by(Course.branch, Course.course_code).all()
    students = Student.query.order_by(Student.rollno).all()
    return render_template('admin.html',
                           departments=departments,
                           courses=courses,
                           students=students,
                           active_tab=tab)


@app.route('/addcourse', methods=['POST'])
@login_required
def addcourse():
    code = request.form.get('course_code', '').strip().upper()
    name = request.form.get('course_name', '').strip()
    branch = request.form.get('branch', '').strip()
    sem = int(request.form.get('sem', 3))

    if not code or not name or not branch:
        flash("All course fields are required", "warning")
        return redirect(url_for('admin', tab='courses'))

    existing = Course.query.filter_by(course_code=code, branch=branch, sem=sem).first()
    if existing:
        flash(f"Course '{code}' already exists for branch {branch} Semester {sem}", "warning")
        return redirect(url_for('admin', tab='courses'))

    new_course = Course(course_code=code, course_name=name, branch=branch, sem=sem)
    db.session.add(new_course)
    db.session.commit()
    flash(f"Course {code} ({name}) Added Successfully for {branch}!", "success")
    return redirect(url_for('admin', tab='courses'))


@app.route('/deletecourse/<int:id>', methods=['GET', 'POST'])
@login_required
def delete_course(id):
    course = db.session.get(Course, id)
    if course:
        c_code = course.course_code
        db.session.delete(course)
        db.session.commit()
        flash(f"Course '{c_code}' Deleted Successfully", "danger")
    else:
        flash("Course not found", "warning")
    return redirect(url_for('admin', tab='courses'))


@app.route('/department', methods=['POST', 'GET'])
@login_required
def department():
    if request.method == "POST":
        dept = request.form.get('dept')
        if not dept or not dept.strip():
            flash("Department name cannot be empty", "warning")
            return redirect(url_for('admin', tab='dept'))

        dept = dept.strip().upper()
        query = Department.query.filter_by(branch=dept).first()
        if query:
            flash("Department Already Exists", "warning")
            return redirect(url_for('admin', tab='dept'))

        dep = Department(branch=dept)
        db.session.add(dep)
        db.session.commit()
        flash(f"Department '{dept}' Added Successfully", "success")
        return redirect(url_for('admin', tab='dept'))

    return redirect(url_for('admin', tab='dept'))


@app.route('/deletedepartment/<int:cid>', methods=['GET', 'POST'])
@login_required
def delete_department(cid):
    dep = db.session.get(Department, cid)
    if dep:
        dept_name = dep.branch
        db.session.delete(dep)
        db.session.commit()
        flash(f"Department '{dept_name}' Deleted Successfully", "danger")
    else:
        flash("Department not found", "warning")
    return redirect(url_for('admin', tab='dept'))


@app.route('/addstudent', methods=['POST', 'GET'])
@login_required
def addstudent():
    if request.method == "POST":
        rollno = request.form.get('rollno', '').strip()
        sname = request.form.get('sname', '').strip()
        sem = request.form.get('sem', 3)
        gender = request.form.get('gender')
        branch = request.form.get('branch')
        email = request.form.get('email')
        num = request.form.get('num')
        address = request.form.get('address')

        existing = Student.query.filter_by(rollno=rollno).first()
        if existing:
            flash(f"Student with Roll Number {rollno} already exists!", "danger")
            return redirect(url_for('admin', tab='student'))

        new_student = Student(
            rollno=rollno,
            sname=sname,
            sem=int(sem),
            gender=gender,
            branch=branch,
            email=email,
            number=num,
            address=address
        )
        db.session.add(new_student)
        db.session.commit()

        sync_legacy_attendance(rollno, 0)

        flash(f"Student {sname} ({rollno}) Added Successfully!", "success")
        return redirect(url_for('admin', tab='student'))

    return redirect(url_for('admin', tab='student'))


@app.route("/edit/<string:id>", methods=['POST', 'GET'])
@login_required
def edit(id):
    post = db.session.get(Student, int(id))
    if not post:
        flash("Student not found", "warning")
        return redirect(url_for('admin', tab='manage'))

    if request.method == "POST":
        post.rollno = request.form.get('rollno')
        post.sname = request.form.get('sname')
        post.sem = int(request.form.get('sem', 3))
        post.gender = request.form.get('gender')
        post.branch = request.form.get('branch')
        post.email = request.form.get('email')
        post.number = request.form.get('num')
        post.address = request.form.get('address')
        db.session.commit()
        flash(f"Student details updated for {post.sname}", "success")
        return redirect(url_for('admin', tab='manage'))

    dept = Department.query.order_by(Department.branch).all()
    return render_template('edit.html', posts=post, dept=dept)


@app.route("/delete/<string:id>", methods=['POST', 'GET'])
@login_required
def delete(id):
    student = db.session.get(Student, int(id))
    if student:
        roll = student.rollno
        name = student.sname
        AttendanceRecord.query.filter_by(rollno=roll).delete()
        Attendence.query.filter_by(rollno=roll).delete()
        db.session.delete(student)
        db.session.commit()
        flash(f"Student {name} ({roll}) and Attendance Data Deleted Successfully", "danger")
    else:
        flash("Student not found", "warning")
    return redirect(url_for('admin', tab='manage'))


# ==========================================
# Attendance Routes: Take & View Attendance
# ==========================================

@app.route('/takeattendance', methods=['POST', 'GET'])
@app.route('/addattendance', methods=['POST', 'GET'])
@login_required
def takeattendance():
    departments = Department.query.order_by(Department.branch).all()
    today_str = date.today().strftime('%Y-%m-%d')

    selected_branch = request.args.get('branch', 'CU')
    selected_sem = request.args.get('sem', '3')
    selected_course = request.args.get('course', 'COA')
    selected_date = request.args.get('date', today_str)

    # Fetch available courses for the branch & sem
    courses_query = Course.query
    if selected_branch:
        courses_query = courses_query.filter_by(branch=selected_branch)
    if selected_sem:
        try:
            courses_query = courses_query.filter_by(sem=int(selected_sem))
        except ValueError:
            pass
    available_courses = courses_query.order_by(Course.course_code).all()

    # If selected_course not in available courses, default to first
    if available_courses and not any(c.course_code == selected_course for c in available_courses):
        selected_course = available_courses[0].course_code

    if request.method == "POST":
        form_date = request.form.get('date', today_str)
        form_course = request.form.get('course', selected_course)
        form_branch = request.form.get('branch', selected_branch)
        form_sem = request.form.get('sem', selected_sem)
        student_ids = request.form.getlist('student_ids')

        # Process batch attendance marking for specific subject
        marked_count = 0
        if student_ids:
            for s_id in student_ids:
                status = request.form.get(f"status_{s_id}", "Present")
                student = db.session.get(Student, int(s_id))
                if not student:
                    continue

                # Check if record for this rollno, course_code, and date already exists
                existing = AttendanceRecord.query.filter_by(
                    rollno=student.rollno,
                    course_code=form_course,
                    date=form_date
                ).first()

                if existing:
                    existing.status = status
                else:
                    new_rec = AttendanceRecord(
                        rollno=student.rollno,
                        course_code=form_course,
                        date=form_date,
                        status=status
                    )
                    db.session.add(new_rec)
                marked_count += 1

            db.session.commit()

            # Update cached percentage in Attendence table
            for s_id in student_ids:
                student = db.session.get(Student, int(s_id))
                if student:
                    stats = get_student_attendance_stats(student.rollno)
                    sync_legacy_attendance(student.rollno, stats['percentage'])

            flash(f"Attendance recorded for {marked_count} students in {form_course} on {form_date}!", "success")
            return redirect(url_for('takeattendance', branch=form_branch, sem=form_sem, course=form_course, date=form_date))

    # Fetch students matching filter
    query = Student.query
    if selected_branch:
        query = query.filter_by(branch=selected_branch)
    if selected_sem:
        try:
            query = query.filter_by(sem=int(selected_sem))
        except ValueError:
            pass

    students = query.order_by(Student.rollno).all()

    student_records = []
    for s in students:
        rec = AttendanceRecord.query.filter_by(
            rollno=s.rollno,
            course_code=selected_course,
            date=selected_date
        ).first()
        current_status = rec.status if rec else "Present"
        stats = get_student_attendance_stats(s.rollno, filter_course=selected_course)
        student_records.append({
            'student': s,
            'today_status': current_status,
            'stats': stats
        })

    return render_template(
        'take_attendance.html',
        students=student_records,
        departments=departments,
        available_courses=available_courses,
        selected_branch=selected_branch,
        selected_sem=selected_sem,
        selected_course=selected_course,
        selected_date=selected_date
    )


@app.route('/viewattendance', methods=['GET'])
@login_required
def viewattendance():
    departments = Department.query.order_by(Department.branch).all()
    selected_branch = request.args.get('branch', '')
    selected_sem = request.args.get('sem', '')
    selected_course = request.args.get('course', '')
    search_query = request.args.get('search', '').strip()
    selected_date = request.args.get('date', '')

    # Fetch courses for dropdown
    courses_query = Course.query
    if selected_branch:
        courses_query = courses_query.filter_by(branch=selected_branch)
    all_courses = courses_query.order_by(Course.course_code).all()

    query = Student.query
    if selected_branch:
        query = query.filter_by(branch=selected_branch)
    if selected_sem:
        try:
            query = query.filter_by(sem=int(selected_sem))
        except ValueError:
            pass
    if search_query:
        query = query.filter((Student.rollno.ilike(f"%{search_query}%")) | (Student.sname.ilike(f"%{search_query}%")))

    students = query.order_by(Student.rollno).all()

    summary_list = []
    shortage_count = 0
    total_percentage_sum = 0

    for s in students:
        stats = get_student_attendance_stats(s.rollno, filter_course=selected_course if selected_course else None)
        if stats['percentage'] < 75 and stats['total_classes'] > 0:
            shortage_count += 1
        total_percentage_sum += stats['percentage']

        summary_list.append({
            'student': s,
            'stats': stats
        })

    avg_percentage = round(total_percentage_sum / len(students), 1) if students else 0.0

    # Date-wise register lookup
    date_records = []
    if selected_date:
        recs_query = AttendanceRecord.query.filter_by(date=selected_date)
        if selected_course:
            recs_query = recs_query.filter_by(course_code=selected_course)
        recs = recs_query.all()
        for r in recs:
            st = Student.query.filter_by(rollno=r.rollno).first()
            date_records.append({
                'rollno': r.rollno,
                'name': st.sname if st else "N/A",
                'branch': st.branch if st else "N/A",
                'sem': st.sem if st else "N/A",
                'course': r.course_code or "General",
                'status': r.status
            })

    return render_template(
        'view_attendance.html',
        summary_list=summary_list,
        total_students=len(students),
        shortage_count=shortage_count,
        avg_percentage=avg_percentage,
        departments=departments,
        all_courses=all_courses,
        selected_branch=selected_branch,
        selected_sem=selected_sem,
        selected_course=selected_course,
        search_query=search_query,
        selected_date=selected_date,
        date_records=date_records
    )


@app.route('/attendance/student/<rollno>', methods=['GET'])
@login_required
def student_attendance_history(rollno):
    student = Student.query.filter_by(rollno=rollno).first_or_404()
    stats = get_student_attendance_stats(rollno)
    records = AttendanceRecord.query.filter_by(rollno=rollno).order_by(AttendanceRecord.date.desc()).all()
    return render_template(
        'student_attendance_detail.html',
        student=student,
        stats=stats,
        records=records
    )


@app.route('/search', methods=['POST', 'GET'])
@login_required
def search():
    results = []
    search_term = ''

    if request.method == "POST":
        search_term = request.form.get('query', request.form.get('roll', '')).strip()
        if search_term:
            matched_students = Student.query.filter(
                (Student.rollno.ilike(f"%{search_term}%")) |
                (Student.sname.ilike(f"%{search_term}%"))
            ).order_by(Student.rollno).all()

            for s in matched_students:
                stats = get_student_attendance_stats(s.rollno)
                results.append({
                    'bio': s,
                    'stats': stats
                })

            if not matched_students:
                flash(f"No student found matching: '{search_term}'", "warning")

    return render_template('search.html', results=results, search_term=search_term)


# ==========================================
# User Auth Routes
# ==========================================

@app.route('/signup', methods=['POST', 'GET'])
def signup():
    if request.method == "POST":
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()
        if user:
            flash("Email Already Exists. Please Login", "warning")
            return render_template('signup.html')

        newuser = User(username=username, email=email, password=password)
        db.session.add(newuser)
        db.session.commit()
        flash("Signup Successful! Please Login", "success")
        return redirect(url_for('login'))

    return render_template('signup.html')


@app.route('/login', methods=['POST', 'GET'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == "POST":
        login_input = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()

        user = User.query.filter((User.email == login_input) | (User.username == login_input)).first()

        if user and user.password == password:
            login_user(user)
            flash("Logged In Successfully", "primary")
            return redirect(url_for('index'))
        else:
            flash("Invalid Username/Email or Password", "danger")
            return render_template('login.html')

    return render_template('login.html')


@app.route('/logout')
def logout():
    logout_user()
    flash("Logged Out Successfully", "warning")
    return redirect(url_for('login'))


# Backward compatibility redirects for removed pages
@app.route('/about')
def about():
    return redirect(url_for('index'))


@app.route('/triggers')
def triggers():
    return redirect(url_for('admin'))


@app.route('/test')
def test():
    try:
        count = Test.query.count()
        student_count = Student.query.count()
        course_count = Course.query.count()
        return f"<h3>Database Connection: SUCCESS!</h3><p>Connected to MySQL database: <b>{DB_NAME}</b></p><p>Total Students: {student_count}</p><p>Total Courses: {course_count}</p>"
    except Exception as e:
        return f"<h3>Database Connection: FAILED</h3><p>Error: {e}</p>"


# ==========================================
# Run Application
# ==========================================

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)