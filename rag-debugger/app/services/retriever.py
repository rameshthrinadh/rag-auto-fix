import logging
import os
import pickle
import faiss
import numpy as np
import re
from typing import List, Dict, Any, Optional, Tuple

from app.core.config import settings
from app.core.constants import TOP_K_RESULTS, CONTEXT_LINE_PADDING
from indexing.indexer import get_embeddings_batch # using the batch function for single embed too

INFRASTRUCTURE_KEYWORDS = {"db_conn", "telemetry", "middleware", "__init__", "logger", "metrics", "env", "venv", "site-packages", "cursors.py", "connections.py", "pymysql"}

class Retriever:
    def __init__(self):
        self.index = None
        self.metadata = []
        self._load_index()
        
    def _load_index(self):
        if not os.path.exists(settings.FAISS_INDEX_PATH):
            return
            
        self.index = faiss.read_index(settings.FAISS_INDEX_PATH)
        if os.path.exists(settings.INDEX_METADATA_PATH):
            with open(settings.INDEX_METADATA_PATH, 'rb') as f:
                self.metadata = pickle.load(f)

    def extract_keywords_from_trace(self, stacktrace: str, file_name: Optional[str]) -> List[Dict[str, Any]]:
        """
        Extracts filenames and function names from the trace with weights.
        Returns a list of dictionaries: {"val": str, "weight": int, "type": "file"|"func"}
        """
        results = []
        if file_name:
            results.append({"val": os.path.basename(file_name), "weight": 10, "type": "file"})
            
        lines = stacktrace.splitlines()
        for i, line in enumerate(lines):
            # Format:   File "/path/to/script.py", line 42, in my_func
            if "File \"" in line and "\", line " in line:
                try:
                    path = line.split('"')[1]
                    fname = os.path.basename(path)
                    
                    # Weight based on proximity to the bottom (last repo file is better)
                    # We'll use index in lines as a proxy
                    base_weight = 5 + (i / len(lines)) * 10
                    
                    results.append({"val": fname, "weight": base_weight, "type": "file"})
                    
                    if ", in " in line:
                        func_name = line.split(", in ")[1].strip()
                        if func_name not in ["<module>", "__init__"]:
                            results.append({"val": func_name, "weight": base_weight * 3, "type": "func"})
                except IndexError:
                    pass
        return results

    def is_infrastructure(self, file_path: str) -> bool:
        """Helper to check if a file path belongs to infrastructure."""
        return any(kw in file_path.lower() for kw in INFRASTRUCTURE_KEYWORDS)

    def extract_primary_location(self, stacktrace: str, repo_path: str) -> Tuple[Optional[str], Optional[int]]:
        """
        Parses the stacktrace to find the most relevant (innermost) file/line 
        that exists within the current repo_path, prioritizing 'application' logic
        over 'infrastructure' drivers/wrappers.
        """
        all_locations = self.extract_all_repo_locations(stacktrace, repo_path)
        if not all_locations:
            return None, None
            
        # Try to find the deepest one that is NOT infrastructure
        for loc in reversed(all_locations):
            path = loc['file']
            is_infra = any(kw in path.lower() for kw in INFRASTRUCTURE_KEYWORDS)
            if not is_infra:
                return loc['file'], loc['line']
        
        # Fallback to the absolute innermost repo file if everything is infra
        innermost = all_locations[-1]
        return innermost['file'], innermost['line']

    def extract_all_repo_locations(self, stacktrace: str, repo_path: str) -> List[Dict[str, Any]]:
        """
        Extracts all file/line pairs from the stacktrace that exist inside the repo.
        Returns list from outermost to innermost: [{"file": "rel/path", "line": 42}, ...]
        """
        results = []
        lines = stacktrace.strip().splitlines()
        for line in lines:
            if "File \"" in line and "\", line " in line:
                try:
                    path = line.split('"')[1]
                    line_num_str = line.split(", line ")[1].split(",")[0].split()[0]
                    line_num = int(line_num_str)
                    
                    if path.startswith(repo_path) and os.path.exists(path):
                        rel_path = os.path.relpath(path, repo_path)
                        results.append({"file": rel_path, "line": line_num})
                except (IndexError, ValueError):
                    continue
        return results

    def search(self, error: str, stacktrace: str, file_name: Optional[str] = None, top_k: int = TOP_K_RESULTS) -> List[Dict[str, Any]]:
        """
        Embeds the query and fetches the top matched chunks. 
        Then expands context using Graph DB and reranks based on exact keyword hits.
        """
        if not self.index or self.index.ntotal == 0:
            return []
            
        query = f"{error}\n{stacktrace}"
        
        # We fetch extra chunks for hybrid reranking locally
        search_k = max(top_k * 3, 10)
        
        # Using batch function with 1 item safely
        query_embs = get_embeddings_batch([query], settings.EMBEDDING_MODEL)
        query_np = np.array(query_embs).astype('float32')
        
        distances, indices = self.index.search(query_np, search_k)
        
        candidates = []
        for idx in indices[0]:
            if idx != -1:
                # Metadata is a list, safely access by index
                if isinstance(self.metadata, list):
                    if 0 <= idx < len(self.metadata):
                        candidates.append(self.metadata[idx])
                elif isinstance(self.metadata, dict):
                    str_idx = str(idx)
                    if str_idx in self.metadata:
                        candidates.append(self.metadata[str_idx])
                        
        # --- Context Expansion via Graph DB ---
        from indexing.graph_store import load_graph
        graph = load_graph()
        
        expanded_results = {}
        for c in candidates:
            node_id = c.get('node_id')
            if not node_id:
                node_id = f"{c.get('repo')}/{c.get('file')}/{c.get('name')}"
                
            expanded_results[node_id] = c
            
            # Graph Traversal (Depth 1 expansion: CALLED, BELONGS_TO)
            if graph.has_node(node_id):
                # Outgoing edges (what this function calls)
                for neighbor in graph.successors(node_id):
                    if neighbor not in expanded_results:
                        for m in (self.metadata if isinstance(self.metadata, list) else self.metadata.values()):
                            if m.get('node_id') == neighbor or f"{m.get('repo')}/{m.get('file')}/{m.get('name')}" == neighbor:
                                expanded_results[neighbor] = m
                                break
                
                # Incoming edges (parents/callers)
                for neighbor in graph.predecessors(node_id):
                    if neighbor not in expanded_results:
                        for m in (self.metadata if isinstance(self.metadata, list) else self.metadata.values()):
                            if m.get('node_id') == neighbor or f"{m.get('repo')}/{m.get('file')}/{m.get('name')}" == neighbor:
                                expanded_results[neighbor] = m
                                break

        results = list(expanded_results.values())
        # ------------------------------------
                    
        # Filter and rank using intelligent keywords (file basenames + function names)
        keywords = self.extract_keywords_from_trace(stacktrace, file_name)
        
        def rank_score(chunk):
            score = 0
            chunk_file = chunk.get("file", "")
            chunk_name = chunk.get("name", "")
            
            # Absolute anchoring boost for the primary file path
            if file_name and file_name in chunk_file:
                score += 50
                
            for kw in keywords:
                if kw["type"] == "file" and kw["val"] in chunk_file:
                    score += kw["weight"]
                if kw["type"] == "func" and kw["val"] == chunk_name:
                    # Higher weight for exact function match
                    score += kw["weight"] * 2
            return score
            
        results.sort(key=rank_score, reverse=True)
        
        # Logging top hit for observability
        if results:
            top = results[0]
            logger = logging.getLogger("uvicorn.error")
            logger.info(f"Top FAISS Hit: {top.get('file')}:{top.get('name')} (Score: {rank_score(top)})")
                    
        return results[:top_k]

    def get_file_snippet(self, file_path: str, line_number: int, padding: int = CONTEXT_LINE_PADDING) -> str:
        """
        Fetches the exact lines around the error from the file.
        Attempts to find the enclosing AST function/class to provide full logical context.
        Falls back to +/- padding if parsing fails or for non-Python files.
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                src = f.read()
                lines = src.splitlines()

            # Try AST parsing for .py files
            if file_path.endswith('.py'):
                import ast
                try:
                    tree = ast.parse(src)
                    
                    class NodeFinder(ast.NodeVisitor):
                        def __init__(self, target_line):
                            self.target_line = target_line
                            self.best_match = None
                            
                        def generic_visit(self, node):
                            if hasattr(node, 'lineno'):
                                start = node.lineno
                                end = getattr(node, 'end_lineno', start)
                                if start <= self.target_line <= end:
                                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                                        self.best_match = node
                            super().generic_visit(node)
                            
                    finder = NodeFinder(line_number)
                    finder.visit(tree)
                    
                    if finder.best_match:
                        node = finder.best_match
                        start = max(0, node.lineno - 1)
                        end = min(len(lines), getattr(node, 'end_lineno', node.lineno))
                        
                        # Guard rail for monstrous functions (> 400 lines)
                        if (end - start) <= 400:
                            return "\n".join(lines[start:end]) + "\n"
                        else:
                            logger = logging.getLogger("uvicorn.error")
                            logger.debug(f"AST node for {file_path} is too large ({end-start} lines), falling back to padding.")
                except Exception as ast_err:
                    logger = logging.getLogger("uvicorn.error")
                    logger.debug(f"AST extraction failed for {file_path}, falling back to padding. Error: {ast_err}")

            # Fallback to naive padding (biased upward to catch variable definitions like SQL queries)
            start = max(0, line_number - (padding * 5) - 1)
            end = min(len(lines), line_number + padding)
            
            snippet_lines = lines[start:end]
            return "\n".join(snippet_lines) + "\n"
        except Exception as e:
            return f"Could not read snippet from {file_path}: {e}"
