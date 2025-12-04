from flask import Flask, jsonify, request
from flask_cors import CORS
import grpc
import sys
sys.path.append('./generated')

import auth_pb2
import auth_pb2_grpc
import course_pb2
import course_pb2_grpc
import enrollment_pb2
import enrollment_pb2_grpc
import grades_pb2
import grades_pb2_grpc
import faculty_grades_pb2
import faculty_grades_pb2_grpc

app = Flask(__name__)
CORS(app)

# gRPC service addresses
AUTH_GRPC = 'localhost:50051'
COURSE_GRPC = 'localhost:50052'
ENROLLMENT_GRPC = 'localhost:50053'
GRADES_GRPC = 'localhost:50054'
FACULTY_GRADES_GRPC = 'localhost:50055' 

# ============= AUTH ENDPOINTS =============

@app.route('/api/v1/auth/register', methods=['POST'])
def register():
    data = request.json
    try:
        with grpc.insecure_channel(AUTH_GRPC) as channel:
            stub = auth_pb2_grpc.AuthServiceStub(channel)
            response = stub.Register(auth_pb2.RegisterRequest(
                username=data.get('username', ''),
                password=data.get('password', ''),
                role=data.get('role', 'student')
            ))
            
            if response.status == "success":
                return jsonify({
                    "status": response.status,
                    "message": response.message,
                    "token": response.token,
                    "user_id": response.user_id,
                    "role": response.role
                }), 201
            else:
                return jsonify({
                    "status": response.status,
                    "message": response.message
                }), 400 if response.status == "error" else 500
    except grpc.RpcError as e:
        return jsonify({"status": "error", "message": "Auth service unavailable"}), 503

@app.route('/api/v1/auth/login', methods=['POST'])
def login():
    data = request.json
    try:
        with grpc.insecure_channel(AUTH_GRPC) as channel:
            stub = auth_pb2_grpc.AuthServiceStub(channel)
            response = stub.Login(auth_pb2.LoginRequest(
                username=data.get('username', ''),
                password=data.get('password', '')
            ))
            
            if response.status == "success":
                return jsonify({
                    "status": response.status,
                    "message": response.message,
                    "token": response.token,
                    "user_id": response.user_id,
                    "role": response.role
                }), 200
            else:
                return jsonify({
                    "status": response.status,
                    "message": response.message
                }), 401
    except grpc.RpcError as e:
        return jsonify({"status": "error", "message": "Auth service unavailable"}), 503

@app.route('/api/v1/auth/validate', methods=['POST'])
def validate():
    data = request.json
    token = data.get('token', '')
    
    try:
        with grpc.insecure_channel(AUTH_GRPC) as channel:
            stub = auth_pb2_grpc.AuthServiceStub(channel)
            response = stub.ValidateToken(auth_pb2.ValidateRequest(token=token))
            
            if response.status == "valid":
                return jsonify({
                    "status": response.status,
                    "user_id": response.user_id,
                    "role": response.role,
                    "username": response.username
                }), 200
            else:
                return jsonify({
                    "status": response.status,
                    "message": response.message
                }), 401
    except grpc.RpcError as e:
        return jsonify({"status": "error", "message": "Auth service unavailable"}), 503

# ============= COURSE ENDPOINTS =============

@app.route('/api/v1/courses', methods=['GET'])
def get_courses():
    try:
        with grpc.insecure_channel(COURSE_GRPC) as channel:
            stub = course_pb2_grpc.CourseServiceStub(channel)
            response = stub.GetCourses(course_pb2.GetCoursesRequest())
            
            if response.status == "success":
                courses = {}
                for course in response.courses:
                    courses[course.course_id] = {
                        "name": course.name,
                        "capacity": course.capacity,
                        "enrolled": course.enrolled,
                        "open": course.is_open
                    }
                return jsonify(courses), 200
            else:
                return jsonify({"status": response.status, "message": response.message}), 500
    except grpc.RpcError as e:
        return jsonify({"status": "error", "message": "Course service unavailable"}), 503

