#!/bin/bash
# Pre-build matplotlib font cache so first request doesn't block for 30+ seconds
set -e
pip install -r requirements.txt
python -c "
import os
os.environ.setdefault('MPLBACKEND', 'Agg')
import matplotlib
matplotlib.use('Agg')
import matplotlib.font_manager
matplotlib.font_manager._load_fontmanager()
print('Matplotlib font cache built')
"
