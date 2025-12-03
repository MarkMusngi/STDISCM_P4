const express = require('express');
const bodyParser = require('body-parser');
const jwt = require('jsonwebtoken');
const authModel = require('./authModel');

const app = express();
const PORT = 3001; 
const JWT_SECRET = 'YOUR_SUPER_SECRET_KEY'; 

app.use(bodyParser.json());

// 1. Login Endpoint
app.post('/api/login', (req, res) => {
    const { username, password } = req.body;
    const user = authModel.findUser(username, password);

    if (user) {
        // Create a JWT token with user info (payload)
        const token = jwt.sign(
            { id: user.id, username: user.username, role: user.role },
            JWT_SECRET,
            { expiresIn: '1h' } // Token expires in 1 hour
        );
        // Send the token back to the View Node
        return res.json({ success: true, token });
    } else {
        return res.status(401).json({ success: false, message: 'Invalid credentials' });
    }
});

// 2. Token Validation Endpoint (Used internally by other services later)
app.post('/api/validate', (req, res) => {
    const token = req.body.token || req.headers['authorization']?.split(' ')[1];
    
    if (!token) {
        return res.status(401).json({ isValid: false, message: 'No token provided' });
    }

    jwt.verify(token, JWT_SECRET, (err, decoded) => {
        if (err) {
            return res.status(401).json({ isValid: false, message: 'Invalid or expired token' });
        }
        // Token is valid, return the user payload
        return res.json({ isValid: true, user: decoded });
    });
});

app.listen(PORT, () => {
    console.log(`Auth Service running on port ${PORT}.`);
    console.log('Test Credentials: student1/password | faculty1/password');
});