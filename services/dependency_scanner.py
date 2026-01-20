"""
Dependency Scanner Service
==========================
Scans UiPath projects to extract and consolidate package dependencies from project.json files.

This service enables batch detection of custom libraries used across multiple projects,
allowing for synchronized download and installation.
"""

import os
import re
import json
from typing import Dict, List, Tuple, Set, Optional
from dataclasses import dataclass, field


@dataclass
class DependencyInfo:
    """Information about a consolidated dependency across projects."""
    package_id: str
    version_specs: Set[str] = field(default_factory=set)
    projects: Set[str] = field(default_factory=set)
    resolved_version: Optional[str] = None
    available_versions: List[str] = field(default_factory=list)
    exists_in_orchestrator: Optional[bool] = None
    error_message: Optional[str] = None


# Default prefixes for official UiPath packages (to be excluded from custom libs)
OFFICIAL_PREFIXES = [
    "UiPath.",
    "System.",
    "Microsoft.",
    "Newtonsoft.",
    "NuGet.",
]


def scan_project_dependencies(base_dir: str) -> Dict[str, DependencyInfo]:
    """
    Scan all UiPath projects in a directory and consolidate their dependencies.
    
    Args:
        base_dir: Root directory containing UiPath project folders
        
    Returns:
        Dict mapping package_id to DependencyInfo with consolidated data
    """
    dependencies: Dict[str, DependencyInfo] = {}
    
    if not os.path.exists(base_dir):
        return dependencies
    
    try:
        # Iterate over immediate subdirectories
        for item in os.listdir(base_dir):
            item_path = os.path.join(base_dir, item)
            
            if os.path.isdir(item_path):
                project_json_path = os.path.join(item_path, "project.json")
                
                if os.path.exists(project_json_path):
                    try:
                        with open(project_json_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        
                        project_name = data.get("name", item)
                        deps = data.get("dependencies", {})
                        
                        # Process each dependency
                        for pkg_id, version_spec in deps.items():
                            if pkg_id not in dependencies:
                                dependencies[pkg_id] = DependencyInfo(package_id=pkg_id)
                            
                            dependencies[pkg_id].version_specs.add(str(version_spec))
                            dependencies[pkg_id].projects.add(project_name)
                            
                    except (json.JSONDecodeError, IOError) as e:
                        # Skip invalid project.json files
                        print(f"Warning: Could not parse {project_json_path}: {e}")
                        continue
                        
    except Exception as e:
        print(f"Error scanning dependencies: {e}")
    
    return dependencies


def parse_version_spec(version_spec: str) -> Tuple[str, Optional[str]]:
    """
    Parse UiPath/NuGet version specification string.
    
    UiPath uses NuGet-style version ranges:
    - "[1.2.3]" = exact version 1.2.3
    - "[1.0,2.0)" = range: >= 1.0 and < 2.0
    - "(,1.0]" = range: <= 1.0
    - "[1.0,)" = range: >= 1.0
    - "1.2.3" = minimum version (often treated as exact in UiPath)
    
    Args:
        version_spec: Version specification string
        
    Returns:
        Tuple of (spec_type, extracted_version)
        spec_type: 'exact', 'minimum', 'range', or 'unknown'
        extracted_version: The version number if exact/minimum, None for ranges
    """
    spec = str(version_spec).strip()
    
    # Exact version: [X.Y.Z]
    exact_match = re.match(r'^\[(\d+\.\d+\.\d+(?:\.\d+)?(?:-[\w\.]+)?)\]$', spec)
    if exact_match:
        return ('exact', exact_match.group(1))
    
    # Simple version (no brackets) - treat as minimum/exact
    simple_match = re.match(r'^(\d+\.\d+\.\d+(?:\.\d+)?(?:-[\w\.]+)?)$', spec)
    if simple_match:
        return ('minimum', simple_match.group(1))
    
    # Range with lower bound: [X.Y.Z, ...
    lower_bound_match = re.match(r'^\[(\d+\.\d+\.\d+(?:\.\d+)?)', spec)
    if lower_bound_match:
        return ('range', lower_bound_match.group(1))
    
    # Range with upper bound only: (,X.Y.Z] or (,X.Y.Z)
    upper_bound_match = re.match(r'^\(,\s*(\d+\.\d+\.\d+(?:\.\d+)?)', spec)
    if upper_bound_match:
        return ('range', None)
    
    return ('unknown', None)


def is_custom_library(
    package_id: str, 
    custom_prefixes: Optional[List[str]] = None,
    official_prefixes: Optional[List[str]] = None
) -> bool:
    """
    Determine if a package is a custom library (not official UiPath/System package).
    
    Args:
        package_id: The package identifier
        custom_prefixes: If provided, package must start with one of these to be custom
        official_prefixes: Prefixes for official packages to exclude
        
    Returns:
        True if package is considered a custom library
    """
    if official_prefixes is None:
        official_prefixes = OFFICIAL_PREFIXES
    
    # If custom prefixes are provided, use whitelist approach
    if custom_prefixes:
        return any(package_id.startswith(prefix) for prefix in custom_prefixes)
    
    # Otherwise, use blacklist approach (exclude official packages)
    return not any(package_id.startswith(prefix) for prefix in official_prefixes)


def filter_custom_dependencies(
    dependencies: Dict[str, DependencyInfo],
    custom_prefixes: Optional[List[str]] = None,
    use_prefix_filter: bool = True
) -> Dict[str, DependencyInfo]:
    """
    Filter dependencies to only include custom libraries.
    
    Args:
        dependencies: Full dependency dict from scan_project_dependencies
        custom_prefixes: List of prefixes for custom packages (e.g., ["Smarthis.", "FS."])
        use_prefix_filter: If True and custom_prefixes provided, use whitelist; otherwise blacklist
        
    Returns:
        Filtered dict with only custom dependencies
    """
    if not use_prefix_filter:
        # No filtering - return all
        return dependencies
    
    return {
        pkg_id: info 
        for pkg_id, info in dependencies.items() 
        if is_custom_library(pkg_id, custom_prefixes if use_prefix_filter else None)
    }


def resolve_best_version(
    available_versions: List[str], 
    version_spec: str
) -> Optional[str]:
    """
    Given available versions and a version spec, find the best matching version.
    
    Strategy:
    1. If exact version specified and available, use it
    2. If minimum version specified, find highest version >= minimum
    3. For ranges, try to satisfy bounds
    4. Fallback: return latest (first in sorted desc list)
    
    Args:
        available_versions: List of available versions (should be sorted descending)
        version_spec: The version specification from project.json
        
    Returns:
        Best matching version or None if no versions available
    """
    if not available_versions:
        return None
    
    spec_type, extracted = parse_version_spec(version_spec)
    
    if spec_type == 'exact' and extracted:
        # Exact match required
        if extracted in available_versions:
            return extracted
        # Try to find close match (ignore build metadata differences)
        base_version = extracted.split('-')[0]
        for v in available_versions:
            if v == extracted or v.startswith(base_version):
                return v
    
    if spec_type == 'minimum' and extracted:
        # Find highest version >= minimum
        try:
            for v in available_versions:  # Already sorted desc
                if compare_versions(v, extracted) >= 0:
                    return v
        except Exception:
            pass
    
    # Fallback: return latest version
    return available_versions[0] if available_versions else None


def compare_versions(v1: str, v2: str) -> int:
    """
    Compare two version strings.
    
    Returns:
        -1 if v1 < v2
         0 if v1 == v2
         1 if v1 > v2
    """
    def normalize(v):
        # Remove pre-release suffix for comparison
        base = v.split('-')[0]
        parts = base.split('.')
        return [int(p) if p.isdigit() else 0 for p in parts]
    
    n1 = normalize(v1)
    n2 = normalize(v2)
    
    # Pad to same length
    max_len = max(len(n1), len(n2))
    n1.extend([0] * (max_len - len(n1)))
    n2.extend([0] * (max_len - len(n2)))
    
    for a, b in zip(n1, n2):
        if a < b:
            return -1
        if a > b:
            return 1
    return 0


def get_display_version(dep_info: DependencyInfo) -> str:
    """
    Get a display-friendly version string for a dependency.
    
    Returns resolved version if available, otherwise first version spec.
    """
    if dep_info.resolved_version:
        return dep_info.resolved_version
    
    if dep_info.version_specs:
        # Get the first version spec and try to extract version
        first_spec = next(iter(dep_info.version_specs))
        spec_type, extracted = parse_version_spec(first_spec)
        if extracted:
            return extracted
        return first_spec
    
    return "Unknown"


def format_projects_list(projects: Set[str], max_display: int = 3) -> str:
    """
    Format project list for display, truncating if too many.
    """
    proj_list = sorted(projects)
    if len(proj_list) <= max_display:
        return ", ".join(proj_list)
    return f"{', '.join(proj_list[:max_display])} (+{len(proj_list) - max_display} more)"