@app.route('/api/v1/courses/<course_id>', methods=['GET'])
def get_course_details(course_id):
    try:
        with grpc.insecure_channel(COURSE_GRPC) as channel:
            stub = course_pb2_grpc.CourseServiceStub(channel)
            response = stub.GetCourseDetails(course_pb2.CourseRequest(course_id=course_id))
            
            if response.status == "success" and response.course:
                return jsonify({
                    "status": "success",
                    "course": {
                        "course_id": response.course.course_id,
                        "name": response.course.name,
                        "capacity": response.course.capacity,
                        "enrolled": response.course.enrolled,
                        "open": response.course.is_open
                    }
                }), 200
            else:
                return jsonify({"status": response.status, "message": response.message}), 404
    except grpc.RpcError as e:
        return jsonify({"status": "error", "message": "Course service unavailable"}), 503

# ============= ENROLLMENT ENDPOINTS =============

@app.route('/api/v1/enroll/course/<course_id>', methods=['POST'])
def enroll_in_course(course_id):
    token = request.headers.get('Authorization')
    if token and token.startswith('Bearer '):
        token = token[7:]
    
    if not token:
        return jsonify({"status": "error", "message": "Token missing"}), 401
    
    try:
        with grpc.insecure_channel(ENROLLMENT_GRPC) as channel:
            stub = enrollment_pb2_grpc.EnrollmentServiceStub(channel)
            response = stub.EnrollInCourse(enrollment_pb2.EnrollRequest(
                token=token,
                course_id=course_id
            ))
            
            if response.status == "success":
                return jsonify({"status": response.status, "message": response.message}), 200
            elif response.status == "rejected":
                return jsonify({"status": response.status, "message": response.message}), 403
            else:
                return jsonify({"status": response.status, "message": response.message}), 400
    except grpc.RpcError as e:
        return jsonify({"status": "error", "message": "Enrollment service unavailable"}), 503

@app.route('/api/v1/enrollments', methods=['GET'])
def get_enrollments():
    token = request.headers.get('Authorization')
    if token and token.startswith('Bearer '):
        token = token[7:]
    
    if not token:
        return jsonify({"status": "error", "message": "Token missing"}), 401
    
    try:
        with grpc.insecure_channel(ENROLLMENT_GRPC) as channel:
            stub = enrollment_pb2_grpc.EnrollmentServiceStub(channel)
            response = stub.GetStudentEnrollments(enrollment_pb2.StudentRequest(token=token))
            
            if response.status == "success":
                enrollments = []
                for enroll in response.enrollments:
                    enrollments.append({
                        "course_id": enroll.course_id,
                        "course_name": enroll.course_name,
                        "enrollment_date": enroll.enrollment_date
                    })
                return jsonify({
                    "status": "success",
                    "enrollments": enrollments
                }), 200
            else:
                return jsonify({"status": response.status, "message": response.message}), 400
    except grpc.RpcError as e:
        return jsonify({"status": "error", "message": "Enrollment service unavailable"}), 503

# ============= GRADES ENDPOINTS (Student View) =============

@app.route('/api/v1/grades/enrolled-with-grades', methods=['GET'])
def get_enrolled_courses_with_grades():
    """Student views their enrolled courses with grades"""
    token = request.headers.get('Authorization')
    if token and token.startswith('Bearer '):
        token = token[7:]
    
    if not token:
        return jsonify({"status": "error", "message": "Token missing"}), 401
    
    try:
        with grpc.insecure_channel(GRADES_GRPC) as channel:
            stub = grades_pb2_grpc.GradesServiceStub(channel)
            response = stub.GetEnrolledCoursesWithGrades(
                grades_pb2.EnrolledCoursesWithGradesRequest(token=token)
            )
            
            if response.status == "success":
                courses = []
                for course in response.courses:
                    courses.append({
                        "course_id": course.course_id,
                        "course_name": course.course_name,
                        "enrollment_date": course.enrollment_date,
                        "grade_released": course.grade_released,
                        "grade": course.grade if course.grade_released else "Not Released",
                        "semester": course.semester,
                        "date_posted": course.date_posted,
                        "remarks": course.remarks
                    })
                return jsonify({
                    "status": "success",
                    "student_name": response.student_name,
                    "courses": courses
                }), 200
            else:
                return jsonify({"status": response.status, "message": response.message}), 400
    except grpc.RpcError as e:
        return jsonify({"status": "error", "message": "Grades service unavailable"}), 503

