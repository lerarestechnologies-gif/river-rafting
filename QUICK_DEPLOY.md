# 🚀 QUICK START: Deploy to Render.com in 5 Minutes

## Prerequisites
- GitHub account (code pushed)
- MongoDB Atlas cluster
- Render.com account

## Step 1: Generate Strong Keys (Run Locally)
```bash
# Generate SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"
# Output: copy this value
```

## Step 2: Get MongoDB Connection String
1. Go to MongoDB Atlas
2. Click "Connect" → "Drivers"
3. Copy connection string (looks like: `mongodb+srv://...`)
4. Replace `<password>` with actual password

## Step 3: Push Code to GitHub (if not already done)
```bash
git add .
git commit -m "Production ready for Render"
git push origin main
```

## Step 4: Create Render Service
1. Go to https://dashboard.render.com
2. Click "New +" → "Web Service"
3. Connect your GitHub repository

## Step 5: Configure Build & Start Commands

| Setting | Value |
|---------|-------|
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `gunicorn app:app` |
| **Python Version** | 3.11 (auto-detected from runtime.txt) |

## Step 6: Add Environment Variables
In Render Dashboard → Service → **Environment**, add:

```
MONGO_URI=mongodb+srv://username:password@cluster.mongodb.net/raft_booking?retryWrites=true&w=majority&appName=rafting

SECRET_KEY=<paste-the-key-from-step-1>

ENVIRONMENT=production

DEBUG=false
```

## Step 7: Deploy
1. Click **"Deploy"** button
2. Wait for "Your service is live" message
3. Note the URL: `https://your-service-name.onrender.com`

## Step 8: Verify Deployment
```bash
curl https://your-service-name.onrender.com/health

# Expected response:
# {"status": "ok", "db": "connected", "environment": "production"}
```

✅ **Done!** Your app is now live on Render.com

---

## 🔧 Troubleshooting

### 502 Bad Gateway
- Check Render logs: Service → Logs
- Verify MONGO_URI is correct and can be accessed
- Ensure MongoDB Atlas allows all IP addresses (or Render's IP)

### Can't Connect to Database
- Verify MONGO_URI is correct (copy from MongoDB Atlas)
- In MongoDB Atlas → Network Access, add IP `0.0.0.0/0` or Render's IP
- Test connection locally first

### ImportError: No module named...
- Ensure requirements.txt is correct
- Verify runtime.txt exists with `python-3.11.10`
- Check that dependencies list all packages needed

---

## 📚 Full Documentation
- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Detailed step-by-step guide
- **[DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)** - Pre-deployment verification
- **[PRODUCTION_READINESS.md](PRODUCTION_READINESS.md)** - What was changed and why
- **[README.md](README.md)** - Project information

---

## ⏱️ Typical Timeline
- Build: 2-3 minutes
- Start: 30-60 seconds
- Total first deployment: 3-5 minutes

---

**Questions?** Check the detailed guides linked above or review your Render service logs.

