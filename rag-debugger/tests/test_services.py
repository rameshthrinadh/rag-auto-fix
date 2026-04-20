import pytest
import os
import tempfile
import json
from unittest.mock import patch

from app.services.context_builder import build_context
from app.services.patcher import create_sandbox, apply_patch
# We can mock retriever to avoid needing an actual FAISS index in the unit test
from app.services.retriever import Retriever

def test_context_builder():
    error = "ZeroDivisionError: division by zero"
    stacktrace = "Traceback (most recent call last):\n  File \"test.py\", line 2, in <module>\n    1/0"
    file = "test.py"
    line = 2
    chunks = [{"file": "test.py", "name": "dummy_func", "type": "function", "code": "def dummy_func():\n    return 1/0"}]
    snippet = "1  def dummy_func():\n2      return 1/0"
    
    result = build_context(error, stacktrace, file, line, chunks, snippet)
    
    assert "ZeroDivisionError" in result
    assert "dummy_func" in result
    assert "1/0" in result
    assert "test.py:2" in result

def test_patcher_sandbox():
    with tempfile.TemporaryDirectory() as src_dir:
        with open(os.path.join(src_dir, 'dummy.txt'), 'w') as f:
            f.write("test")
            
        sandbox_path = create_sandbox(src_dir)
        
        assert os.path.exists(sandbox_path)
        assert os.path.exists(os.path.join(sandbox_path, 'dummy.txt'))
        
def test_patcher_apply_patch():
    with tempfile.TemporaryDirectory() as src_dir:
        # Create a basic file
        file_path = os.path.join(src_dir, 'main.py')
        with open(file_path, 'w') as f:
            f.write("def add(a, b):\n    return a - b\n") # Intentional bug
            
        sandbox_path = create_sandbox(src_dir)
        
        # We need a unified diff
        diff = '''--- a/main.py
+++ b/main.py
@@ -1,2 +1,2 @@
 def add(a, b):
-    return a - b
+    return a + b
'''
        
        success = apply_patch(sandbox_path, diff)
        
        # Verification
        assert success == True
        with open(os.path.join(sandbox_path, 'main.py'), 'r') as f:
            content = f.read()
            assert "return a + b" in content

@patch('app.services.retriever.faiss')
@patch('app.services.retriever.os.path.exists')
def test_retriever_initialization_mocked(mock_exists, mock_faiss):
    mock_exists.return_value = False # Simulate no index present
    
    r = Retriever()
    assert r.index is None
    assert r.metadata == {}
    
    res = r.search("dummy")
    assert res == []
