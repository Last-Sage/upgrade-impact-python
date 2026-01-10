"""Usage mapper to build surface area map of package usage."""

from collections import defaultdict
from pathlib import Path

from upgrade_analyzer.models import UsageNode
from upgrade_analyzer.scanner.ast_analyzer import ASTAnalyzer
from upgrade_analyzer.scanner.file_discovery import FileDiscovery


class UsageMapper:
    """Maps package usage across a codebase."""
    
    def __init__(self, project_root: Path) -> None:
        """Initialize usage mapper.
        
        Args:
            project_root: Root directory of the project
        """
        self.project_root = project_root
        self.file_discovery = FileDiscovery(project_root)
    
    def map_package_usage(self, package_name: str) -> list[UsageNode]:
        """Map all usage of a package in the codebase.
        
        Args:
            package_name: Name of package to map
            
        Returns:
            List of usage nodes
        """
        usage_nodes: list[UsageNode] = []
        
        # Find all Python files
        python_files = self.file_discovery.find_python_files()
        
        # Analyze each file
        for file_path in python_files:
            analyzer = ASTAnalyzer(file_path)
            imports = analyzer.extract_imports()
            
            # Check if this file imports the package
            if package_name in imports:
                for usage_node in imports[package_name]:
                    # Count usage of each symbol
                    symbol = usage_node.symbol_path.split(".")[-1]
                    usage_node.call_count = analyzer.count_function_calls(symbol)
                    
                    usage_nodes.append(usage_node)
        
        return usage_nodes
    
    def map_all_usage(self) -> dict[str, list[UsageNode]]:
        """Map usage of all packages in the codebase.
        
        Returns:
            Dictionary mapping package names to usage nodes
        """
        all_usage: dict[str, list[UsageNode]] = defaultdict(list)
        
        # Find all Python files
        python_files = self.file_discovery.find_python_files()
        
        # Analyze each file
        for file_path in python_files:
            analyzer = ASTAnalyzer(file_path)
            imports = analyzer.extract_imports()
            
            # Add all imports to usage map
            for package_name, usage_nodes in imports.items():
                for usage_node in usage_nodes:
                    # Count usage
                    symbol = usage_node.symbol_path.split(".")[-1]
                    usage_node.call_count = analyzer.count_function_calls(symbol)
                    
                    all_usage[package_name].append(usage_node)
        
        return dict(all_usage)
    
    def get_usage_summary(self, package_name: str) -> dict[str, int]:
        """Get summary statistics for package usage.
        
        Args:
            package_name: Package to summarize
            
        Returns:
            Dictionary with usage statistics
        """
        usage_nodes = self.map_package_usage(package_name)
        
        # Count unique files and symbols
        files = {node.file_path for node in usage_nodes}
        symbols = {node.symbol_path for node in usage_nodes}
        total_calls = sum(node.call_count for node in usage_nodes)
        
        return {
            "total_files": len(files),
            "unique_symbols": len(symbols),
            "total_calls": total_calls,
            "import_statements": len(usage_nodes),
        }
