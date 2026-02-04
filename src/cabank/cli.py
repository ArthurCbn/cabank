from pathlib import Path
import streamlit.web.bootstrap
from importlib import resources

def run():
    src_dir = Path(__file__).absolute().parent
    main_path = src_dir / "main.py"
    with resources.as_file(resources.files("cabank") / "main.py") as app_path:
        streamlit.web.bootstrap.run(
            main_script_path=str(app_path),
            is_hello=False,
            args=[],
            flag_options={}
        )