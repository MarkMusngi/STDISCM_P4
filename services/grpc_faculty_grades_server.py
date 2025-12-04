import grpc
from concurrent import futures
import sys
sys.path.append('./generated')

import faculty_grades_pb2
import faculty_grades_pb2_grpc
import auth_pb2
import auth_pb2_grpc

import psycopg2
from psycopg2.extras import DictCursor
import os
import uuid
from datetime import datetime

# Configuration
POSTGRES_DB_GRADES = os.getenv('POSTGRES_DB_GRADES', 'student_portal_grades')
POSTGRES_DB_COURSES = os.getenv('POSTGRES_DB_COURSES', 'student_portal_courses')
POSTGRES_DB_AUTH = os.getenv('POSTGRES_DB_AUTH', 'student_portal_auth')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'postgres')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', '1234')
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = os.getenv('POSTGRES_PORT', '5432')

# Auth service gRPC address
AUTH_GRPC_HOST = os.getenv('AUTH_GRPC_HOST', 'localhost:50051')

def get_db_connection(db_name):
    try:
        conn = psycopg2.connect(
            dbname=db_name,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            host=POSTGRES_HOST,
            port=POSTGRES_PORT
        )
        return conn
    except psycopg2.OperationalError as e:
        print(f"Database connection failed: {e}")
        return None

def validate_token_with_auth_service(token):
    """Call Auth Service via gRPC to validate token"""
    try:
        with grpc.insecure_channel(AUTH_GRPC_HOST) as channel:
            stub = auth_pb2_grpc.AuthServiceStub(channel)
            response = stub.ValidateToken(auth_pb2.ValidateRequest(token=token))
            
            if response.status == "valid":
                return {
                    "valid": True,
                    "user_id": response.user_id,
                    "role": response.role,
                    "username": response.username
                }
            else:
                return {
                    "valid": False,
                    "message": response.message
                }
    except grpc.RpcError as e:
        print(f"gRPC error calling auth service: {e}")
        return {
            "valid": False,
            "message": "Auth service unavailable"
        }

