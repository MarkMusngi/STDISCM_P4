import grpc
from concurrent import futures
import sys
sys.path.append('./generated')

import enrollment_pb2
import enrollment_pb2_grpc

import psycopg2
from psycopg2.extras import DictCursor
import os
import jwt
from datetime import datetime, timezone

DB_NAME = os.getenv('POSTGRES_DB', 'student_portal_courses')
DB_USER = os.getenv('POSTGRES_USER', 'postgres')
DB_PASSWORD = os.getenv('POSTGRES_PASSWORD', '1234')
DB_HOST = os.getenv('POSTGRES_HOST', 'localhost')
DB_PORT = os.getenv('POSTGRES_PORT', '5432')

# JWT Configuration (must match auth server)
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'super_secret_auth_key_12345')
JWT_ALGORITHM = "HS256"

def get_db_connection():
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )
        return conn
    except psycopg2.Error as e:
        print(f"Database connection error: {e}")
        return None

def validate_token_locally(token):
    """Validate JWT token locally without calling auth service"""
    if not token:
        return {
            "valid": False,
            "message": "Token missing"
        }
    
    try:
        # Decode and verify the JWT token
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        
        # Check if token has expired (jwt.decode already does this, but being explicit)
        exp_timestamp = payload.get('exp')
        if exp_timestamp:
            exp_datetime = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
            if datetime.now(timezone.utc) > exp_datetime:
                return {
                    "valid": False,
                    "message": "Token expired"
                }
        
        return {
            "valid": True,
            "user_id": payload.get('public_id'),
            "role": payload.get('role'),
            "username": payload.get('username')
        }
    
    except jwt.ExpiredSignatureError:
        print(f"✗ Token validation failed: Token expired")
        return {
            "valid": False,
            "message": "Token expired"
        }
    except jwt.InvalidTokenError as e:
        print(f"✗ Token validation failed: Invalid token - {e}")
        return {
            "valid": False,
            "message": "Invalid token"
        }
    except Exception as e:
        print(f"✗ Token validation error: {e}")
        return {
            "valid": False,
            "message": "Token validation error"
        }

