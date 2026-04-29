import os
import tempfile
import shutil
import subprocess
import logging
from typing import List, Dict, Any

logger = logging.getLogger("uvicorn.error")

def create_sandbox(repo_path: str) -> str:
    """
    Copies the original repository to a temporary directory 
    so we don't modify the user's primary code directly.
    """
    temp_dir = tempfile.mkdtemp(prefix="rag_debug_")
    sandbox_path = os.path.join(temp_dir, os.path.basename(repo_path))
    shutil.copytree(repo_path, sandbox_path)
    return sandbox_path

def get_patch_blocks(diff_content: str, repo_path: str = None) -> List[Dict[str, Any]]:
    """
    Parses the SEARCH/REPLACE blocks into a list of dictionaries for inspection.
    """
    blocks = diff_content.split("<<<< ")
    parsed = []
    
    for block in blocks[1:]:
        try:
            parts = block.split("\n", 1)
            if len(parts) < 2: continue
            
            file_path_rel = parts[0].strip()
            
            if repo_path:
                repo_basename = os.path.basename(repo_path)
                if os.path.isabs(file_path_rel):
                    if repo_basename in file_path_rel:
                        file_path_rel = file_path_rel.split(repo_basename + "/")[-1]
                if f"../{repo_basename}/" in file_path_rel:
                    file_path_rel = file_path_rel.split(f"{repo_basename}/")[-1]

            rest = parts[1]
            
            if "====\n" not in rest or ">>>>" not in rest:
                continue
                
            search_part, replace_raw = rest.split("====\n", 1)
            search_str = search_part.rstrip("\n")
            replace_str = replace_raw.split(">>>>")[0].rstrip("\n")
            
            parsed.append({
                "file": file_path_rel,
                "search": search_str,
                "replace": replace_str
            })
        except Exception:
            continue
    return parsed


def apply_patch(sandbox_path: str, diff_content: str) -> bool:
    """
    Applies the generated SEARCH/REPLACE blocks natively to the source.
    """
    logger.info(f"Triggering native block parser targeting: {sandbox_path}")
    
    # Split by <<<< to find blocks, but handle potential prefix text
    blocks = diff_content.split("<<<< ")
    if len(blocks) <= 1:
        logger.error("No valid search/replace blocks found in LLM output.")
        return False
        
    success = True
    for block in blocks[1:]:
        try:
            parts = block.split("\n", 1)
            if len(parts) < 2: continue
            
            file_path_rel = parts[0].strip()
            
            # Dynamically trap absolute path hallucinations
            repo_basename = os.path.basename(sandbox_path)
            if file_path_rel.startswith(sandbox_path):
                file_path_rel = file_path_rel[len(sandbox_path):].lstrip("/")
            elif os.path.isabs(file_path_rel):
                if repo_basename in file_path_rel:
                    file_path_rel = file_path_rel.split(repo_basename + "/")[-1]
            
            # Trap relative path hallucinations that escape and re-enter the repo
            if f"../{repo_basename}/" in file_path_rel:
                file_path_rel = file_path_rel.split(f"{repo_basename}/")[-1]
                    
            rest = parts[1]
            
            if "====\n" not in rest or ">>>>" not in rest:
                logger.error(f"Malformed block for {file_path_rel}")
                success = False
                continue
                
            search_part, replace_raw = rest.split("====\n", 1)
            search_str = search_part.rstrip("\n")
            
            # Extract replace string and handle trailing >>>>
            replace_str = replace_raw.split(">>>>")[0].rstrip("\n")
            
            full_path = os.path.join(sandbox_path, file_path_rel)
            if not os.path.exists(full_path):
                logger.error(f"Target file not found explicitly: {full_path}")
                success = False
                continue
                
            with open(full_path, 'r', encoding='utf-8') as f:
                file_lines = f.readlines()
            
            search_lines = search_str.splitlines()
            
            # Try exact match first
            file_content = "".join(file_lines)
            if search_str in file_content:
                new_content = file_content.replace(search_str, replace_str, 1)
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                logger.info(f"Exact match processed for: {file_path_rel}")
                continue

            # Fallback: Robust line-by-line matching (ignoring indentation)
            matched_start_index = -1
            search_len = len(search_lines)
            
            if search_len == 0:
                logger.error(f"Empty search block for {file_path_rel}")
                success = False
                continue

            for i in range(len(file_lines) - search_len + 1):
                match = True
                for j in range(search_len):
                    # Collapse multiple spaces and ignore leading/trailing whitespace
                    file_line_norm = " ".join(file_lines[i + j].split())
                    search_line_norm = " ".join(search_lines[j].split())
                    
                    if file_line_norm != search_line_norm:
                        match = False
                        break
                if match:
                    matched_start_index = i
                    break
            
            if matched_start_index != -1:
                logger.info(f"Fuzzy match found for {file_path_rel} at line {matched_start_index + 1}")
                
                # Reconstruct file with replacement
                new_lines = file_lines[:matched_start_index] + [replace_str + "\n"] + file_lines[matched_start_index + search_len:]
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.writelines(new_lines)
                logger.info(f"Fuzzy match processed for: {file_path_rel}")
            else:
                logger.error(f"Could not locate matching target string (even fuzzy) in {file_path_rel}")
                success = False
                
        except Exception as e:
            logger.exception(f"Parsing block exception execution failed entirely: {e}")
            success = False
            
    return success
