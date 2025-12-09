import subprocess
from pathlib import Path

def run():
    src_dir = Path(__file__).absolute().parent
    main_path = src_dir / "main.py"
    subprocess.run(["streamlit", "run", main_path])