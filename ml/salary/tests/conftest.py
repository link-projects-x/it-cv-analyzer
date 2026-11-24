import sys
from pathlib import Path

# The modules in ml/salary/ are flat scripts (SageMaker script mode puts source_dir on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
