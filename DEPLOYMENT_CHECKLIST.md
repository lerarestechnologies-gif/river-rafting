# Production Deployment Checklist for Render.com

Use this checklist before deploying to Render.com to ensure everything is production-ready.

## Code Quality & Security

- [x] Debug mode disabled in production (config.py)
- [x] No hardcoded secrets in code
- [x] All database credentials use environment variables
- [x] `.gitignore` prevents committing `.env` file
- [x] `.env` file never committed to git
- [x] Secure session cookies enabled
- [x] Error handlers configured for 404 and 500 errors
- [x] Logging configured for production
- [x] MongoDB Atlas requires strong password
- [x] SECRET_KEY is unique and strong (not "some-long-random-secure-key")

## Project Structure

- [x] `venv/` removed from repository
- [x] `__pycache__/` directories removed
- [x] `*.pyc` files removed
- [x] `start.bat` removed (Windows-only)
- [x] `.gitignore` file created
- [x] `.env.example` file created with placeholder values
- [x] `runtime.txt` specifies Python 3.11.10
- [x] `requirements.txt` updated and tested
- [x] Gunicorn added to `requirements.txt`
- [x] All necessary dependencies listed

## Configuration Files

- [x] `config.py` loads from environment variables
- [x] `config.py` raises error if MONGO_URI not set
- [x] `config.py` raises error if SECRET_KEY not set
- [x] `app.py` imports config safely with try/except
- [x] `app.py` does not require `if __name__ == '__main__'` for Render
- [x] MongoDB connection has error handling
- [x] Blueprints import has error handling
- [x] Health endpoint (`/health`) works

## Production Settings

- [x] Flask DEBUG = False
- [x] SESSION_COOKIE_SECURE = True in production
- [x] SESSION_COOKIE_HTTPONLY = True
- [x] SESSION_COOKIE_SAMESITE set to 'Lax'
- [x] PERMANENT_SESSION_LIFETIME set (30 minutes)
- [x] Error handlers return proper HTTP status codes
- [x] No print statements in production code (use logging instead)

## Dependencies & Versions

- [x] `requirements.txt` has pinned versions
- [x] All packages are production-appropriate
- [x] `gunicorn` is in `requirements.txt`
- [x] `python-dotenv` is in `requirements.txt`
- [x] Flask is latest stable version (3.1.2)
- [x] PyMongo is latest stable version (4.15.3)
- [x] Bcrypt is latest stable version (5.0.0)
- [x] No development-only packages in production

## Render Configuration

### Before Deployment
- [ ] GitHub repository created and code pushed
- [ ] `.gitignore` verified to prevent secret commits
- [ ] MongoDB Atlas cluster created
- [ ] MongoDB database user created
- [ ] MongoDB collection access configured
- [ ] Render.com account created
- [ ] Connection string copied from MongoDB Atlas

### Service Configuration in Render Dashboard
- [ ] Service name set (e.g., "raft-booking-app")
- [ ] GitHub repo connected
- [ ] Python 3 environment selected
- [ ] **Build Command:** `pip install -r requirements.txt`
- [ ] **Start Command:** `gunicorn app:app`
- [ ] Instance type selected (Free/Starter)
- [ ] Auto-deploy from main branch enabled (optional)

### Environment Variables in Render
- [ ] `MONGO_URI` set correctly (with username:password)
- [ ] `SECRET_KEY` set to a strong random value
- [ ] `ENVIRONMENT` set to `production`
- [ ] `DEBUG` set to `false`
- [ ] All environment variables reviewed for typos

## Pre-Deployment Testing (Local Machine)

```bash
# Create local .env file
cp .env.example .env
# Edit .env with your MongoDB credentials

# Install dependencies
pip install -r requirements.txt

# Test configuration loading
python -c "from config import MONGO_URI, SECRET_KEY; print('Config loaded successfully')"

# Test MongoDB connection
python -c "import pymongo; pymongo.MongoClient('YOUR_MONGO_URI').server_info(); print('MongoDB connected')"

# Test Flask app startup (should start without debug mode)
python app.py &
# Test health endpoint
curl http://localhost:5000/health
```

- [ ] Dependencies install without errors
- [ ] Configuration loads successfully
- [ ] MongoDB connection succeeds
- [ ] Flask app starts without errors
- [ ] Health endpoint returns 200 OK response
- [ ] Login page loads
- [ ] Booking page loads
- [ ] Admin dashboard accessible

## Deployment Execution

1. [ ] Commit all changes: `git add . && git commit -m "Production ready"`
2. [ ] Push to GitHub: `git push origin main`
3. [ ] Go to Render dashboard
4. [ ] Click "New Web Service"
5. [ ] Connect GitHub repository
6. [ ] Choose Python 3 environment
7. [ ] Set Build Command: `pip install -r requirements.txt`
8. [ ] Set Start Command: `gunicorn app:app`
9. [ ] Add all environment variables
10. [ ] Click "Create Web Service"
11. [ ] Monitor deployment logs for errors
12. [ ] Wait for "Service live" message

## Post-Deployment Verification

- [ ] Render logs show no errors
- [ ] App status shows "Live" and "Active"
- [ ] Health endpoint works: `curl https://app-name.onrender.com/health`
- [ ] Response includes `"status": "ok"` and `"db": "connected"`
- [ ] Home page loads: `https://app-name.onrender.com/`
- [ ] Login page loads: `https://app-name.onrender.com/login`
- [ ] Login functionality works
- [ ] Booking page loads: `https://app-name.onrender.com/book`
- [ ] Can create a test booking
- [ ] Admin dashboard loads: `https://app-name.onrender.com/admin/dashboard`
- [ ] Database queries work correctly
- [ ] Static files load (CSS, images)
- [ ] No 502 Bad Gateway errors
- [ ] No MongoDB connection errors in logs

## Monitoring & Maintenance

- [ ] Set up Render alerts for service failures
- [ ] Monitor Render dashboard for CPU/memory usage
- [ ] Check MongoDB Atlas for slow queries
- [ ] Test backups are working
- [ ] Review logs regularly for errors
- [ ] Monitor uptime statistics

## Common Issues Resolved

- [x] No hardcoded MongoDB password in code
- [x] No development dependencies in requirements.txt
- [x] Debug mode disabled
- [x] Gunicorn configured as start command
- [x] Python version pinned in runtime.txt
- [x] Health check endpoint available
- [x] Error handling for missing environment variables
- [x] Session cookies secure in production

## Documentation

- [x] DEPLOYMENT.md created with step-by-step guide
- [x] .env.example provided as reference
- [x] Comments added to config.py for environment variables
- [x] README.md describes the application

## Final Sign-Off

- [ ] Project lead reviewed all changes
- [ ] All tests pass locally
- [ ] No security vulnerabilities detected
- [ ] Performance acceptable
- [ ] Ready for production deployment

---

**Date Completed:** _____________  
**Deployed By:** _____________  
**Render Service URL:** _____________  
**Version:** 1.0 (Production Ready)  

