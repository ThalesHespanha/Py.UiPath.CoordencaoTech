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
    # Maps project_name -> version_spec for each project
    project_versions: Dict[str, str] = field(default_factory=dict)
    resolved_version: Optional[str] = None
    # All resolved versions needed (unique) across all projects
    all_resolved_versions: List[str] = field(default_factory=list)
    # Versions already installed in local NuGet cache
    installed_versions: List[str] = field(default_factory=list)
    available_versions: List[str] = field(default_factory=list)
    exists_in_orchestrator: Optional[bool] = None
    # True if ALL required versions are installed locally
    installed_locally: Optional[bool] = None
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
                            # Track which project uses which version
                            dependencies[pkg_id].project_versions[project_name] = str(version_spec)
                            
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


def resolve_all_versions_for_package(
    dep_info: DependencyInfo,
    available_versions: List[str]
) -> List[str]:
    """
    Resolve ALL unique versions required for a package across all projects.
    
    Args:
        dep_info: DependencyInfo with version_specs from multiple projects
        available_versions: List of versions available in Orchestrator (sorted desc)
        
    Returns:
        List of resolved versions (unique, sorted descending)
    """
    if not available_versions:
        return []
    
    resolved_set = set()
    
    for version_spec in dep_info.version_specs:
        resolved = resolve_best_version(available_versions, version_spec)
        if resolved:
            resolved_set.add(resolved)
    
    # Sort descending (newest first)
    return sorted(list(resolved_set), reverse=True, key=lambda v: [int(x) if x.isdigit() else 0 for x in v.split('.')])


def check_files_exist_in_directory(
    package_versions: List[tuple],
    target_dir: str
) -> Dict[tuple, bool]:
    """
    Check which (package_id, version) pairs already exist as .nupkg files in target directory.
    
    Args:
        package_versions: List of (package_id, version) tuples
        target_dir: Directory to check for existing files
        
    Returns:
        Dict mapping (package_id, version) -> exists (bool)
    """
    result = {}
    
    for pkg_id, version in package_versions:
        filename = f"{pkg_id}.{version}.nupkg"
        filepath = os.path.join(target_dir, filename)
        # File exists and is large enough to be a valid package
        exists = os.path.exists(filepath) and os.path.getsize(filepath) > 1000
        result[(pkg_id, version)] = exists
    
    return result


def get_download_list(
    custom_deps: Dict[str, DependencyInfo],
    target_dir: str
) -> tuple:
    """
    Build list of (package_id, version) pairs to download, excluding existing files.
    
    Args:
        custom_deps: Dict of DependencyInfo with all_resolved_versions populated
        target_dir: Directory to check for existing files
        
    Returns:
        Tuple of (to_download, already_exists) where each is a list of (pkg_id, version)
    """
    all_versions = []
    
    for pkg_id, dep_info in custom_deps.items():
        if dep_info.exists_in_orchestrator and dep_info.all_resolved_versions:
            for version in dep_info.all_resolved_versions:
                all_versions.append((pkg_id, version))
    
    # Check which already exist
    existence = check_files_exist_in_directory(all_versions, target_dir)
    
    to_download = [pv for pv in all_versions if not existence.get(pv, False)]
    already_exists = [pv for pv in all_versions if existence.get(pv, False)]
    
    return to_download, already_exists


def get_nuget_cache_path() -> str:
    """Get the local NuGet packages cache path."""
    return os.path.expanduser("~/.nuget/packages")


def check_local_nuget_cache(
    package_id: str,
    version_specs: Set[str]
) -> Tuple[List[str], bool]:
    """
    Check which versions of a package are installed in local NuGet cache.
    
    This is MUCH faster than querying Orchestrator API and can be used
    to skip unnecessary network calls.
    
    Args:
        package_id: Package ID to check (e.g., "Smarthis.Common.Activities")
        version_specs: Version specifications from projects
        
    Returns:
        Tuple of (list_of_installed_versions, all_specs_satisfied)
    """
    cache_path = get_nuget_cache_path()
    package_dir = os.path.join(cache_path, package_id.lower())
    
    installed_versions = []
    
    if os.path.exists(package_dir) and os.path.isdir(package_dir):
        # List all version folders
        try:
            for version_dir in os.listdir(package_dir):
                version_path = os.path.join(package_dir, version_dir)
                if os.path.isdir(version_path):
                    # Check for .nupkg or .nuspec to confirm it's a valid install
                    nupkg_file = os.path.join(version_path, f"{package_id.lower()}.{version_dir}.nupkg")
                    nuspec_files = [f for f in os.listdir(version_path) if f.endswith('.nuspec')]
                    
                    if os.path.exists(nupkg_file) or nuspec_files:
                        installed_versions.append(version_dir)
        except Exception as e:
            print(f"Warning: Error checking local cache for {package_id}: {e}")
    
    # Check if all required versions are installed
    all_satisfied = False
    if installed_versions and version_specs:
        # Parse each spec and check if any installed version satisfies it
        satisfied_specs = 0
        for spec in version_specs:
            spec_type, extracted = parse_version_spec(spec)
            if extracted:
                # Check if this version or compatible version is installed
                if extracted in installed_versions:
                    satisfied_specs += 1
                else:
                    # For minimum/range specs, check if any higher version is installed
                    for v in installed_versions:
                        if compare_versions(v, extracted) >= 0:
                            satisfied_specs += 1
                            break
        
        all_satisfied = satisfied_specs == len(version_specs)
    
    # Sort versions descending
    if installed_versions:
        installed_versions = sorted(
            installed_versions, 
            reverse=True, 
            key=lambda v: [int(x) if x.isdigit() else 0 for x in v.split('.')]
        )
    
    return installed_versions, all_satisfied


def check_all_local_cache(
    dependencies: Dict[str, DependencyInfo]
) -> int:
    """
    Check local NuGet cache for ALL dependencies and update their installed_versions.
    
    This is a fast local check that should be done BEFORE querying Orchestrator.
    
    Args:
        dependencies: Dict of DependencyInfo to check
        
    Returns:
        Number of packages that are fully satisfied from local cache
    """
    fully_installed = 0
    
    for pkg_id, dep_info in dependencies.items():
        installed, all_satisfied = check_local_nuget_cache(pkg_id, dep_info.version_specs)
        
        dep_info.installed_versions = installed
        dep_info.installed_locally = all_satisfied
        
        if all_satisfied:
            fully_installed += 1
    
    return fully_installed
