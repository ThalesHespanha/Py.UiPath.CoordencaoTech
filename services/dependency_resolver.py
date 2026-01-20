"""
Dependency Resolver Service
===========================
Handles recursive dependency resolution for UiPath custom libraries.
Parses .nuspec files to discover transitive dependencies including .Runtime packages.

This ensures that when a custom library declares dependencies (e.g., .Runtime packages),
those dependencies are also downloaded and installed to the local NuGet cache.
"""

import os
import re
import zipfile
from typing import List, Dict, Set, Tuple, Optional, TYPE_CHECKING
from dataclasses import dataclass, field

if TYPE_CHECKING:
    from services.orchestrator import OrchestratorService


# Official package prefixes to skip during transitive resolution
OFFICIAL_PREFIXES = [
    "UiPath.",
    "System.",
    "Microsoft.",
    "Newtonsoft.",
    "NuGet.",
]


@dataclass
class ResolvedPackage:
    """A resolved package with its transitive dependencies."""
    package_id: str
    version: str
    nupkg_path: Optional[str] = None
    dependencies: List['ResolvedPackage'] = field(default_factory=list)
    is_downloaded: bool = False
    is_installed: bool = False
    was_skipped: bool = False  # True if file already existed
    error: Optional[str] = None


class DependencyResolver:
    """
    Resolves transitive dependencies for UiPath custom libraries.
    
    Key features:
    - Parses .nuspec files to discover dependencies
    - Recursively downloads all transitive dependencies
    - Tracks visited packages to avoid duplicate downloads
    - Handles .Runtime companion packages automatically
    """
    
    def __init__(self, orchestrator_service: 'OrchestratorService'):
        """
        Initialize the resolver with an OrchestratorService instance.
        
        Args:
            orchestrator_service: Service for downloading packages from Orchestrator
        """
        self.orch = orchestrator_service
        self._visited: Set[Tuple[str, str]] = set()
        self._download_stats = {
            "downloaded": 0,
            "installed": 0,
            "skipped": 0,
            "failed": 0
        }
    
    def reset_stats(self):
        """Reset download statistics."""
        self._visited.clear()
        self._download_stats = {
            "downloaded": 0,
            "installed": 0,
            "skipped": 0,
            "failed": 0
        }
    
    def get_stats(self) -> Dict[str, int]:
        """Get current download statistics."""
        return self._download_stats.copy()
    
    def parse_nuspec_dependencies(self, nupkg_path: str) -> List[Dict[str, str]]:
        """
        Parse .nuspec file inside a .nupkg to extract dependencies.
        
        Args:
            nupkg_path: Path to the .nupkg file
            
        Returns:
            List of dicts with 'id' and 'version' keys for each dependency
        """
        dependencies = []
        
        try:
            with zipfile.ZipFile(nupkg_path, 'r') as zf:
                # Find .nuspec file
                nuspec_files = [f for f in zf.namelist() if f.endswith('.nuspec')]
                if not nuspec_files:
                    print(f"Warning: No .nuspec found in {nupkg_path}")
                    return []
                
                content = zf.read(nuspec_files[0]).decode('utf-8')
                
                # Parse dependency elements
                # Pattern matches: <dependency id="..." version="..." />
                # Also handles: <dependency id="..." version="..." ... />
                pattern = r'<dependency\s+id=["\']([^"\']+)["\']\s+version=["\']([^"\']+)["\']'
                matches = re.findall(pattern, content, re.IGNORECASE)
                
                for pkg_id, version_spec in matches:
                    resolved_version = self._resolve_version_spec(version_spec)
                    dependencies.append({
                        'id': pkg_id,
                        'version': resolved_version,
                        'version_spec': version_spec  # Keep original for reference
                    })
                    
                if dependencies:
                    print(f"  Found {len(dependencies)} dependencies in {os.path.basename(nupkg_path)}")
                    
        except zipfile.BadZipFile:
            print(f"Error: {nupkg_path} is not a valid zip/nupkg file")
        except Exception as e:
            print(f"Error parsing nuspec from {nupkg_path}: {e}")
        
        return dependencies

    def resolve_all(
        self, 
        token: str,
        root_packages: List[Tuple[str, str]],
        target_dir: str,
        install_to_cache: bool = True,
        version_cache: Optional[Dict] = None
    ) -> Tuple[List[ResolvedPackage], List[str]]:
        """
        Resolve and download all packages including transitive dependencies.
        
        This is the main entry point for resolving dependencies. It will:
        1. Download each root package
        2. Parse its .nuspec to find dependencies
        3. Recursively download all transitive dependencies
        4. Track visited packages to avoid duplicates
        
        Args:
            token: Orchestrator auth token
            root_packages: List of (package_id, version) tuples to resolve
            target_dir: Directory to save .nupkg files
            install_to_cache: Also install to NuGet cache
            version_cache: Optional dict for caching version lookups
            
        Returns:
            Tuple of (list_of_resolved_packages, list_of_errors)
        """
        self.reset_stats()
        os.makedirs(target_dir, exist_ok=True)
        
        resolved = []
        errors = []
        
        print(f"\n{'='*60}")
        print(f"Resolving {len(root_packages)} root packages with transitive dependencies")
        print(f"Target directory: {target_dir}")
        print(f"{'='*60}\n")
        
        for pkg_id, version in root_packages:
            print(f"\n📦 Processing: {pkg_id}@{version}")
            result, errs = self._resolve_recursive(
                token, pkg_id, version, target_dir, install_to_cache, version_cache
            )
            resolved.append(result)
            errors.extend(errs)
        
        print(f"\n{'='*60}")
        print(f"Resolution complete!")
        print(f"  Downloaded: {self._download_stats['downloaded']}")
        print(f"  Installed:  {self._download_stats['installed']}")
        print(f"  Skipped:    {self._download_stats['skipped']}")
        print(f"  Failed:     {self._download_stats['failed']}")
        print(f"{'='*60}\n")
        
        return resolved, errors

    def _resolve_recursive(
        self,
        token: str,
        package_id: str,
        version: str,
        target_dir: str,
        install_to_cache: bool,
        version_cache: Optional[Dict] = None
    ) -> Tuple[ResolvedPackage, List[str]]:
        """
        Recursively resolve a package and its dependencies.
        
        Args:
            token: Auth token
            package_id: Package to resolve
            version: Version to download
            target_dir: Where to save files
            install_to_cache: Also install to NuGet cache
            version_cache: Optional version cache for lookups
            
        Returns:
            Tuple of (ResolvedPackage, list_of_errors)
        """
        errors = []
        pkg = ResolvedPackage(package_id=package_id, version=version)
        
        # Check if already visited (avoid loops and duplicates)
        key = (package_id.lower(), version)
        if key in self._visited:
            print(f"  ⏭️  Already processed: {package_id}@{version}")
            pkg.is_downloaded = True
            pkg.was_skipped = True
            return pkg, errors
        
        self._visited.add(key)
        
        # Check if package is available (if we have version cache)
        if version_cache is not None:
            if package_id not in version_cache:
                exists, available = self.orch.check_library_exists(token, package_id, version_cache)
                if not exists:
                    pkg.error = f"Package not found in Orchestrator"
                    errors.append(f"{package_id}@{version}: Not found in Orchestrator")
                    self._download_stats['failed'] += 1
                    return pkg, errors
        
        # Download the package
        success, result = self.orch.download_library_persistent(
            token, package_id, version, target_dir, skip_existing=True
        )
        
        if not success:
            pkg.error = result
            errors.append(f"{package_id}@{version}: {result}")
            self._download_stats['failed'] += 1
            return pkg, errors
        
        pkg.nupkg_path = result
        pkg.is_downloaded = True
        
        # Check if file was already there or newly downloaded
        # We can detect this by checking if download was very fast (file existed)
        expected_path = os.path.join(target_dir, f"{package_id}.{version}.nupkg")
        if result == expected_path:
            print(f"  ✅ Downloaded: {package_id}@{version}")
            self._download_stats['downloaded'] += 1
        else:
            self._download_stats['downloaded'] += 1
        
        # Install to cache if requested
        if install_to_cache:
            inst_ok, inst_msg = self.orch.install_nupkg_to_cache(result)
            pkg.is_installed = inst_ok
            if inst_ok:
                print(f"  📥 Installed to cache: {package_id}@{version}")
                self._download_stats['installed'] += 1
            else:
                print(f"  ⚠️  Install failed: {inst_msg}")
                errors.append(f"Install failed {package_id}: {inst_msg}")
        
        # Parse dependencies from .nuspec
        dependencies = self.parse_nuspec_dependencies(result)
        
        for dep in dependencies:
            dep_id = dep['id']
            dep_version = dep['version']
            
            # Skip official UiPath/System packages
            if self._is_official_package(dep_id):
                print(f"  ⏭️  Skipping official package: {dep_id}")
                continue
            
            print(f"  🔗 Resolving dependency: {dep_id}@{dep_version}")
            
            # Resolve dependency recursively
            dep_pkg, dep_errs = self._resolve_recursive(
                token, dep_id, dep_version, target_dir, install_to_cache, version_cache
            )
            pkg.dependencies.append(dep_pkg)
            errors.extend(dep_errs)
        
        return pkg, errors

    def _is_official_package(self, package_id: str) -> bool:
        """
        Check if package is an official UiPath/System package.
        
        Official packages are available on public feeds and don't need
        to be downloaded from Orchestrator.
        """
        return any(package_id.startswith(p) for p in OFFICIAL_PREFIXES)
    
    def _resolve_version_spec(self, spec: str) -> str:
        """
        Extract concrete version from NuGet version specification.
        
        Examples:
        - "[1.0.0]" -> "1.0.0" (exact)
        - "[1.0.0, 2.0.0)" -> "1.0.0" (range: take lower bound)
        - "1.0.0" -> "1.0.0" (minimum)
        - "[1.0.0,)" -> "1.0.0" (minimum inclusive)
        """
        spec = spec.strip()
        
        # Exact version: [X.Y.Z]
        exact_match = re.match(r'^\[(\d+\.\d+\.\d+(?:\.\d+)?(?:-[\w\.]+)?)\]$', spec)
        if exact_match:
            return exact_match.group(1)
        
        # Range with lower bound: [X.Y.Z, ...
        lower_bound_match = re.match(r'^\[(\d+\.\d+\.\d+(?:\.\d+)?)', spec)
        if lower_bound_match:
            return lower_bound_match.group(1)
        
        # Simple version (no brackets)
        simple_match = re.match(r'^(\d+\.\d+\.\d+(?:\.\d+)?(?:-[\w\.]+)?)$', spec)
        if simple_match:
            return simple_match.group(1)
        
        # Fallback: return as-is
        return spec


def count_total_packages(resolved_list: List[ResolvedPackage]) -> Tuple[int, int]:
    """
    Count total packages in a resolution result (main + transitive).
    
    Args:
        resolved_list: List of ResolvedPackage from resolve_all
        
    Returns:
        Tuple of (main_count, transitive_count)
    """
    main_count = len(resolved_list)
    
    def count_deps(pkg: ResolvedPackage) -> int:
        count = len(pkg.dependencies)
        for dep in pkg.dependencies:
            count += count_deps(dep)
        return count
    
    transitive_count = sum(count_deps(pkg) for pkg in resolved_list)
    
    return main_count, transitive_count
