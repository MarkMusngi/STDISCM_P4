import grpc
from concurrent import futures
import sys
sys.path.append('./generated')

# Assuming the following definitions have been added to the course.proto:
# message CourseInfo {
#   ...
#   string faculty_id = 6;
#   string faculty_username = 7;
# }
# message ClaimCourseRequest {
#   string course_id = 1;
#   string faculty_id = 2;
#   string faculty_username = 3;
# }
# message ClaimCourseResponse {
#   string status = 1;
#   string message = 2;
# }
import course_pb2
import course_pb2_grpc

import psycopg2
from psycopg2.extras import DictCursor
import os

# Configuration
POSTGRES_DB = os.getenv('POSTGRES_DB', 'student_portal_courses')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'postgres')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', '1234')
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = os.getenv('POSTGRES_PORT', '5432')

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

def init_db():
    """Initialize courses database with sample data, including faculty_id."""
    conn = get_db_connection()
    if conn is None:
        print("Cannot initialize DB without a connection.")
        return

    try:
        with conn.cursor() as cur:
            # Drop and recreate the table to include new columns
            cur.execute("DROP TABLE IF EXISTS courses;")
            cur.execute("""
                CREATE TABLE courses (
                    course_id VARCHAR(10) PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    capacity INTEGER NOT NULL,
                    enrolled INTEGER DEFAULT 0,
                    is_open BOOLEAN DEFAULT TRUE,
                    faculty_id VARCHAR(36) DEFAULT NULL,
                    faculty_username VARCHAR(255) DEFAULT NULL
                );
            """)

            # Sample data
            courses_data = [
                ('CS101', 'Introduction to Programming', 30, 15, True, None, None),
                ('MA202', 'Linear Algebra', 25, 25, True, None, None), # Full course
                ('PH301', 'Quantum Mechanics', 20, 10, False, None, None), # Closed course
                ('HI105', 'World History', 40, 20, True, 'b947c0a8-b615-4309-8473-b2649a3c9454', 'prof_a') # Pre-claimed course (Example ID)
            ]
            
            for course_id, name, capacity, enrolled, is_open, faculty_id, faculty_username in courses_data:
                cur.execute("""
                    INSERT INTO courses (course_id, name, capacity, enrolled, is_open, faculty_id, faculty_username)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (course_id) DO NOTHING;
                """, (course_id, name, capacity, enrolled, is_open, faculty_id, faculty_username))

            conn.commit()
            print("Courses table initialized/updated successfully.")
    except Exception as e:
        print(f"Error during database initialization: {e}")
    finally:
        conn.close()


class CourseServiceServicer(course_pb2_grpc.CourseServiceServicer):
    
    # ... (existing GetCourse logic) ...

    def GetAllCourses(self, request, context):
        conn = get_db_connection()
        if conn is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            context.set_details("Database connection failed")
            return course_pb2.AllCoursesResponse(status="error", message="DB connection error")

        try:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute("SELECT * FROM courses;")
                courses = []
                for row in cur.fetchall():
                    courses.append(course_pb2.CourseInfo(
                        course_id=row['course_id'],
                        name=row['name'],
                        capacity=row['capacity'],
                        enrolled=row['enrolled'],
                        is_open=row['is_open'],
                        faculty_id=row['faculty_id'] or "",  # Include new fields
                        faculty_username=row['faculty_username'] or ""
                    ))
                
                return course_pb2.AllCoursesResponse(
                    status="success",
                    message="All courses retrieved",
                    courses=courses
                )
        except Exception as e:
            print(f"Error fetching all courses: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Internal server error")
            return course_pb2.AllCoursesResponse(status="error", message="Internal server error")
        finally:
            conn.close()

    def GetCourse(self, request, context):
        course_id = request.course_id
        conn = get_db_connection()
        if conn is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            context.set_details("Database connection failed")
            return course_pb2.CourseResponse(status="error", message="DB connection error", course=None)

        try:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute("SELECT * FROM courses WHERE course_id = %s;", (course_id,))
                row = cur.fetchone()
                
                if row is None:
                    return course_pb2.CourseResponse(
                        status="error",
                        message=f"Course {course_id} not found",
                        course=None
                    )
                
                course_info = course_pb2.CourseInfo(
                    course_id=row['course_id'],
                    name=row['name'],
                    capacity=row['capacity'],
                    enrolled=row['enrolled'],
                    is_open=row['is_open'],
                    faculty_id=row['faculty_id'] or "",  # Include new fields
                    faculty_username=row['faculty_username'] or ""
                )
                
                return course_pb2.CourseResponse(
                    status="success",
                    message="Course details retrieved",
                    course=course_info
                )
        
        except Exception as e:
            print(f"Error fetching course details: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Internal server error")
            return course_pb2.CourseResponse(
                status="error",
                message="Internal server error",
                course=None
            )
        finally:
            conn.close()

    def ClaimCourse(self, request, context):
        """Allows a faculty member to claim an unassigned course."""
        course_id = request.course_id
        faculty_id = request.faculty_id
        faculty_username = request.faculty_username
        
        if not course_id or not faculty_id:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details("Missing course ID or faculty ID")
            return course_pb2.ClaimCourseResponse(status="error", message="Missing course ID or faculty ID")
        
        conn = get_db_connection()
        if conn is None:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            context.set_details("Database connection failed")
            return course_pb2.ClaimCourseResponse(status="error", message="DB connection error")

        try:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                # 1. Check if the course exists and is unclaimed
                cur.execute("SELECT faculty_id FROM courses WHERE course_id = %s FOR UPDATE;", (course_id,))
                row = cur.fetchone()

                if row is None:
                    return course_pb2.ClaimCourseResponse(
                        status="error",
                        message=f"Course {course_id} not found."
                    )
                
                if row['faculty_id']:
                    # Course is already claimed
                    return course_pb2.ClaimCourseResponse(
                        status="error",
                        message=f"Course {course_id} is already claimed by another faculty."
                    )

                # 2. Claim the course
                cur.execute("""
                    UPDATE courses 
                    SET faculty_id = %s, faculty_username = %s 
                    WHERE course_id = %s;
                """, (faculty_id, faculty_username, course_id))

                if cur.rowcount == 0:
                    conn.rollback()
                    return course_pb2.ClaimCourseResponse(
                        status="error",
                        message="Failed to update course ownership."
                    )

                conn.commit()
                print(f"Course {course_id} successfully claimed by faculty {faculty_username} ({faculty_id})")
                
                return course_pb2.ClaimCourseResponse(
                    status="success",
                    message=f"Course {course_id} successfully claimed."
                )
                
        except Exception as e:
            conn.rollback()
            print(f"Error claiming course {course_id}: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Internal server error during course claim")
            return course_pb2.ClaimCourseResponse(status="error", message="Internal server error")
        finally:
            conn.close()


def serve():
    init_db()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    course_pb2_grpc.add_CourseServiceServicer_to_server(CourseServiceServicer(), server)
    server.add_insecure_port('[::]:50052')
    print("gRPC Course Service starting on port 50052...")
    server.start()
    server.wait_for_termination()

if __name__ == '__main__':
    serve()