from setuptools import setup, find_packages

setup(
    name="cabank",
    version="1.0.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "streamlit>=1.51.0",
        "pandas",
        "plotly",
        "streamlit-calendar",
    ],
    entry_points={
        "console_scripts": [
            "cabank=cabank.cli:run"
        ]
    },
    author="Arthur Cabon",
    description="Outil pour faire ses comptes",
    python_requires=">=3.8"
)
