import jwt
from functools import wraps
from flask import request, jsonify

# Shared JWT config for all services
SECRET_KEY = 'super_secret_distributed_key_shh_its_a_secret'
ALGORITHM = 'HS256'
EXPIRY_HOURS = 2


def token_required(f):
    """
    Decorator to enforce JWT authentication on API endpoints.
    Checks the Authorization header for a valid Bearer token
    and attaches decoded payload to request.user_data.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None

        # Expect Authorization: Bearer <token>
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ', 1)[1]

        if not token:
            return jsonify({'status': 'error', 'message': 'Token is missing!'}), 401

        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            # Attach decoded JWT to the request for downstream handlers
            request.user_data = data
        except jwt.ExpiredSignatureError:
            return jsonify({'status': 'error', 'message': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'status': 'error', 'message': 'Invalid token'}), 401

        return f(*args, **kwargs)

    return decorated