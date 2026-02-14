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
# Must run before any imports that pull in matplotlib (vnstock/vnstock_ezchart)
# Prevents "Matplotlib is building the font cache" blocking first request on Render
import os
os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

# Warm up matplotlib font cache at worker startup (not on first request)
import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager
matplotlib.font_manager._load_fontmanager()

from app import create_app

app = create_app()
