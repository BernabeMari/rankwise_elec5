# Deployment Guide for RankWise

## Deploying to Render

### 1. Prerequisites
- A Render account
- Your code pushed to a Git repository (GitHub, GitLab, etc.)

### 2. Configuration Files Created
The following files have been created/updated for Render deployment:

- `requirements.txt` - Updated with compatible package versions
- `runtime.txt` - Specifies Python 3.10.12
- `render.yaml` - Render deployment configuration
- `Procfile` - Alternative deployment configuration
- `.python-version` - Python version specification

### 3. Deployment Steps

1. **Connect your repository to Render:**
   - Go to [render.com](https://render.com)
   - Click "New +" and select "Web Service"
   - Connect your Git repository
   - Select the repository containing your RankWise app

2. **Configure the service:**
   - **Name:** `rankwise` (or your preferred name)
   - **Environment:** `Python`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn run:app --bind 0.0.0.0:$PORT`

3. **Environment Variables (optional):**
   - `FLASK_ENV`: `production`
   - `FLASK_APP`: `run.py`

4. **Deploy:**
   - Click "Create Web Service"
   - Render will automatically build and deploy your app

### 4. What Was Fixed

The original error was caused by:
- `fuzzywuzzy` and `python-Levenshtein` packages not being compatible with Python 3.13
- These packages were replaced with `rapidfuzz` which is:
  - Fully compatible with Python 3.11+
  - Faster and more maintained
  - Has the same API as `fuzzywuzzy`

### 5. Package Versions

Updated package versions for better compatibility:
- Flask: 3.0.0 (from 2.2.3)
- Flask-SQLAlchemy: 3.1.1 (from 3.0.3)
- SQLAlchemy: 2.0.23 (from 2.0.21)
- pandas: 2.0.3 (kept stable for compatibility)
- Added: gunicorn for production deployment

### 6. Testing Locally

Before deploying, test the rapidfuzz replacement:
```bash
python test_rapidfuzz.py
```

### 7. Common Issues and Solutions

#### Issue: Build fails with package installation errors
**Solution:** Ensure you're using Python 3.10.12 (specified in runtime.txt)

#### Issue: App starts but crashes
**Solution:** Check Render logs for specific error messages

#### Issue: Database connection errors
**Solution:** The app uses SQLite which should work fine on Render

### 8. Monitoring

- Check Render dashboard for deployment status
- Monitor logs for any runtime errors
- Set up alerts for service failures

### 9. Scaling

- Start with the free plan
- Upgrade to paid plans for better performance and reliability
- Consider adding a database service for production use

## Local Development

To run locally with the same configuration:
```bash
# Install dependencies
pip install -r requirements.txt

# Run the app
python run.py
```

## Support

If you encounter issues:
1. Check Render deployment logs
2. Verify all configuration files are present
3. Test locally with `python test_rapidfuzz.py`
4. Check that your Git repository contains all the updated files 