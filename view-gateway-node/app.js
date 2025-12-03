const express = require('express');
const cookieParser = require('cookie-parser');
const bodyParser = require('body-parser');
const exphbs = require('express-handlebars');
const path = require('path');
const axios = require('axios'); // Used to make HTTP calls to other services

const app = express();
const PORT = 3000; // Standard port for the web interface
const AUTH_SERVICE_URL = 'http://localhost:3001'; // URL of the Auth Service

// --- Middleware Setup ---
app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, 'views'));
app.use(express.static(path.join(__dirname, 'public')));
app.use(bodyParser.urlencoded({ extended: true }));
app.use(cookieParser());

// --- Handlebars Configuration ---
app.engine('handlebars', exphbs.engine({
    // Configure the directory where your main layout file lives
    layoutsDir: path.join(__dirname, 'views/layouts'),
    // The main layout file (must exist)
    defaultLayout: 'main', 
    // The extension used for the view files
    extname: 'handlebars' 
}));
app.set('view engine', 'handlebars');
app.set('views', path.join(__dirname, 'views'));

// --- Simple Mock View Files (You'll need to create these empty files) ---
// /view-gateway-node/views/login.ejs
// /view-gateway-node/views/courses.ejs 

// --- Core Routing ---

// 1. Home/Courses Route (Requires Auth)
app.get('/', (req, res) => {
    // Check if the user has a JWT token in their cookies
    const token = req.cookies.jwt; 
    
    if (!token) {
        return res.redirect('/login');
    }

    // In a real scenario, you'd validate the token here via the Auth Service
    // For now, we'll just check if a token exists and assume valid
    // The Course View logic will be added here later.
    res.render('courses', { 
        message: 'Welcome! You are logged in. (Full course data coming soon!)' 
    });
});

// 2. Login Page
app.get('/login', (req, res) => {
    res.render('login', { error: null });
});

// 3. Handle Login Submission
app.post('/login', async (req, res) => {
    try {
        const response = await axios.post(`${AUTH_SERVICE_URL}/api/login`, req.body);
        
        if (response.data.success) {
            // Set the JWT token as an HTTP-only cookie for secure session tracking
            res.cookie('jwt', response.data.token, { httpOnly: true, maxAge: 3600000 }); 
            return res.redirect('/');
        } else {
            return res.render('login', { error: 'Login failed: Invalid credentials.' });
        }
    } catch (error) {
        // --- FAULT TOLERANCE TEST HERE ---
        // If the Auth Service is down (e.g., terminal 2 is closed), this catch block runs.
        console.error('Error connecting to Auth Service:', error.message);
        return res.render('login', { 
            error: 'Authentication Service Unavailable. Please try again later.' 
        });
    }
});

// 4. Logout
app.get('/logout', (req, res) => {
    res.clearCookie('jwt');
    res.redirect('/login');
});


app.listen(PORT, () => {
    console.log(`View/Gateway Node running on http://localhost:${PORT}`);
});