"""AST-based code analysis for import and usage detection with alias support."""

import ast
import logging
from pathlib import Path
from typing import Any

from upgrade_analyzer.models import CallSite, UsageNode

logger = logging.getLogger(__name__)


class ASTAnalyzer:
    """Analyzes Python code using AST to detect imports and usage."""
    
    def __init__(self, file_path: Path) -> None:
        """Initialize AST analyzer.
        
        Args:
            file_path: Path to Python file to analyze
        """
        self.file_path = file_path
        self._tree: ast.Module | None = None
        self._import_aliases: dict[str, str] = {}  # alias -> full.module.path
        self._symbol_aliases: dict[str, str] = {}  # alias -> full.symbol.path
    
    def _parse_file(self) -> ast.Module | None:
        """Parse file into AST.
        
        Returns:
            AST module or None if parsing fails
        """
        if self._tree is not None:
            return self._tree
        
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                code = f.read()
            
            self._tree = ast.parse(code, filename=str(self.file_path))
            self._build_alias_maps()
            return self._tree
        
        except SyntaxError as e:
            logger.warning(f"Syntax error in {self.file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error parsing {self.file_path}: {e}")
            return None
    
    def _build_alias_maps(self) -> None:
        """Build maps of import aliases to their full paths."""
        if self._tree is None:
            return
        
        for node in ast.walk(self._tree):
            # Handle "import package as alias"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.asname:
                        # e.g., import requests as req -> req -> requests
                        self._import_aliases[alias.asname] = alias.name
                    else:
                        # e.g., import requests -> requests -> requests
                        self._import_aliases[alias.name] = alias.name
            
            # Handle "from package import symbol as alias"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for alias in node.names:
                        symbol_name = alias.name
                        local_name = alias.asname if alias.asname else alias.name
                        
                        if symbol_name != "*":
                            # e.g., from requests import get as fetch -> fetch -> requests.get
                            full_path = f"{node.module}.{symbol_name}"
                            self._symbol_aliases[local_name] = full_path
    
    def extract_imports(self) -> dict[str, list[UsageNode]]:
        """Extract all imports from the file.
        
        Returns:
            Dictionary mapping package names to imported symbols
        """
        tree = self._parse_file()
        
        if tree is None:
            return {}
        
        imports: dict[str, list[UsageNode]] = {}
        
        for node in ast.walk(tree):
            # Handle "import package" and "import package as alias"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    package_name = alias.name.split(".")[0]
                    
                    if package_name not in imports:
                        imports[package_name] = []
                    
                    imports[package_name].append(
                        UsageNode(
                            package_name=package_name,
                            symbol_path=alias.name,
                            file_path=self.file_path,
                            line_numbers=[node.lineno],
                        )
                    )
            
            # Handle "from package import symbol"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    package_name = node.module.split(".")[0]
                    
                    if package_name not in imports:
                        imports[package_name] = []
                    
                    for alias in node.names:
                        symbol_name = alias.name
                        
                        # Build full symbol path
                        if symbol_name == "*":
                            symbol_path = f"{node.module}.*"
                        else:
                            symbol_path = f"{node.module}.{symbol_name}"
                        
                        imports[package_name].append(
                            UsageNode(
                                package_name=package_name,
                                symbol_path=symbol_path,
                                file_path=self.file_path,
                                line_numbers=[node.lineno],
                            )
                        )
        
        return imports
    
    def find_symbol_usage(self, symbol_path: str) -> list[CallSite]:
        """Find all places where a symbol is used.
        
        Args:
            symbol_path: Full symbol path (e.g., "requests.get")
            
        Returns:
            List of call sites
        """
        tree = self._parse_file()
        
        if tree is None:
            return []
        
        call_sites: list[CallSite] = []
        
        # Split symbol path to get module and function
        parts = symbol_path.split(".")
        
        if len(parts) < 2:
            return call_sites
        
        module_name = ".".join(parts[:-1])
        func_name = parts[-1]
        
        # Walk AST looking for function calls
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Check if this is a call to our symbol
                if self._is_matching_call(node.func, module_name, func_name, symbol_path):
                    call_site = self._extract_call_info(node, symbol_path)
                    if call_site:
                        call_sites.append(call_site)
        
        return call_sites
    
    def _is_matching_call(
        self,
        func_node: ast.expr,
        module_name: str,
        func_name: str,
        full_symbol_path: str
    ) -> bool:
        """Check if function call matches the symbol we're looking for.
        
        Args:
            func_node: AST node representing the function
            module_name: Expected module name
            func_name: Expected function name
            full_symbol_path: Full expected symbol path
            
        Returns:
            True if this is a match
        """
        # Handle "module.func()" pattern (e.g., requests.get())
        if isinstance(func_node, ast.Attribute):
            if func_node.attr == func_name:
                # Check if the value is the module (directly or via alias)
                if isinstance(func_node.value, ast.Name):
                    value_name = func_node.value.id
                    
                    # Direct match: requests.get()
                    if value_name == module_name.split(".")[0]:
                        return True
                    
                    # Alias match: req.get() where req = requests
                    resolved = self._import_aliases.get(value_name)
                    if resolved and resolved.split(".")[0] == module_name.split(".")[0]:
                        return True
        
        # Handle "func()" pattern (imported directly, e.g., from requests import get; get())
        elif isinstance(func_node, ast.Name):
            local_name = func_node.id
            
            # Direct match
            if local_name == func_name:
                # Check if it was imported from the right module
                resolved = self._symbol_aliases.get(local_name)
                if resolved == full_symbol_path:
                    return True
                # Also match if no alias tracking (simpler case)
                if local_name == func_name and not resolved:
                    return True
        
        return False
    
    def _extract_call_info(
        self,
        call_node: ast.Call,
        symbol: str
    ) -> CallSite | None:
        """Extract information from a function call.
        
        Args:
            call_node: AST Call node
            symbol: Symbol being called
            
        Returns:
            CallSite or None
        """
        try:
            # Extract arguments
            positional_args = []
            keyword_args = {}
            
            for arg in call_node.args:
                positional_args.append(self._ast_to_string(arg))
            
            for keyword in call_node.keywords:
                if keyword.arg:
                    keyword_args[keyword.arg] = self._ast_to_string(keyword.value)
            
            return CallSite(
                symbol=symbol,
                file_path=self.file_path,
                line_number=call_node.lineno,
                positional_args=positional_args,
                keyword_args=keyword_args,
            )
        
        except Exception as e:
            logger.debug(f"Error extracting call info: {e}")
            return None
    
    def _ast_to_string(self, node: ast.expr) -> str:
        """Convert AST node to string representation.
        
        Args:
            node: AST node
            
        Returns:
            String representation
        """
        try:
            return ast.unparse(node)
        except Exception:
            return "<unknown>"
    
    def count_function_calls(self, function_name: str) -> int:
        """Count how many times a function is called (including via aliases).
        
        Args:
            function_name: Name of function to count
            
        Returns:
            Number of calls
        """
        tree = self._parse_file()
        
        if tree is None:
            return 0
        
        count = 0
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Check function name (direct call)
                if isinstance(node.func, ast.Name):
                    if node.func.id == function_name:
                        count += 1
                    # Check if it's an alias for our function
                    resolved = self._symbol_aliases.get(node.func.id, "")
                    if resolved.endswith(f".{function_name}"):
                        count += 1
                        
                elif isinstance(node.func, ast.Attribute):
                    if node.func.attr == function_name:
                        count += 1
        
        return count
    
    def get_all_function_calls(self) -> dict[str, list[int]]:
        """Get all function calls with their line numbers.
        
        Returns:
            Dictionary mapping symbol paths to line numbers
        """
        tree = self._parse_file()
        
        if tree is None:
            return {}
        
        calls: dict[str, list[int]] = {}
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                symbol_path = self._resolve_call_symbol(node.func)
                
                if symbol_path:
                    if symbol_path not in calls:
                        calls[symbol_path] = []
                    calls[symbol_path].append(node.lineno)
        
        return calls
    
    def _resolve_call_symbol(self, func_node: ast.expr) -> str | None:
        """Resolve the full symbol path for a function call.
        
        Args:
            func_node: AST node representing the function
            
        Returns:
            Full symbol path or None
        """
        try:
            if isinstance(func_node, ast.Name):
                # Direct function call - check aliases
                local_name = func_node.id
                return self._symbol_aliases.get(local_name, local_name)
            
            elif isinstance(func_node, ast.Attribute):
                # module.function call
                if isinstance(func_node.value, ast.Name):
                    module_alias = func_node.value.id
                    func_name = func_node.attr
                    
                    # Resolve module alias
                    module_name = self._import_aliases.get(module_alias, module_alias)
                    
                    return f"{module_name}.{func_name}"
            
            return None
            
        except Exception:
            return None
