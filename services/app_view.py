from flask import Flask, render_template, redirect, url_for, request, session, jsonify
import requests 

app = Flask(__name__, 
            template_folder='../frontend/templates', 
            static_folder='../frontend/static')
app.config['SECRET_KEY'] = 'a_view_node_secret_key_for_flask_sessions' 

# Service URLs
AUTH_SERVICE_URL = 'http://127.0.0.1:5001'
COURSE_SERVICE_URL = 'http://127.0.0.1:5002'
GRADES_READ_SERVICE_URL = 'http://127.0.0.1:5003'
GRADES_WRITE_SERVICE_URL = 'http://127.0.0.1:5004'

# --- PAGE ROUTES ---
@app.route('/')
def index():
    # If a user is logged in, redirect them to the courses page
    if 'jwt_token' in session:
        return redirect(url_for('courses_page'))
    return render_template('auth.html')

@app.route('/courses')
def courses_page():
    if 'jwt_token' not in session: return redirect(url_for('index'))
    # Pass the user_role to the template
    return render_template('courses.html', user_role=session.get('user_role'))

@app.route('/my_grades')
def grades_view():
    if 'jwt_token' not in session: return redirect(url_for('index'))
    return render_template('grades_view.html', service_name="Grades Read Node")

@app.route('/faculty/upload')
def grades_upload_view():
    if 'jwt_token' not in session: return redirect(url_for('index'))
    # In a real app, we'd check session['user_role'] == 'faculty' here
    return render_template('grades_upload.html', service_name="Grades Write Node")

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# --- API PROXY ROUTES ---

@app.route('/api/login', methods=['POST'])
def handle_login():
    try:
        # Proxy to Auth Node
        response = requests.post(f"{AUTH_SERVICE_URL}/api/v1/auth/login", json=request.json)
        
        if response.status_code == 200:
            data = response.json()
            session['jwt_token'] = data.get('token')
            session['user_role'] = data.get('role')
            session['user_id'] = data.get('user_id')  # <--- VITAL: Save User ID for Grades
            return jsonify({"status": "success", "redirect": "/courses"}), 200
        else:
            return jsonify(response.json()), response.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"status": "error", "message": "Auth Service (Node 2) Unavailable"}), 503 

@app.route('/api/courses', methods=['GET'])
def get_courses():
    if 'jwt_token' not in session: return jsonify({"message": "Unauthorized"}), 401
    
    headers = {'Authorization': f"Bearer {session['jwt_token']}"}
    try:
        # Proxy to Course Node
        response = requests.get(f"{COURSE_SERVICE_URL}/api/v1/courses", headers=headers)
        return jsonify(response.json()), response.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"status": "error", "message": "Course Service (Node 3) Unavailable"}), 503 
    
@app.route('/api/enroll', methods=['POST'])
def enroll_proxy():
    if 'jwt_token' not in session: return jsonify({"message": "Unauthorized"}), 401
    
    headers = {'Authorization': f"Bearer {session['jwt_token']}"}
    try:
        # Proxy to Course Service (Node 3)
        response = requests.post(f"{COURSE_SERVICE_URL}/api/v1/enroll", json=request.json, headers=headers)
        return jsonify(response.json()), response.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"status": "error", "message": "Course Service Unavailable"}), 503

@app.route('/api/grades', methods=['GET'])
def get_grades():
    """Proxies request to Node 4 to get grades for the current logged-in user."""
    if 'user_id' not in session: return jsonify({"message": "Unauthorized"}), 401

    user_id = session['user_id']
    try:
        # Proxy to Grades Read Node (Node 4)
        response = requests.get(f"{GRADES_READ_SERVICE_URL}/api/v1/grades/student/{user_id}")
        return jsonify(response.json()), response.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"status": "error", "message": "Grades Read Service (Node 4) Unavailable"}), 503

@app.route('/api/grades/upload', methods=['POST'])
def upload_grades():
    """Proxies request to Node 5 for faculty uploads."""
    if 'jwt_token' not in session: return jsonify({"message": "Unauthorized"}), 401
    
    payload = request.json
    # Add faculty ID from session to ensure security
    payload['faculty_id'] = session.get('user_id')

    try:
        # Proxy to Grades Write Node (Node 5)
        response = requests.post(f"{GRADES_WRITE_SERVICE_URL}/api/v1/grades/upload", json=payload)
        return jsonify(response.json()), response.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"status": "error", "message": "Grades Write Service (Node 5) Unavailable"}), 503

if __name__ == '__main__':
    print("Starting View Service (Node 1) on Port 5000...")
    app.run(port=5000, debug=True)