cd services

mkdir -p generated
python -m grpc_tools.protoc -I./proto --python_out=./generated --grpc_python_out=./generated ./proto/auth.proto

python -m grpc_tools.protoc -I./proto --python_out=./generated --grpc_python_out=./generated ./proto/course.proto

python -m grpc_tools.protoc -I./proto --python_out=./generated --grpc_python_out=./generated ./proto/enrollment.proto

psql -U postgres
CREATE DATABASE student_portal_auth;
CREATE DATABASE student_portal_courses;
\q

Run these in 5 terminals seperately for each one
python app_view.py
python grpc_auth_server.py
python grpc_course_server.py
python grpc_enrollment_server.py
python rest_gateway.py