@app.route('/api/v1/grades/my-grades', methods=['GET'])
def get_my_grades():
    """Student views their own grades"""
    token = request.headers.get('Authorization')
    if token and token.startswith('Bearer '):
        token = token[7:]
    
    if not token:
        return jsonify({"status": "error", "message": "Token missing"}), 401
    
    try:
        with grpc.insecure_channel(GRADES_GRPC) as channel:
            stub = grades_pb2_grpc.GradesServiceStub(channel)
            response = stub.GetStudentGrades(grades_pb2.GradesRequest(token=token))
            
            if response.status == "success":
                grades = []
                for grade in response.grades:
                    grades.append({
                        "grade_id": grade.grade_id,
                        "course_id": grade.course_id,
                        "course_name": grade.course_name,
                        "grade": grade.grade,
                        "semester": grade.semester,
                        "date_posted": grade.date_posted,
                        "remarks": grade.remarks
                    })
                return jsonify({
                    "status": "success",
                    "student_name": response.student_name,
                    "grades": grades
                }), 200
            else:
                return jsonify({"status": response.status, "message": response.message}), 400
    except grpc.RpcError as e:
        return jsonify({"status": "error", "message": "Grades service unavailable"}), 503

@app.route('/api/v1/grades/upload', methods=['POST'])
def upload_grade():
    """Faculty uploads a grade (Legacy endpoint - redirects to faculty service)"""
    token = request.headers.get('Authorization')
    if token and token.startswith('Bearer '):
        token = token[7:]
    
    if not token:
        return jsonify({"status": "error", "message": "Token missing"}), 401
    
    data = request.json
    
    try:
        with grpc.insecure_channel(GRADES_GRPC) as channel:
            stub = grades_pb2_grpc.GradesServiceStub(channel)
            response = stub.UploadGrade(grades_pb2.UploadGradeRequest(
                token=token,
                student_id=data.get('student_id', ''),
                course_id=data.get('course_id', ''),
                grade=data.get('grade', ''),
                semester=data.get('semester', ''),
                remarks=data.get('remarks', '')
            ))
            
            if response.status == "success":
                return jsonify({
                    "status": response.status,
                    "message": response.message,
                    "grade_id": response.grade_id
                }), 201
            else:
                return jsonify({"status": response.status, "message": response.message}), 400
    except grpc.RpcError as e:
        return jsonify({"status": "error", "message": "Grades service unavailable"}), 503

@app.route('/api/v1/grades/course/<course_id>', methods=['GET'])
def get_course_grades(course_id):
    """Faculty views all grades for a course"""
    token = request.headers.get('Authorization')
    if token and token.startswith('Bearer '):
        token = token[7:]
    
    if not token:
        return jsonify({"status": "error", "message": "Token missing"}), 401
    
    try:
        with grpc.insecure_channel(GRADES_GRPC) as channel:
            stub = grades_pb2_grpc.GradesServiceStub(channel)
            response = stub.GetCourseGrades(grades_pb2.CourseGradesRequest(
                token=token,
                course_id=course_id
            ))
            
            if response.status == "success":
                student_grades = []
                for sg in response.student_grades:
                    student_grades.append({
                        "student_id": sg.student_id,
                        "student_name": sg.student_name,
                        "grade": sg.grade,
                        "date_posted": sg.date_posted
                    })
                return jsonify({
                    "status": "success",
                    "course_id": response.course_id,
                    "course_name": response.course_name,
                    "student_grades": student_grades
                }), 200
            else:
                return jsonify({"status": response.status, "message": response.message}), 400
    except grpc.RpcError as e:
        return jsonify({"status": "error", "message": "Grades service unavailable"}), 503

# ============= FACULTY GRADES ENDPOINTS (NEW - Node 5: Port 50055) =============

@app.route('/api/v1/faculty/students', methods=['GET'])
def get_all_students():
    """Faculty gets list of all students in the system"""
    token = request.headers.get('Authorization')
    if token and token.startswith('Bearer '):
        token = token[7:]
    
    if not token:
        return jsonify({"status": "error", "message": "Token missing"}), 401
    
    try:
        with grpc.insecure_channel(FACULTY_GRADES_GRPC) as channel:
            stub = faculty_grades_pb2_grpc.FacultyGradesServiceStub(channel)
            response = stub.GetAllStudents(faculty_grades_pb2.GetStudentsRequest(token=token))
            
            if response.status == "success":
                students = []
                for student in response.students:
                    students.append({
                        "student_id": student.student_id,
                        "username": student.username
                    })
                return jsonify({
                    "status": "success",
                    "message": response.message,
                    "students": students
                }), 200
            else:
                return jsonify({"status": response.status, "message": response.message}), 400
    except grpc.RpcError as e:
        return jsonify({"status": "error", "message": "Faculty Grades service unavailable"}), 503

