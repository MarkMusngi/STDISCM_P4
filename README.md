# Run this once for the View Node
cd /view-gateway-node
npm init -y
npm install express body-parser cookie-parser axios ejs

# Run this once for the Auth Service Node
cd /api-controller-node/src/auth-service
npm init -y
npm install express body-parser jsonwebtoken