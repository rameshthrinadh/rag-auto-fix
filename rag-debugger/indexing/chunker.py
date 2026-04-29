import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

import tiktoken
import tree_sitter_languages
from typing import List, Dict, Any

tokenizer = tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    return len(tokenizer.encode(text))

def node_text(node, source_code: bytes) -> str:
    return source_code[node.start_byte:node.end_byte].decode('utf-8')

def extract_docstring(node, source_code: bytes) -> str:
    """Extracts the docstring from a function or class node."""
    if node.type in ['function_definition', 'class_definition']:
        body = node.child_by_field_name('body')
        if body and body.children:
            first_stmt = body.children[0]
            if first_stmt.type == 'expression_statement':
                expr = first_stmt.children[0]
                if expr.type == 'string':
                    return node_text(expr, source_code).strip('\'"')
    return ""

def extract_calls(node, source_code: bytes) -> List[str]:
    """Recursively finds all function calls within a node's body."""
    calls = []
    def walk(n):
        if n.type == 'call':
            func_node = n.child_by_field_name('function')
            if func_node:
                calls.append(node_text(func_node, source_code))
        for child in n.children:
            walk(child)
    
    # Exclude the node itself to avoid catching the definition as a call
    body = node.child_by_field_name('body')
    if body:
        walk(body)
        
    seen = set()
    return [c for c in calls if not (c in seen or seen.add(c))]

def extract_imports(tree, source_code: bytes) -> List[str]:
    """Finds all imports in the file to resolve external calls later."""
    imports = []
    def walk(n):
        if n.type == 'import_statement':
            for child in n.children:
                if child.type == 'dotted_name':
                    imports.append(node_text(child, source_code))
        elif n.type == 'import_from_statement':
            module_name_node = n.child_by_field_name('module_name')
            if module_name_node:
                imports.append(node_text(module_name_node, source_code))
        for child in n.children:
            walk(child)
    walk(tree.root_node)
    return list(set(imports))

def get_ast_chunks(file_content: str, file_path: str) -> List[Dict[str, Any]]:
    """
    Parses a python file content into structured entities using tree-sitter.
    Extracts classes, functions, and methods with their relationships.
    """
    # Simple heuristic for repo name, normally passed in from higher level
    parts = file_path.split('/')
    repo = parts[-3] if len(parts) >= 3 else "unknown_repo"
    
    try:
        parser = tree_sitter_languages.get_parser("python")
    except Exception as e:
        print(f"Error loading tree-sitter parser: {e}")
        return []

    source_bytes = file_content.encode('utf-8')
    tree = parser.parse(source_bytes)
    
    global_imports = extract_imports(tree, source_bytes)
    chunks = []
    
    def process_node(node, parent_name=None):
        if node.type in ['function_definition', 'class_definition']:
            name_node = node.child_by_field_name('name')
            name = node_text(name_node, source_bytes) if name_node else "anonymous"
            
            if parent_name:
                full_name = f"{parent_name}.{name}"
                entity_type = "method" if node.type == 'function_definition' else "class"
            else:
                full_name = name
                entity_type = "function" if node.type == 'function_definition' else "class"
            
            code = node_text(node, source_bytes)
            docstring = extract_docstring(node, source_bytes)
            calls = extract_calls(node, source_bytes)
            
            tokens = count_tokens(code)
            
            chunks.append({
                "repo": repo,
                "file": file_path,
                "entity_type": entity_type,
                "name": full_name,
                "code": code,
                "docstring": docstring,
                "imports": global_imports,
                "calls": calls,
                "called_by": [], # to be populated by graph linkage layer
                "external_calls": [], # to be populated by graph linkage layer
                "tokens": tokens,
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1
            })
            
            body = node.child_by_field_name('body')
            if body:
                for child in body.children:
                    process_node(child, full_name)
        else:
            for child in node.children:
                process_node(child, parent_name)
                
    process_node(tree.root_node)
    
    if not chunks and file_content.strip():
        chunks.append({
            "repo": repo,
            "file": file_path,
            "entity_type": "module",
            "name": "module",
            "code": file_content,
            "docstring": "",
            "imports": global_imports,
            "calls": extract_calls(tree.root_node, source_bytes) if tree.root_node else [],
            "called_by": [],
            "external_calls": [],
            "tokens": count_tokens(file_content),
            "start_line": 1,
            "end_line": len(file_content.splitlines())
        })
        
    return chunks
