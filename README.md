Initialize the proto files using these command
cd services
mkdir -p generated
python -m grpc_tools.protoc -I./proto --python_out=./generated --grpc_python_out=./generated ./proto/auth.proto
python -m grpc_tools.protoc -I./proto --python_out=./generated --grpc_python_out=./generated ./proto/course.proto
python -m grpc_tools.protoc -I./proto --python_out=./generated --grpc_python_out=./generated ./proto/enrollment.proto
python -m grpc_tools.protoc -I./proto --python_out=./generated --grpc_python_out=./generated ./proto/grades.proto
python -m grpc_tools.protoc -I./proto --python_out=./generated --grpc_python_out=./generated ./proto/faculty_grades.proto

Initialize the PostgreSQL Databases
psql -U postgres
CREATE DATABASE student_portal_auth;
CREATE DATABASE student_portal_courses;
CREATE DATABASE student_portal_grades;
\q

Run all services in seperate terminals (CMD)
python app_view.py
python grpc_auth_server.py
python grpc_course_server.py
python grpc_enrollment_server.py
python grpc_grades_server.py
python grpc_faculty_grades_server.py
python rest_gateway.py

After doing all the steps, run at http://localhost:5000.