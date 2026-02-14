"""
WSGI entry point for production deployment (Gunicorn, uWSGI, etc.).

Usage:
  gunicorn -w 4 -b 0.0.0.0:8000 wsgi:app

Environment variables for deployment:
  FLASK_ENV=production       Use ProductionConfig (DEBUG=False)
  USE_SAMPLE_DATA=false     Use real VNStock APIs (default)
  ENABLE_SELENIUM=false     Disable Vietstock Selenium fallback (default for cloud)
  USE_VNSTOCK_PRIMARY=true  Use VNStock as primary data source
"""
from app import create_app

app = create_app()
