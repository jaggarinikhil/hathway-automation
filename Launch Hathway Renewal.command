#!/bin/bash
# Hathway STB Renewal — Double-click launcher for macOS

# Go to the project folder
cd "$(dirname "$0")"

# Activate Anaconda Python environment
source ~/anaconda3/etc/profile.d/conda.sh
conda activate base

# Launch the web UI
python web_ui.py --config-file config.json
