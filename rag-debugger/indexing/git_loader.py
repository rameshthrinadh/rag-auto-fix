import os
import glob
from typing import List

def load_repo_files(repo_path: str, extensions: List[str] = ['.py']) -> List[str]:
    """
    Scans a given repository path and returns a list of absolute paths 
    to files matching the specified extensions.
    """
    if not os.path.exists(repo_path):
        raise FileNotFoundError(f"Repository path {repo_path} does not exist.")
        
    repo_path = os.path.abspath(repo_path)
    
    file_paths = []
    for root, dirs, files in os.walk(repo_path):
        # Ignore hidden folders or venvs more safely
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('venv', 'env', '__pycache__')]
            
        for file in files:
            if any(file.endswith(ext) for ext in extensions):
                file_paths.append(os.path.join(root, file))
                
    return file_paths

def read_file_content(file_path: str) -> str:
    """Reads and returns the content of a file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        return ""
