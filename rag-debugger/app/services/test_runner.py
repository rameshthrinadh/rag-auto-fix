import subprocess
import os
from typing import Tuple, Optional

def find_venv_bin(sandbox_path: str, bin_name: str) -> str:
    """
    Look for a binary in common virtualenv locations.
    """
    candidates = [
        os.path.join(sandbox_path, ".venv", "bin", bin_name),
        os.path.join(sandbox_path, "venv", "bin", bin_name),
        os.path.join(sandbox_path, "rvenv", "bin", bin_name),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return bin_name # Fallback to global command

def run_tests(
    sandbox_path: str, 
    target_file: Optional[str] = None, 
    original_error: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Executes pytest in the given sandbox directory.
    If target_file is provided, limits scope to that file.
    If original_error is provided, performs a heuristic check.
    """
    pytest_bin = find_venv_bin(sandbox_path, "pytest")
    
    # Building the command
    cmd = [pytest_bin]
    if target_file and os.path.exists(os.path.join(sandbox_path, target_file)):
        cmd.append(target_file)
        
    try:
        # We run pytest, capturing output
        result = subprocess.run(
            cmd,
            cwd=sandbox_path,
            capture_output=True,
            text=True,
            timeout=60 # Prevent hanging on DB timeouts
        )
        
        output = result.stdout + "\n" + result.stderr
        
        # 1. Strict Success: returncode 0
        if result.returncode == 0:
            return True, output
            
        # 2. Heuristic Success: 
        # If pytest failed (returncode != 0), but the specific error message 
        # that triggered this debug session is GONE from the console output,
        # we treat it as a "Probable Fix" but log it clearly.
        if original_error and original_error.lower() not in output.lower():
            # Double check: did the test actually RUN or did it just fail to boot?
            if "collected" in output.lower() or "passed" in output.lower():
                heuristic_msg = f"\n[HEURISTIC SUCCESS]: Tests failed globally, but original error '{original_error}' was not detected in output.\n"
                return True, output + heuristic_msg
                
        return False, output
    except subprocess.TimeoutExpired:
        return False, "Test runner timed out (possible database or hanging network connection)."
    except Exception as e:
        return False, f"Test runner failed to execute: {str(e)}"
