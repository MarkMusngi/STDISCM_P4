import grpc
from concurrent import futures
import sys
sys.path.append('./generated')

import grades_pb2
import grades_pb2_grpc
import auth_pb2
import auth_pb2_grpc

import psycopg2
from psycopg2.extras import DictCursor
import os
import uuid
from datetime import datetime

# Configuration
POSTGRES_DB = os.getenv('POSTGRES_DB', 'student_portal_grades')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'postgres')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', '1234')
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = os.getenv('POSTGRES_PORT', '5432')

# Auth service gRPC address
AUTH_GRPC_HOST = os.getenv('AUTH_GRPC_HOST', 'localhost:50051')

def get_db_connection():
    try:
        conn = psycopg2.connect(
            dbname=POSTGRES_DB,
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

def init_db():
    """Initialize grades database"""
    conn = get_db_connection()
    if conn is None:
        print("Cannot initialize DB without a connection.")
        return

    try:
        with conn.cursor() as cur:
            # Create grades table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS grades (
                    grade_id UUID PRIMARY KEY,
                    student_public_id UUID NOT NULL,
                    course_id VARCHAR(20) NOT NULL,
                    grade VARCHAR(5) NOT NULL,
                    semester VARCHAR(20) NOT NULL,
                    date_posted TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    remarks TEXT,
                    uploaded_by_faculty_id UUID NOT NULL
                );
            """)
            
            # Create index for faster lookups
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_student_grades 
                ON grades(student_public_id);
            """)
            
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_course_grades 
                ON grades(course_id);
            """)
            
            # Insert sample grades if table is empty
            cur.execute("SELECT COUNT(*) FROM grades;")
            if cur.fetchone()[0] == 0:
                # You'll need actual student UUIDs from your auth database
                # For now, using placeholder UUIDs
                sample_grades = [
                    (str(uuid.uuid4()), '00000000-0000-0000-0000-000000000001', 
                     'CS101', 'A', 'Fall 2023', 'Excellent work', 
                     '00000000-0000-0000-0000-000000000002'),
                    (str(uuid.uuid4()), '00000000-0000-0000-0000-000000000001', 
                     'MATH203', 'B+', 'Fall 2023', 'Good performance', 
                     '00000000-0000-0000-0000-000000000002'),
                    (str(uuid.uuid4()), '00000000-0000-0000-0000-000000000001', 
                     'ENG100', 'A-', 'Spring 2024', 'Strong essays', 
                     '00000000-0000-0000-0000-000000000002'),
                ]
                cur.executemany("""
                    INSERT INTO grades (grade_id, student_public_id, course_id, 
                                      grade, semester, remarks, uploaded_by_faculty_id) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s);
                """, sample_grades)
                print("Sample grades inserted.")
        
        conn.commit()
        print("Grades database initialized successfully.")
    except Exception as e:
        print(f"Error initializing database: {e}")
        conn.rollback()
    finally:
        conn.close()

class GradesServiceServicer(grades_pb2_grpc.GradesServiceServicer):
    
    def GetEnrolledCoursesWithGrades(self, request, context):
        """Get all enrolled courses with their grades (or 'Not Released' status)"""
        token = request.token
        
        # Validate token
        auth_result = validate_token_with_auth_service(token)
        
        if not auth_result.get('valid'):
            return grades_pb2.EnrolledCoursesWithGradesResponse(
                status="error",
                message=f"Authentication failed: {auth_result.get('message', 'Invalid token')}",
                courses=[],
                student_name=""
            )
        
        user_id = auth_result['user_id']
        username = auth_result['username']
        user_role = auth_result['role']
        
        # Students can only view their own grades
        if user_role != 'student':
            return grades_pb2.EnrolledCoursesWithGradesResponse(
                status="error",
                message=f"Only students can view grades. Your role is '{user_role}'",
                courses=[],
                student_name=""
            )
        
        # Need to connect to BOTH databases: courses and grades
        # First, get enrollments from courses database
        courses_conn = psycopg2.connect(
            dbname='student_portal_courses',
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            host=POSTGRES_HOST,
            port=POSTGRES_PORT
        )
        
        grades_conn = get_db_connection()
        
        if not courses_conn or not grades_conn:
            return grades_pb2.EnrolledCoursesWithGradesResponse(
                status="error",
                message="Database connection error",
                courses=[],
                student_name=""
            )
        
        try:
            course_grades_list = []
            
            # Get enrolled courses
            with courses_conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute("""
                    SELECT e.course_id, c.name, e.enrollment_date
                    FROM enrollments e
                    JOIN courses c ON e.course_id = c.course_id
                    WHERE e.student_public_id = %s
                    ORDER BY e.enrollment_date DESC;
                """, (user_id,))
                enrollments = cur.fetchall()
            
            # For each enrollment, check if grade exists
            with grades_conn.cursor(cursor_factory=DictCursor) as cur:
                for enrollment in enrollments:
                    course_id = enrollment['course_id']
                    
                    # Check if grade exists for this course and student
                    cur.execute("""
                        SELECT grade, semester, date_posted, remarks
                        FROM grades
                        WHERE student_public_id = %s AND course_id = %s;
                    """, (user_id, course_id))
                    
                    grade_row = cur.fetchone()
                    
                    if grade_row:
                        # Grade has been released
                        course_grade = grades_pb2.CourseGradeInfo(
                            course_id=course_id,
                            course_name=enrollment['name'],
                            enrollment_date=str(enrollment['enrollment_date']),
                            grade_released=True,
                            grade=grade_row['grade'],
                            semester=grade_row['semester'],
                            date_posted=str(grade_row['date_posted']),
                            remarks=grade_row['remarks'] or ""
                        )
                    else:
                        # Grade not yet released
                        course_grade = grades_pb2.CourseGradeInfo(
                            course_id=course_id,
                            course_name=enrollment['name'],
                            enrollment_date=str(enrollment['enrollment_date']),
                            grade_released=False,
                            grade="",
                            semester="",
                            date_posted="",
                            remarks=""
                        )
                    
                    course_grades_list.append(course_grade)
            
            return grades_pb2.EnrolledCoursesWithGradesResponse(
                status="success",
                message="Enrolled courses with grades retrieved",
                courses=course_grades_list,
                student_name=username
            )
        
        except Exception as e:
            print(f"Error fetching enrolled courses with grades: {e}")
            return grades_pb2.EnrolledCoursesWithGradesResponse(
                status="error",
                message=f"Internal server error: {str(e)}",
                courses=[],
                student_name=""
            )
        finally:
            if courses_conn:
                courses_conn.close()
            if grades_conn:
                grades_conn.close()
    
    def GetStudentGrades(self, request, context):
        """Get all grades for a student"""
        token = request.token
        
        # Validate token
        auth_result = validate_token_with_auth_service(token)
        
        if not auth_result.get('valid'):
            return grades_pb2.GradesResponse(
                status="error",
                message=f"Authentication failed: {auth_result.get('message', 'Invalid token')}",
                grades=[],
                student_name=""
            )
        
        user_id = auth_result['user_id']
        username = auth_result['username']
        user_role = auth_result['role']
        
        # Students can only view their own grades
        if user_role != 'student':
            return grades_pb2.GradesResponse(
                status="error",
                message=f"Only students can view grades. Your role is '{user_role}'",
                grades=[],
                student_name=""
            )
        
        conn = get_db_connection()
        if conn is None:
            return grades_pb2.GradesResponse(
                status="error",
                message="Database connection error",
                grades=[],
                student_name=""
            )
        
        try:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                # Get grades with course names from course database
                # Note: This assumes courses table exists. You might need to join
                # across databases or store course names in grades table
                cur.execute("""
                    SELECT 
                        g.grade_id,
                        g.course_id,
                        g.course_id as course_name,
                        g.grade,
                        g.semester,
                        g.date_posted,
                        g.remarks
                    FROM grades g
                    WHERE g.student_public_id = %s
                    ORDER BY g.date_posted DESC;
                """, (user_id,))
                
                rows = cur.fetchall()
                
                grades = []
                for row in rows:
                    grade_info = grades_pb2.GradeInfo(
                        grade_id=str(row['grade_id']),
                        course_id=row['course_id'],
                        course_name=row['course_name'],
                        grade=row['grade'],
                        semester=row['semester'],
                        date_posted=str(row['date_posted']),
                        remarks=row['remarks'] or ""
                    )
                    grades.append(grade_info)
                
                return grades_pb2.GradesResponse(
                    status="success",
                    message="Grades retrieved successfully",
                    grades=grades,
                    student_name=username
                )
        
        except Exception as e:
            print(f"Error fetching grades: {e}")
            return grades_pb2.GradesResponse(
                status="error",
                message="Internal server error",
                grades=[],
                student_name=""
            )
        finally:
            conn.close()
    
    def UploadGrade(self, request, context):
        """Faculty uploads a grade for a student"""
        token = request.token
        student_id = request.student_id
        course_id = request.course_id
        grade = request.grade
        semester = request.semester
        remarks = request.remarks
        
        # Validate token
        auth_result = validate_token_with_auth_service(token)
        
        if not auth_result.get('valid'):
            return grades_pb2.UploadGradeResponse(
                status="error",
                message="Authentication failed",
                grade_id=""
            )
        
        faculty_id = auth_result['user_id']
        user_role = auth_result['role']
        
        # Only faculty can upload grades
        if user_role != 'faculty':
            return grades_pb2.UploadGradeResponse(
                status="error",
                message=f"Only faculty can upload grades. Your role is '{user_role}'",
                grade_id=""
            )
        
        conn = get_db_connection()
        if conn is None:
            return grades_pb2.UploadGradeResponse(
                status="error",
                message="Database connection error",
                grade_id=""
            )
        
        try:
            grade_id = str(uuid.uuid4())
            
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO grades (grade_id, student_public_id, course_id, 
                                      grade, semester, remarks, uploaded_by_faculty_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s);
                """, (grade_id, student_id, course_id, grade, semester, remarks, faculty_id))
            
            conn.commit()
            print(f"Grade uploaded: {grade} for student {student_id} in {course_id}")
            
            return grades_pb2.UploadGradeResponse(
                status="success",
                message=f"Grade {grade} uploaded successfully for {course_id}",
                grade_id=grade_id
            )
        
        except Exception as e:
            conn.rollback()
            print(f"Error uploading grade: {e}")
            return grades_pb2.UploadGradeResponse(
                status="error",
                message="Failed to upload grade",
                grade_id=""
            )
        finally:
            conn.close()
    
    def GetCourseGrades(self, request, context):
        """Faculty views all grades for a specific course"""
        token = request.token
        course_id = request.course_id
        
        # Validate token
        auth_result = validate_token_with_auth_service(token)
        
        if not auth_result.get('valid'):
            return grades_pb2.CourseGradesResponse(
                status="error",
                message="Authentication failed",
                course_id="",
                course_name="",
                student_grades=[]
            )
        
        user_role = auth_result['role']
        
        # Only faculty can view course grades
        if user_role != 'faculty':
            return grades_pb2.CourseGradesResponse(
                status="error",
                message=f"Only faculty can view course grades. Your role is '{user_role}'",
                course_id="",
                course_name="",
                student_grades=[]
            )
        
        conn = get_db_connection()
        if conn is None:
            return grades_pb2.CourseGradesResponse(
                status="error",
                message="Database connection error",
                course_id="",
                course_name="",
                student_grades=[]
            )
        
        try:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute("""
                    SELECT 
                        student_public_id,
                        grade,
                        date_posted
                    FROM grades
                    WHERE course_id = %s
                    ORDER BY date_posted DESC;
                """, (course_id,))
                
                rows = cur.fetchall()
                
                student_grades = []
                for row in rows:
                    student_grade = grades_pb2.StudentGradeInfo(
                        student_id=str(row['student_public_id']),
                        student_name="Student",  # Would need to fetch from auth DB
                        grade=row['grade'],
                        date_posted=str(row['date_posted'])
                    )
                    student_grades.append(student_grade)
                
                return grades_pb2.CourseGradesResponse(
                    status="success",
                    message="Course grades retrieved",
                    course_id=course_id,
                    course_name=course_id,  # Would fetch actual name
                    student_grades=student_grades
                )
        
        except Exception as e:
            print(f"Error fetching course grades: {e}")
            return grades_pb2.CourseGradesResponse(
                status="error",
                message="Internal server error",
                course_id="",
                course_name="",
                student_grades=[]
            )
        finally:
            conn.close()

def serve():
    init_db()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    grades_pb2_grpc.add_GradesServiceServicer_to_server(GradesServiceServicer(), server)
    server.add_insecure_port('[::]:50054')
    print("gRPC Grades Service starting on port 50054...")
    server.start()
    server.wait_for_termination()

if __name__ == '__main__':
    serve()