@app.route('/api/v1/faculty/students/<student_id>/enrollments', methods=['GET'])
def get_student_enrollments_by_faculty(student_id):
    """Faculty gets all courses a specific student is enrolled in"""
    token = request.headers.get('Authorization')
    if token and token.startswith('Bearer '):
        token = token[7:]
    
    if not token:
        return jsonify({"status": "error", "message": "Token missing"}), 401
    
    try:
        with grpc.insecure_channel(FACULTY_GRADES_GRPC) as channel:
            stub = faculty_grades_pb2_grpc.FacultyGradesServiceStub(channel)
            response = stub.GetStudentEnrollments(
                faculty_grades_pb2.GetEnrollmentsRequest(token=token, student_id=student_id)
            )
            
            if response.status == "success":
                enrollments = []
                for enrollment in response.enrollments:
                    enrollments.append({
                        "course_id": enrollment.course_id,
                        "course_name": enrollment.course_name,
                        "enrollment_date": enrollment.enrollment_date
                    })
                return jsonify({
                    "status": "success",
                    "message": response.message,
                    "student_id": response.student_id,
                    "student_username": response.student_username,
                    "enrollments": enrollments
                }), 200
            else:
                return jsonify({"status": response.status, "message": response.message}), 400
    except grpc.RpcError as e:
        return jsonify({"status": "error", "message": "Faculty Grades service unavailable"}), 503

@app.route('/api/v1/faculty/grades/upload', methods=['POST'])
def faculty_upload_student_grade():
    """Faculty uploads a grade for a specific student (NEW dedicated endpoint)"""
    token = request.headers.get('Authorization')
    if token and token.startswith('Bearer '):
        token = token[7:]
    
    if not token:
        return jsonify({"status": "error", "message": "Token missing"}), 401
    
    data = request.json
    
    try:
        with grpc.insecure_channel(FACULTY_GRADES_GRPC) as channel:
            stub = faculty_grades_pb2_grpc.FacultyGradesServiceStub(channel)
            response = stub.UploadStudentGrade(faculty_grades_pb2.UploadGradeRequest(
                token=token,
                student_id=data.get('student_id', ''),
                course_id=data.get('course_id', ''),
                grade=data.get('grade', ''),
                semester=data.get('semester', 'Fall 2024'),
                remarks=data.get('remarks', '')
            ))
            
            if response.status == "success":
                return jsonify({
                    "status": response.status,
                    "message": response.message,
                    "grade_id": response.grade_id
                }), 201
            else:
                return jsonify({"status": response.status, "message": response.message}), 400
    except grpc.RpcError as e:
        return jsonify({"status": "error", "message": "Faculty Grades service unavailable (Port 50055)"}), 503

# ============= HEALTH CHECK =============

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint to verify REST gateway is running"""
    services_status = {
        "gateway": "running",
        "services": {
            "auth": AUTH_GRPC,
            "courses": COURSE_GRPC,
            "enrollment": ENROLLMENT_GRPC,
            "grades": GRADES_GRPC,
            "faculty_grades": FACULTY_GRADES_GRPC
        }
    }
    return jsonify(services_status), 200

if __name__ == '__main__':
    print("=" * 70)
    print("REST Gateway starting on port 5001...")
    print("=" * 70)
    print("Translating REST calls to gRPC services:")
    print(f"  - Auth Service:          {AUTH_GRPC}")
    print(f"  - Course Service:        {COURSE_GRPC}")
    print(f"  - Enrollment Service:    {ENROLLMENT_GRPC}")
    print(f"  - Grades Service:        {GRADES_GRPC}")
    print(f"  - Faculty Grades Service: {FACULTY_GRADES_GRPC} (NEW)")
    print("=" * 70)
    print("\nNew Faculty Endpoints:")
    print("  GET  /api/v1/faculty/students")
    print("  GET  /api/v1/faculty/students/<id>/enrollments")
    print("  POST /api/v1/faculty/grades/upload")
    print("=" * 70)
    app.run(host='0.0.0.0', port=5001, debug=True)