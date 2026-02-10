# Raft Booking Application

A modern Flask + MongoDB Atlas web application for managing raft booking reservations, built for production deployment on Render.com.

## Features

- 🎟️ **Booking Management** - Users can book raft slots and track reservations
- 📅 **Flexible Scheduling** - Admin-configurable booking windows and time slots
- 👥 **Multi-Role Access** - Admin and Sub-Admin dashboards with different permissions
- 💾 **Secure Authentication** - Password hashing with bcrypt
- 🗄️ **MongoDB Integration** - Cloud-hosted database with Atlas
- 🔐 **Production Security** - Hardened Flask config, secure cookies, environment variables
- 📊 **Health Monitoring** - Built-in health check endpoint

## Technology Stack

- **Backend:** Flask 3.1.2 (Python)
- **Database:** MongoDB Atlas
- **Server:** Gunicorn
- **Deployment:** Render.com
- **Python Version:** 3.11.10

## Project Structure

```
.
├── app.py                    # Flask application entry point
├── config.py                 # Configuration from environment variables
├── requirements.txt          # Python dependencies
├── runtime.txt              # Python version for Render
├── .env.example             # Example environment variables
├── .gitignore               # Files to ignore in git
│
├── models/
│   ├── user_model.py        # User authentication & roles
│   ├── booking_model.py     # Booking reservation logic
│   └── raft_model.py        # Raft availability management
│
├── routes/
│   ├── auth_routes.py       # Login/logout/authentication
│   ├── booking_routes.py    # User booking endpoints
│   └── admin_routes.py      # Admin dashboard & management
│
├── templates/
│   ├── base.html            # Base template
│   ├── home.html            # Home page
│   ├── login.html           # Login page
│   ├── booking.html         # Booking form
│   ├── admin_dashboard.html # Admin dashboard
│   └── ...                  # Other templates
│
├── static/
│   ├── css/
│   │   └── style.css        # Styling
│   └── images/
│       └── ...              # Images & assets
│
├── utils/
│   ├── allocation_logic.py  # Raft allocation algorithm
│   ├── booking_ops.py       # Booking operations
│   ├── amount_calculator.py # Fee calculation
│   └── settings_manager.py  # Admin settings
│
├── scripts/
│   ├── init_db.py           # Database initialization
│   ├── create_subadmin.py   # Create subadmin user
│   └── test_mongo_connection.py  # Connection testing
│
└── docs/
    ├── DEPLOYMENT.md        # Step-by-step deployment guide
    └── DEPLOYMENT_CHECKLIST.md  # Pre-deployment verification
```

## Quick Start (Development)

### Prerequisites
- Python 3.11+
- MongoDB Atlas account
- Git

### Setup

1. **Clone the repository:**
```bash
git clone https://github.com/YOUR_USERNAME/raft-booking-app.git
cd raft-booking-app
```

2. **Create virtual environment:**
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

3. **Install dependencies:**
```bash
pip install -r requirements.txt
```

4. **Create `.env` file:**
```bash
cp .env.example .env
```

5. **Configure MongoDB:**
Edit `.env` and add your MongoDB Atlas connection string:
```
MONGO_URI=mongodb+srv://username:password@cluster.mongodb.net/raft_booking?retryWrites=true&w=majority&appName=rafting
SECRET_KEY=your-secret-key-here
ENVIRONMENT=development
DEBUG=true
```

6. **Run the application:**
```bash
python app.py
```

The app will be available at `http://localhost:5000`

## Production Deployment (Render.com)

### 1. Complete the Deployment Checklist
See [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md) for pre-deployment verification.

### 2. Follow Deployment Guide
See [DEPLOYMENT.md](DEPLOYMENT.md) for complete step-by-step instructions.

### 3. Quick Summary
```
Build Command:  pip install -r requirements.txt
Start Command:  gunicorn app:app
```

Environment Variables Required:
- `MONGO_URI` - MongoDB Atlas connection string
- `SECRET_KEY` - Strong random key for sessions
- `ENVIRONMENT` - Set to `production`
- `DEBUG` - Set to `false`

## API Endpoints

### Public
- `GET /` - Home page
- `POST /login` - User login
- `GET /book` - Booking page
- `POST /book` - Submit booking
- `GET /health` - Health check (useful for monitoring)

### Admin (Protected)
- `GET /admin/dashboard` - Admin dashboard
- `GET /admin/bookings` - View all bookings
- `POST /admin/booking/<id>/confirm` - Confirm booking
- `POST /admin/booking/<id>/cancel` - Cancel booking

### Sub-Admin (Protected)
- Same as admin with limited data (today/tomorrow only)

## Database Schema

### Users Collection
```json
{
  "_id": ObjectId,
  "name": "string",
  "email": "string",
  "phone": "string",
  "password_hash": "string",
  "role": "admin|subadmin|user"
}
```

### Bookings Collection
```json
{
  "_id": ObjectId,
  "contact_name": "string",
  "contact_email": "string",
  "contact_phone": "string",
  "date": "YYYY-MM-DD",
  "time_slot": "string",
  "status": "Pending|Confirmed|Cancelled",
  "amount": "number",
  "created_at": "ISO datetime"
}
```

