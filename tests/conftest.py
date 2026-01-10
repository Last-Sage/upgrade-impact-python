"""Test configuration."""

import pytest
from pathlib import Path


@pytest.fixture
def sample_project_dir(tmp_path):
    """Create a sample project directory."""
    return tmp_path / "sample_project"


@pytest.fixture
def sample_requirements(sample_project_dir):
    """Create a sample requirements.txt file."""
    sample_project_dir.mkdir(parents=True, exist_ok=True)
    
    req_file = sample_project_dir / "requirements.txt"
    req_file.write_text("""
requests==2.28.0
flask==2.0.0
pytest==7.0.0
numpy==1.24.0
""")
    
    return req_file


@pytest.fixture
def sample_python_file(sample_project_dir):
    """Create a sample Python file with imports."""
    sample_project_dir.mkdir(parents=True, exist_ok=True)
    
    py_file = sample_project_dir / "main.py"
    py_file.write_text("""
import requests
from flask import Flask

app = Flask(__name__)

def fetch_data():
    response = requests.get("https://api.example.com/data")
    return response.json()

if __name__ == "__main__":
    app.run()
""")
    
    return py_file
