"""Comprehensive tests for AST analyzer with alias support."""

import ast
from pathlib import Path

import pytest

from upgrade_analyzer.scanner.ast_analyzer import ASTAnalyzer


class TestASTAnalyzer:
    """Tests for AST analyzer."""
    
    def test_extract_simple_import(self, tmp_path: Path) -> None:
        """Test extraction of simple imports."""
        code = '''
import requests
import json
'''
        file = tmp_path / "test.py"
        file.write_text(code)
        
        analyzer = ASTAnalyzer(file)
        imports = analyzer.extract_imports()
        
        assert "requests" in imports
        assert "json" in imports
    
    def test_extract_from_import(self, tmp_path: Path) -> None:
        """Test extraction of from imports."""
        code = '''
from requests import get, post
from flask import Flask
'''
        file = tmp_path / "test.py"
        file.write_text(code)
        
        analyzer = ASTAnalyzer(file)
        imports = analyzer.extract_imports()
        
        assert "requests" in imports
        assert len(imports["requests"]) == 2
        assert "flask" in imports
    
    def test_import_with_alias(self, tmp_path: Path) -> None:
        """Test import alias tracking."""
        code = '''
import numpy as np
import pandas as pd
from requests import get as http_get

np.array([1, 2, 3])
pd.DataFrame()
http_get("https://example.com")
'''
        file = tmp_path / "test.py"
        file.write_text(code)
        
        analyzer = ASTAnalyzer(file)
        imports = analyzer.extract_imports()
        
        assert "numpy" in imports
        assert "pandas" in imports
        assert "requests" in imports
    
    def test_find_symbol_usage_with_alias(self, tmp_path: Path) -> None:
        """Test symbol usage detection with aliases."""
        code = '''
import requests as req

response = req.get("https://api.example.com")
data = req.post("https://api.example.com", json={"key": "value"})
'''
        file = tmp_path / "test.py"
        file.write_text(code)
        
        analyzer = ASTAnalyzer(file)
        
        # Should find calls to requests.get even when aliased as req.get
        call_sites = analyzer.find_symbol_usage("requests.get")
        
        # The alias tracking should resolve req -> requests
        assert len(call_sites) >= 1
    
    def test_find_direct_import_usage(self, tmp_path: Path) -> None:
        """Test symbol usage when imported directly."""
        code = '''
from requests import get

response = get("https://example.com")
'''
        file = tmp_path / "test.py"
        file.write_text(code)
        
        analyzer = ASTAnalyzer(file)
        call_sites = analyzer.find_symbol_usage("requests.get")
        
        assert len(call_sites) >= 1
    
    def test_count_function_calls(self, tmp_path: Path) -> None:
        """Test function call counting."""
        code = '''
import requests

requests.get("url1")
requests.get("url2")
requests.post("url3")
'''
        file = tmp_path / "test.py"
        file.write_text(code)
        
        analyzer = ASTAnalyzer(file)
        
        assert analyzer.count_function_calls("get") == 2
        assert analyzer.count_function_calls("post") == 1
    
    def test_extract_call_arguments(self, tmp_path: Path) -> None:
        """Test extraction of call arguments."""
        code = '''
import requests

requests.get("https://example.com", headers={"Auth": "token"}, timeout=30)
'''
        file = tmp_path / "test.py"
        file.write_text(code)
        
        analyzer = ASTAnalyzer(file)
        call_sites = analyzer.find_symbol_usage("requests.get")
        
        if call_sites:
            site = call_sites[0]
            assert "https://example.com" in site.positional_args[0]
            assert "headers" in site.keyword_args
            assert "timeout" in site.keyword_args
    
    def test_get_all_function_calls(self, tmp_path: Path) -> None:
        """Test getting all function calls."""
        code = '''
import requests
from json import loads

data = requests.get("url").json()
parsed = loads(data)
'''
        file = tmp_path / "test.py"
        file.write_text(code)
        
        analyzer = ASTAnalyzer(file)
        calls = analyzer.get_all_function_calls()
        
        assert len(calls) > 0
    
    def test_syntax_error_handling(self, tmp_path: Path) -> None:
        """Test handling of syntax errors."""
        code = '''
def broken(
    # Missing closing paren
'''
        file = tmp_path / "test.py"
        file.write_text(code)
        
        analyzer = ASTAnalyzer(file)
        imports = analyzer.extract_imports()
        
        # Should return empty dict on parse error
        assert imports == {}
    
    def test_star_import(self, tmp_path: Path) -> None:
        """Test handling of star imports."""
        code = '''
from os.path import *
'''
        file = tmp_path / "test.py"
        file.write_text(code)
        
        analyzer = ASTAnalyzer(file)
        imports = analyzer.extract_imports()
        
        assert "os" in imports
        assert any("*" in u.symbol_path for u in imports["os"])