### Rafts Collection
```json
{
  "_id": ObjectId,
  "date": "YYYY-MM-DD",
  "time_slot": "string",
  "raft_number": "number",
  "status": "available|occupied"
}
```

## Environment Variables

| Variable | Required | Mode | Description |
|----------|----------|------|-------------|
| `MONGO_URI` | Yes | Both | MongoDB Atlas connection string |
| `SECRET_KEY` | Yes | Both | Flask session secret (must be strong) |
| `ENVIRONMENT` | No | Both | `development` or `production` (default: production) |
| `DEBUG` | No | Dev | `true` for development, `false` for production |

## Configuration

Configuration is loaded from `config.py`:
```python
from config import MONGO_URI, SECRET_KEY, DEBUG, ENVIRONMENT
```

- Development: Variables load from `.env` file
- Production: Variables load from Render environment variables
- If required variables missing, the app raises an error on startup

## Security Features

✅ **Production Security Hardening:**
- Debug mode disabled in production
- Secure session cookies (HTTPS only)
- HTTP-only session prevention
- CSRF protection via Flask-Login
- Password hashing with bcrypt
- No hardcoded secrets
- Environment variables for all credentials
- Error handling for database failures
- Structured logging for monitoring

## Logging

The application uses Python's standard logging module configured for production:
```
Level:     INFO and above
Format:    Timestamp - Name - Level - Message
Destination: Console (visible in Render logs)
```

Example log output:
```
2026-02-07 12:34:56,789 - app - INFO - MongoDB connection initialized
2026-02-07 12:34:57,123 - app - INFO - Blueprints registered successfully
2026-02-07 12:34:58,456 - app - INFO - Starting Flask app in production mode
```

## Health Check

Monitor application health:
```bash
curl https://your-app-name.onrender.com/health
```

**Success Response (200 OK):**
```json
{
  "status": "ok",
  "db": "connected",
  "environment": "production"
}
```

**Failure Response (503 Service Unavailable):**
```json
{
  "status": "error",
  "db": "disconnected",
  "message": "Connection timeout"
}
```

## Troubleshooting

### MongoDB Connection Failed
- Verify `MONGO_URI` is correct
- Check MongoDB Atlas user credentials
- Ensure IP/network access is allowed in Atlas
- Test connection: `mongosh "YOUR_MONGO_URI"`

### Import Errors
- Ensure all dependencies installed: `pip install -r requirements.txt`
- Verify Python 3.11+ is being used
- Check for circular imports in models/routes

### Booking Page Won't Load
- Check that raft data is initialized in MongoDB
- Run: `python scripts/init_db.py` (local development)
- Check admin settings in database

### Admin Login Fails
- Create admin user: `python scripts/create_subadmin.py`
- Verify password hash in database
- Check user role is set to `admin` or `subadmin`

## Performance Optimization

For production improvements:
1. Add Redis caching layer
2. Use CDN for static files
3. Enable MongoDB index optimization
4. Monitor Render metrics
5. Set up database backups

## Development Workflow

```bash
# Install development dependencies
pip install -r requirements.txt

# Set DEBUG=true in .env
ENVIRONMENT=development
DEBUG=true

# Run locally
python app.py

# Make changes
# Test locally
# Commit and push to GitHub
# Render auto-deploys if enabled

# View production logs
# Render Dashboard → Service → Logs
```

## Testing User

For local testing, create a test admin:
```bash
python scripts/create_subadmin.py
```

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| Flask | 3.1.2 | Web framework |
| Flask-Login | 0.6.3 | User authentication |
| Flask-PyMongo | 3.0.1 | MongoDB integration |
| PyMongo | 4.15.3 | MongoDB driver |
| Gunicorn | 23.0.0 | WSGI server |
| Bcrypt | 5.0.0 | Password hashing |
| python-dotenv | 1.2.1 | Environment variables |
| DNSPython | 2.4.2 | MongoDB DNS resolution |

See [requirements.txt](requirements.txt) for complete list with versions.

## Contributing

1. Create feature branch: `git checkout -b feature/amazing-feature`
2. Commit changes: `git commit -m 'Add amazing feature'`
3. Push to branch: `git push origin feature/amazing-feature`
4. Open Pull Request

## License

This project is proprietary and confidential.

## Support

- 📖 Read [DEPLOYMENT.md](DEPLOYMENT.md) for deployment issues
- ✅ Check [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md) before deploying
- 🐛 Review logs in Render Dashboard
- 📞 Contact development team

## Version History

- **v1.0** (2026-02-07) - Production ready release
  - Added Gunicorn for production server
  - Removed hardcoded secrets
  - Added environment variable configuration
  - Created production deployment documentation
  - Hardened Flask security settings
  - Added structured logging
  - Created .gitignore and .env.example

---

**Last Updated:** February 7, 2026  
**Status:** ✅ Production Ready  
**Deployment Target:** Render.com  
**Database:** MongoDB Atlas  
