import ast
import os
import re
from typing import List, Dict, Any, Tuple

class SafetyValidator:
    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        self.sensitive_files = {".env", "config.py", "database.py", "db_conn", "secrets"}
        self.max_files_touched = 2
        self.max_deletion_ratio = 0.5 # If more than 50% of original block is deleted

    def validate_patch(self, patch_blocks: List[Dict[str, Any]], original_files_content: Dict[str, str]) -> Tuple[bool, str]:
        """
        Runs heuristics on the proposed patch before application.
        """
        touched_files = set()
        
        for block in patch_blocks:
            file_rel_path = block["file"]
            touched_files.add(file_rel_path)
            
            # Rule: Sensitive files
            if any(s in file_rel_path for s in self.sensitive_files):
                return False, f"Modification of sensitive file detected: {file_rel_path}"
            
            original_code = block["search"]
            replacement_code = block["replace"]
            
            # Rule: Signature Changes (Naive check)
            if self._detect_signature_change(original_code, replacement_code):
                return False, f"Function or Class signature change detected in {file_rel_path}. This is considered high risk."
            
            # Rule: Large Deletions
            if len(replacement_code.strip()) < len(original_code.strip()) * (1 - self.max_deletion_ratio):
                if len(original_code.splitlines()) > 5: # Only care if it was a substantial block
                    return False, f"Large code block deletion detected in {file_rel_path}."

        # Rule: Max files touched
        if len(touched_files) > self.max_files_touched:
            return False, f"Patch touches {len(touched_files)} files (max {self.max_files_touched} allowed for auto-fix)."

        return True, "Safe"

    def validate_syntax(self, file_content: str) -> Tuple[bool, str]:
        """
        Parses Python code to ensure it is syntactically valid.
        """
        try:
            ast.parse(file_content)
            return True, "Valid syntax"
        except SyntaxError as e:
            return False, f"Syntax Error: {e.msg} at line {e.lineno}"
        except Exception as e:
            return False, f"Parser Error: {str(e)}"

    def _detect_signature_change(self, original: str, replacement: str) -> bool:
        """
        Checks if 'def func(' or 'class Name(' lines are modified in their headers.
        """
        pattern = r"^\s*(?:def|class)\s+\w+\s*\(.*?\)\s*:"
        orig_heads = re.findall(pattern, original, re.MULTILINE)
        repl_heads = re.findall(pattern, replacement, re.MULTILINE)
        
        if not orig_heads:
            return False 
            
        if len(orig_heads) != len(repl_heads):
            return True
            
        for oh, rh in zip(orig_heads, repl_heads):
            if oh.strip() != rh.strip():
                return True
                
        return False