class FacultyGradesServiceServicer(faculty_grades_pb2_grpc.FacultyGradesServiceServicer):
    
    def GetAllStudents(self, request, context):
        """Get all students in the system (Faculty only)"""
        token = request.token
        
        # Validate token
        auth_result = validate_token_with_auth_service(token)
        
        if not auth_result.get('valid'):
            return faculty_grades_pb2.StudentsResponse(
                status="error",
                message=f"Authentication failed: {auth_result.get('message', 'Invalid token')}",
                students=[]
            )
        
        user_role = auth_result['role']
        
        # Only faculty can access this
        if user_role != 'faculty':
            return faculty_grades_pb2.StudentsResponse(
                status="error",
                message=f"Access denied. Faculty only. Your role is '{user_role}'",
                students=[]
            )
        
        conn = get_db_connection(POSTGRES_DB_AUTH)
        if conn is None:
            return faculty_grades_pb2.StudentsResponse(
                status="error",
                message="Database connection error",
                students=[]
            )
        
        try:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute("""
                    SELECT public_id, username 
                    FROM users 
                    WHERE role = 'student'
                    ORDER BY username;
                """)
                rows = cur.fetchall()
                
                students = []
                for row in rows:
                    student = faculty_grades_pb2.StudentInfo(
                        student_id=str(row['public_id']),
                        username=row['username']
                    )
                    students.append(student)
                
                return faculty_grades_pb2.StudentsResponse(
                    status="success",
                    message="Students retrieved successfully",
                    students=students
                )
        
        except Exception as e:
            print(f"Error fetching students: {e}")
            return faculty_grades_pb2.StudentsResponse(
                status="error",
                message="Internal server error",
                students=[]
            )
        finally:
            conn.close()
    
    def GetStudentEnrollments(self, request, context):
        """Get all courses a student is enrolled in (Faculty only)"""
        token = request.token
        student_id = request.student_id
        
        # Validate token
        auth_result = validate_token_with_auth_service(token)
        
        if not auth_result.get('valid'):
            return faculty_grades_pb2.StudentEnrollmentsResponse(
                status="error",
                message="Authentication failed",
                student_id="",
                student_username="",
                enrollments=[]
            )
        
        user_role = auth_result['role']
        
        # Only faculty can access this
        if user_role != 'faculty':
            return faculty_grades_pb2.StudentEnrollmentsResponse(
                status="error",
                message=f"Access denied. Faculty only. Your role is '{user_role}'",
                student_id="",
                student_username="",
                enrollments=[]
            )
        
        # Get student username from auth DB
        auth_conn = get_db_connection(POSTGRES_DB_AUTH)
        if auth_conn is None:
            return faculty_grades_pb2.StudentEnrollmentsResponse(
                status="error",
                message="Database connection error",
                student_id="",
                student_username="",
                enrollments=[]
            )
        
        try:
            with auth_conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute("""
                    SELECT username FROM users WHERE public_id = %s;
                """, (student_id,))
                user_row = cur.fetchone()
                
                if not user_row:
                    return faculty_grades_pb2.StudentEnrollmentsResponse(
                        status="error",
                        message="Student not found",
                        student_id="",
                        student_username="",
                        enrollments=[]
                    )
                
                student_username = user_row['username']
        finally:
            auth_conn.close()
        
        # Get enrollments from courses DB
        courses_conn = get_db_connection(POSTGRES_DB_COURSES)
        if courses_conn is None:
            return faculty_grades_pb2.StudentEnrollmentsResponse(
                status="error",
                message="Courses database connection error",
                student_id=student_id,
                student_username=student_username,
                enrollments=[]
            )
        
        try:
            with courses_conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute("""
                    SELECT e.course_id, c.name, e.enrollment_date
                    FROM enrollments e
                    JOIN courses c ON e.course_id = c.course_id
                    WHERE e.student_public_id = %s
                    ORDER BY e.enrollment_date DESC;
                """, (student_id,))
                rows = cur.fetchall()
                
                enrollments = []
                for row in rows:
                    enrollment = faculty_grades_pb2.EnrollmentInfo(
                        course_id=row['course_id'],
                        course_name=row['name'],
                        enrollment_date=str(row['enrollment_date'])
                    )
                    enrollments.append(enrollment)
                
                return faculty_grades_pb2.StudentEnrollmentsResponse(
                    status="success",
                    message="Enrollments retrieved successfully",
                    student_id=student_id,
                    student_username=student_username,
                    enrollments=enrollments
                )
        
        except Exception as e:
            print(f"Error fetching enrollments: {e}")
            return faculty_grades_pb2.StudentEnrollmentsResponse(
                status="error",
                message="Internal server error",
                student_id=student_id,
                student_username=student_username,
                enrollments=[]
            )
        finally:
            courses_conn.close()
    
    def UploadStudentGrade(self, request, context):
        """Upload a grade for a specific student in a specific course (Faculty only)"""
        token = request.token
        student_id = request.student_id
        course_id = request.course_id
        grade = request.grade
        semester = request.semester
        remarks = request.remarks
        
        # Validate token
        auth_result = validate_token_with_auth_service(token)
        
        if not auth_result.get('valid'):
            return faculty_grades_pb2.UploadGradeResponse(
                status="error",
                message="Authentication failed",
                grade_id=""
            )
        
        faculty_id = auth_result['user_id']
        user_role = auth_result['role']
        
        # Only faculty can upload grades
        if user_role != 'faculty':
            return faculty_grades_pb2.UploadGradeResponse(
                status="error",
                message=f"Only faculty can upload grades. Your role is '{user_role}'",
                grade_id=""
            )
        
        # Verify student is enrolled in the course
        courses_conn = get_db_connection(POSTGRES_DB_COURSES)
        if courses_conn is None:
            return faculty_grades_pb2.UploadGradeResponse(
                status="error",
                message="Database connection error",
                grade_id=""
            )
        
        try:
            with courses_conn.cursor() as cur:
                cur.execute("""
                    SELECT 1 FROM enrollments 
                    WHERE student_public_id = %s AND course_id = %s;
                """, (student_id, course_id))
                
                if not cur.fetchone():
                    return faculty_grades_pb2.UploadGradeResponse(
                        status="error",
                        message="Student is not enrolled in this course",
                        grade_id=""
                    )
        finally:
            courses_conn.close()
        
        # Upload grade to grades database
        grades_conn = get_db_connection(POSTGRES_DB_GRADES)
        if grades_conn is None:
            return faculty_grades_pb2.UploadGradeResponse(
                status="error",
                message="Grades database connection error",
                grade_id=""
            )
        
        try:
            grade_id = str(uuid.uuid4())
            
            with grades_conn.cursor() as cur:
                # Check if grade already exists for this student and course
                cur.execute("""
                    SELECT grade_id FROM grades 
                    WHERE student_public_id = %s AND course_id = %s;
                """, (student_id, course_id))
                
                existing_grade = cur.fetchone()
                
                if existing_grade:
                    # Update existing grade
                    cur.execute("""
                        UPDATE grades 
                        SET grade = %s, semester = %s, remarks = %s, 
                            uploaded_by_faculty_id = %s, date_posted = CURRENT_TIMESTAMP
                        WHERE student_public_id = %s AND course_id = %s
                        RETURNING grade_id;
                    """, (grade, semester, remarks, faculty_id, student_id, course_id))
                    grade_id = str(cur.fetchone()[0])
                    message = f"Grade updated to {grade} for course {course_id}"
                else:
                    # Insert new grade
                    cur.execute("""
                        INSERT INTO grades (grade_id, student_public_id, course_id, 
                                          grade, semester, remarks, uploaded_by_faculty_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s);
                    """, (grade_id, student_id, course_id, grade, semester, remarks, faculty_id))
                    message = f"Grade {grade} uploaded successfully for course {course_id}"
            
            grades_conn.commit()
            print(f"Faculty {faculty_id} uploaded grade {grade} for student {student_id} in {course_id}")
            
            return faculty_grades_pb2.UploadGradeResponse(
                status="success",
                message=message,
                grade_id=grade_id
            )
        
        except Exception as e:
            grades_conn.rollback()
            print(f"Error uploading grade: {e}")
            return faculty_grades_pb2.UploadGradeResponse(
                status="error",
                message="Failed to upload grade",
                grade_id=""
            )
        finally:
            grades_conn.close()

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    faculty_grades_pb2_grpc.add_FacultyGradesServiceServicer_to_server(
        FacultyGradesServiceServicer(), server
    )
    server.add_insecure_port('[::]:50055')
    print("=" * 60)
    print("gRPC Faculty Grades Service (Node 5)")
    print("Port: 50055")
    print("=" * 60)
    print("\nRPC Methods Available:")
    print("  - GetAllStudents")
    print("  - GetStudentEnrollments")
    print("  - UploadStudentGrade")
    print("\nAccess Control: Faculty Only")
    print("=" * 60)
    print("\nServer starting on port 50055...")
    server.start()
    server.wait_for_termination()

if __name__ == '__main__':
    serve()