class EnrollmentServiceServicer(enrollment_pb2_grpc.EnrollmentServiceServicer):
    
    def EnrollInCourse(self, request, context):
        token = request.token
        course_id = request.course_id

        # Use local JWT validation instead of calling auth service
        auth_result = validate_token_locally(token)
        
        if not auth_result.get('valid'):
            return enrollment_pb2.EnrollResponse(
                status="error",
                message=f"Authentication failed: {auth_result.get('message', 'Invalid token')}"
            )

        user_id = auth_result['user_id']
        user_role = auth_result['role']

        if user_role != 'student':
            return enrollment_pb2.EnrollResponse(
                status="rejected",
                message=f"Only students can enroll. Your role is '{user_role}'"
            )

        conn = get_db_connection()
        if conn is None:
            return enrollment_pb2.EnrollResponse(
                status="error",
                message="Database is unavailable"
            )

        try:
            cur = conn.cursor(cursor_factory=DictCursor)

            cur.execute("SELECT name, capacity, enrolled, is_open FROM courses WHERE course_id = %s;", (course_id,))
            course = cur.fetchone()

            if course is None:
                return enrollment_pb2.EnrollResponse(
                    status="error",
                    message=f"Course {course_id} not found"
                )

            if not course['is_open']:
                return enrollment_pb2.EnrollResponse(
                    status="error",
                    message=f"Course {course['name']} is not open for enrollment"
                )

            if course['enrolled'] >= course['capacity']:
                return enrollment_pb2.EnrollResponse(
                    status="error",
                    message=f"Course {course['name']} is full"
                )

            cur.execute("SELECT 1 FROM enrollments WHERE student_public_id = %s AND course_id = %s;", 
                        (user_id, course_id))
            if cur.fetchone() is not None:
                return enrollment_pb2.EnrollResponse(
                    status="error",
                    message=f"You are already enrolled in {course['name']}"
                )

            cur.execute("UPDATE courses SET enrolled = enrolled + 1 WHERE course_id = %s;", (course_id,))
            cur.execute("INSERT INTO enrollments (student_public_id, course_id) VALUES (%s, %s);", 
                        (user_id, course_id))

            conn.commit()
            print(f"✓ User {user_id} successfully enrolled in {course_id}")
            
            return enrollment_pb2.EnrollResponse(
                status="success",
                message=f"Successfully enrolled in {course['name']}!"
            )

        except Exception as e:
            conn.rollback()
            print(f"✗ Enrollment error: {e}")
            return enrollment_pb2.EnrollResponse(
                status="error",
                message="An internal error occurred during enrollment"
            )
        finally:
            if conn:
                conn.close()

    def GetStudentEnrollments(self, request, context):
        token = request.token

        # Use local JWT validation
        auth_result = validate_token_locally(token)
        
        if not auth_result.get('valid'):
            return enrollment_pb2.EnrollmentsResponse(
                status="error",
                message="Authentication failed",
                enrollments=[]
            )

        user_id = auth_result['user_id']

        conn = get_db_connection()
        if conn is None:
            return enrollment_pb2.EnrollmentsResponse(
                status="error",
                message="Database unavailable",
                enrollments=[]
            )

        try:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute("""
                    SELECT e.course_id, c.name, e.enrollment_date 
                    FROM enrollments e
                    JOIN courses c ON e.course_id = c.course_id
                    WHERE e.student_public_id = %s
                    ORDER BY e.enrollment_date DESC;
                """, (user_id,))
                rows = cur.fetchall()

                enrollments = []
                for row in rows:
                    enrollment_info = enrollment_pb2.EnrollmentInfo(
                        course_id=row['course_id'],
                        course_name=row['name'],
                        enrollment_date=str(row['enrollment_date'])
                    )
                    enrollments.append(enrollment_info)

                print(f"✓ Retrieved {len(enrollments)} enrollments for user {user_id}")
                return enrollment_pb2.EnrollmentsResponse(
                    status="success",
                    message="Enrollments retrieved",
                    enrollments=enrollments
                )

        except Exception as e:
            print(f"✗ Error fetching enrollments: {e}")
            return enrollment_pb2.EnrollmentsResponse(
                status="error",
                message="Internal server error",
                enrollments=[]
            )
        finally:
            if conn:
                conn.close()

    def DropFromCourse(self, request, context):
        token = request.token
        course_id = request.course_id

        # Use local JWT validation
        auth_result = validate_token_locally(token)
        
        if not auth_result.get('valid'):
            return enrollment_pb2.DropResponse(
                status="error",
                message=f"Authentication failed: {auth_result.get('message', 'Invalid token')}"
            )

        user_id = auth_result['user_id']
        user_role = auth_result['role']

        if user_role != 'student':
            return enrollment_pb2.DropResponse(
                status="rejected",
                message=f"Only students can drop a course. Your role is '{user_role}'"
            )

        conn = get_db_connection()
        if conn is None:
            return enrollment_pb2.DropResponse(
                status="error",
                message="Database is unavailable"
            )

        try:
            cur = conn.cursor(cursor_factory=DictCursor)

            cur.execute("SELECT 1 FROM enrollments WHERE student_public_id = %s AND course_id = %s;", 
                        (user_id, course_id))
            if cur.fetchone() is None:
                return enrollment_pb2.DropResponse(
                    status="error",
                    message=f"You are not enrolled in course {course_id}"
                )

            cur.execute("SELECT name FROM courses WHERE course_id = %s;", (course_id,))
            course = cur.fetchone()
            course_name = course['name'] if course else course_id

            cur.execute("DELETE FROM enrollments WHERE student_public_id = %s AND course_id = %s;", 
                        (user_id, course_id))
            cur.execute("UPDATE courses SET enrolled = enrolled - 1 WHERE course_id = %s AND enrolled > 0;", 
                        (course_id,))

            conn.commit()
            print(f"✓ User {user_id} successfully dropped from {course_id}")
            
            return enrollment_pb2.DropResponse(
                status="success",
                message=f"Successfully dropped from {course_name}."
            )

        except Exception as e:
            conn.rollback()
            print(f"✗ Drop error: {e}")
            return enrollment_pb2.DropResponse(
                status="error",
                message="An internal error occurred during drop process"
            )
        finally:
            if conn:
                conn.close()

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    enrollment_pb2_grpc.add_EnrollmentServiceServicer_to_server(EnrollmentServiceServicer(), server)
    server.add_insecure_port('[::]:50053')
    print("=" * 70)
    print("gRPC Enrollment Service starting on port 50053...")
    print("Using local JWT validation (independent of auth service)")
    print("=" * 70)
    server.start()
    server.wait_for_termination()

if __name__ == '__main__':
    serve()