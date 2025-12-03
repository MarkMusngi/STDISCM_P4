from flask import Flask, jsonify, request
from common_jwt import token_required

app = Flask(__name__)

# Mock Database
COURSES = {
    'CS101': {'name': 'Distributed Systems', 'status': 'Open', 'capacity': 50, 'enrolled': 45},
    'MATH205': {'name': 'Advanced Calculus', 'status': 'Open', 'capacity': 60, 'enrolled': 15},
    'ENG300': {'name': 'Technical Writing', 'status': 'Closed', 'capacity': 30, 'enrolled': 30},
}

# Track enrollments: { "user_id": ["CS101", "MATH205"] }
ENROLLMENTS = {}

@app.route('/api/v1/courses', methods=['GET'])
@token_required 
def get_available_courses():
    """Feature 2: View available courses."""
    user_id = request.user_data['user_id']
    role = request.user_data['role']
    
    return jsonify({
        "status": "success",
        "courses": COURSES,
        "enrolled": ENROLLMENTS.get(str(user_id), [])
    }), 200

@app.route('/api/v1/enroll', methods=['POST'])
@token_required
def enroll_student():
    """Feature 3: Student Enrollment."""
    user_id = str(request.user_data['user_id'])
    role = request.user_data['role']
    course_id = request.json.get('course_id')

    if role != 'student':
        return jsonify({"status": "error", "message": "Only students can enroll"}), 403

    course = COURSES.get(course_id)
    if not course:
        return jsonify({"status": "error", "message": "Course not found"}), 404
    
    if course['status'] == 'Closed' or course['enrolled'] >= course['capacity']:
        return jsonify({"status": "error", "message": "Course is full or closed"}), 400
    
    # Check if already enrolled
    user_enrollments = ENROLLMENTS.get(user_id, [])
    if course_id in user_enrollments:
        return jsonify({"status": "error", "message": "Already enrolled"}), 400

    # Commit Transaction
    course['enrolled'] += 1
    if user_id not in ENROLLMENTS:
        ENROLLMENTS[user_id] = []
    ENROLLMENTS[user_id].append(course_id)

    print(f"User {user_id} enrolled in {course_id}")
    return jsonify({"status": "success", "message": f"Enrolled in {course_id}"}), 200

if __name__ == '__main__':
    print("Starting Course Service (Node 3) on Port 5002...")
    app.run(port=5002, debug=True)