import sys
from pathlib import Path

# Add cv_pipeline directory to sys.path
cv_pipeline_dir = Path(__file__).resolve().parent.parent
if str(cv_pipeline_dir) not in sys.path:
    sys.path.insert(0, str(cv_pipeline_dir))
