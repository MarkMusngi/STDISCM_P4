const users = [
    { id: 101, username: 'student1', password: 'password', role: 'student' },
    { id: 201, username: 'faculty1', password: 'password', role: 'faculty' }
];

// In a real app, 'password' would be a hashed value (e.g., bcrypt)
function findUser(username, password) {
    return users.find(user => user.username === username && user.password === password);
}

module.exports = {
    findUser
};