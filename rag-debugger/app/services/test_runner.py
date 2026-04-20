import subprocess
from typing import Tuple

def run_tests(sandbox_path: str) -> Tuple[bool, str]:
    """
    Executes pytest in the given sandbox directory.
    Returns (success_boolean, output_logs).
    """
    try:
        # We run pytest, capturing output
        result = subprocess.run(
            ["pytest"],
            cwd=sandbox_path,
            capture_output=True,
            text=True
        )
        
        output = result.stdout + "\n" + result.stderr
        success = (result.returncode == 0)
        return success, output
    except Exception as e:
        return False, f"Test runner failed to execute: {str(e)}"
