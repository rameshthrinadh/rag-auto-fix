import os
from typing import List, Dict
import re

def generate_repo_map(repo_path: str, output_path: str):
    """
    Generates a high-level overview of the repository.
    Includes:
    - Directory structure (depth limited)
    - Key architectural patterns
    - Major dependencies
    - Summary of module purposes
    """
    repo_path = os.path.abspath(repo_path)
    lines = [f"# Repository Map: {os.path.basename(repo_path)}", ""]
    
    # 1. Directory Tree
    lines.append("## Project Structure")
    lines.append("```")
    lines.extend(_get_tree_structure(repo_path, max_depth=3))
    lines.append("```")
    lines.append("")
    
    # 2. Tech Stack Detection
    lines.append("## Tech Stack")
    stack = _detect_stack(repo_path)
    for k, v in stack.items():
        lines.append(f"- **{k}**: {v}")
    lines.append("")
    
    # 3. Module Summaries
    lines.append("## Key Modules")
    summaries = _generate_summaries(repo_path)
    for module, summary in summaries.items():
        lines.append(f"### {module}")
        lines.append(summary)
        lines.append("")
        
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Global repo map generated at {output_path}")

def _get_tree_structure(path: str, prefix: str = "", max_depth: int = 3, current_depth: int = 0) -> List[str]:
    if current_depth > max_depth:
        return ["  ... (max depth reached)"]
        
    tree = []
    try:
        items = sorted(os.listdir(path))
    except PermissionError:
        return []
        
    # Filter items
    items = [i for i in items if not i.startswith('.') and i not in ('venv', 'env', '__pycache__', 'node_modules')]
    
    for i, item in enumerate(items):
        full_path = os.path.join(path, item)
        connector = "└── " if i == len(items) - 1 else "├── "
        tree.append(f"{prefix}{connector}{item}")
        
        if os.path.isdir(full_path):
            new_prefix = prefix + ("    " if i == len(items) - 1 else "│   ")
            tree.extend(_get_tree_structure(full_path, new_prefix, max_depth, current_depth + 1))
            
    return tree

def _detect_stack(repo_path: str) -> Dict[str, str]:
    stack = {
        "Language": "Python",
        "Framework": "Unknown",
        "Database": "Unknown",
    }
    
    # Deep scan for config files
    relevant_files = []
    for root, _, fs in os.walk(repo_path):
        if any(d in root for d in ['.venv', 'venv', 'node_modules', '__pycache__']):
            continue
        for f in fs:
            if f in ['requirements.txt', 'pyproject.toml', 'app.py', 'main.py', 'config.py']:
                relevant_files.append(os.path.join(root, f))
        if len(relevant_files) > 50: break
        
    for fpath in relevant_files:
        try:
            with open(fpath, "r", errors='ignore') as f:
                content = f.read().lower()
                if "flask" in content: stack["Framework"] = "Flask"
                if "fastapi" in content or "uvicorn" in content: stack["Framework"] = "FastAPI"
                if "pymysql" in content or "mysql" in content: stack["Database"] = "MySQL"
                if "sqlalchemy" in content: stack["ORM"] = "SQLAlchemy"
                if "celery" in content: stack["Task Queue"] = "Celery"
        except:
            continue
        
    return stack

def _generate_summaries(repo_path: str) -> Dict[str, str]:
    summaries = {}
    # Look for top level README
    readme_path = os.path.join(repo_path, "README.md")
    if os.path.exists(readme_path):
        try:
            with open(readme_path, "r") as f:
                content = f.read(500)
                summaries["Project Overview"] = content.split('\n')[0] + " (from README.md)"
        except:
            pass

    base_dirs = ["services", "app", "src", "api", "utils"]
    for d in base_dirs:
        full_path = os.path.join(repo_path, d)
        if os.path.exists(full_path) and os.path.isdir(full_path):
            subdirs = [s for s in os.listdir(full_path) if os.path.isdir(os.path.join(full_path, s)) and not s.startswith('.')]
            summaries[d] = f"Core directory containing: {', '.join(subdirs[:10])}"
            
    return summaries
