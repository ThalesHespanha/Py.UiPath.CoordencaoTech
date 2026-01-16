import os
import requests
import streamlit as st
from typing import Optional, Tuple, List

class OrchestratorService:
    def __init__(self, config: dict):
        self.config = config
        self.base_url = config.get("orch_url", "https://cloud.uipath.com")
        self.org = config.get("orch_org", "")
        self.tenant = config.get("orch_tenant", "")
        self.client_id = config.get("orch_client_id", "")
        self.client_secret = config.get("orch_client_secret", "")
        self.scope = config.get("orch_scope", "OR.Default")

    def get_token(self) -> Optional[str]:
        """Authenticate with Orchestrator and get access token."""
        # Determine Identity URL (Cloud uses 'identity_', On-Prem uses 'identity')
        identity_path = "identity_" if "cloud.uipath.com" in self.base_url else "identity"
        token_url = f"{self.base_url.rstrip('/')}/{identity_path}/connect/token"
        
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": self.scope,
        }
        
        try:
            response = requests.post(token_url, data=payload, timeout=30)
            response.raise_for_status()
            return response.json().get("access_token")
        except requests.exceptions.JSONDecodeError:
            st.error(f"❌ Erro de Resposta Inválida (Não é JSON).")
            st.error(f"URL Tentada: {token_url}")
            st.code(response.text[:1000]) # Show first 1000 chars of response
            return None
        except requests.RequestException as e:
            st.error(f"❌ Erro ao autenticar no Orchestrator: {e}")
            if hasattr(e, 'response') and e.response is not None:
                 st.error(f"Status: {e.response.status_code}")
                 st.code(e.response.text[:1000])
            return None

    def upload_package(self, token: str, nupkg_path: str, folder_id: Optional[int] = None) -> Tuple[bool, str]:
        """
        Upload a .nupkg package to Orchestrator.
        If folder_id is None, uploads to Tenant level (modern approach).
        """
        upload_url = f"{self.base_url}/{self.org}/{self.tenant}/orchestrator_/odata/Processes/UiPath.Server.Configuration.OData.UploadPackage"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "X-UIPATH-TenantName": self.tenant,
        }
        
        if folder_id:
            headers["X-UIPATH-OrganizationUnitId"] = str(folder_id)
        
        try:
            with open(nupkg_path, "rb") as f:
                files = {"file": (os.path.basename(nupkg_path), f, "application/octet-stream")}
                response = requests.post(upload_url, headers=headers, files=files, timeout=120)
                
            if response.status_code in [200, 201]:
                return True, "✅ Pacote enviado com sucesso!"
            else:
                return False, f"❌ Erro ({response.status_code}): {response.text}"
        except requests.RequestException as e:
            return False, f"❌ Erro de conexão: {e}"

    def download_package(self, token: str, package_id: str, version: str, output_dir: str) -> Tuple[bool, str]:
        """Download a package from Orchestrator."""
        download_url = f"{self.base_url}/{self.org}/{self.tenant}/orchestrator_/odata/Processes/UiPath.Server.Configuration.OData.DownloadPackage(key='{package_id}',version='{version}')"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "X-UIPATH-TenantName": self.tenant,
        }
        
        try:
            response = requests.get(download_url, headers=headers, timeout=120, stream=True)
            response.raise_for_status()
            
            filename = f"{package_id}.{version}.nupkg"
            output_path = os.path.join(output_dir, filename)
            
            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            return True, output_path
        except requests.RequestException as e:
            return False, f"❌ Erro ao baixar pacote: {e}"

    def list_packages(self, token: str) -> List[dict]:
        """List packages from Orchestrator."""
        url = f"{self.base_url}/{self.org}/{self.tenant}/orchestrator_/odata/Processes"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "X-UIPATH-TenantName": self.tenant,
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json().get("value", [])
        except requests.RequestException as e:
            st.error(f"❌ Erro ao listar pacotes: {e}")
            return []

    def list_libraries(self, token: str, search_term: str = None) -> List[dict]:
        """List libraries from Orchestrator (Tenant level) - returns only latest version of each."""
        url = f"{self.base_url}/{self.org}/{self.tenant}/orchestrator_/odata/Libraries"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "X-UIPATH-TenantName": self.tenant,
        }
        
        # Query to get libraries - this returns only latest versions by default
        params = {
            "$orderby": "Id asc",
            "$top": "100",
            "$select": "Id,Version,Title,Authors,Published,IsLatestVersion"
        }
        if search_term:
            params["$filter"] = f"contains(tolower(Id), tolower('{search_term}'))"
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=60)
            response.raise_for_status()
            return response.json().get("value", [])
        except requests.RequestException as e:
            print(f"❌ Erro ao listar libraries: {e}")
            return []

    def get_library_versions(self, token: str, package_id: str) -> List[str]:
        """Get ALL versions of a specific library using GetVersions endpoint."""
        url = f"{self.base_url}/{self.org}/{self.tenant}/orchestrator_/odata/Libraries/UiPath.Server.Configuration.OData.GetVersions(packageId='{package_id}')"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "X-UIPATH-TenantName": self.tenant,
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            # The response may contain strings or objects with Version field
            raw_versions = data.get("value", [])
            
            # Extract version strings - handle both cases
            versions = []
            for v in raw_versions:
                if isinstance(v, str):
                    versions.append(v)
                elif isinstance(v, dict):
                    # May have "Version" or "version" key
                    ver = v.get("Version") or v.get("version") or str(v)
                    versions.append(ver)
                else:
                    versions.append(str(v))
            
            # Sort versions descending
            def version_key(v):
                try:
                    return [int(x) if x.isdigit() else x for x in str(v).replace('-', '.').split('.')]
                except:
                    return [str(v)]
            
            sorted_versions = sorted(versions, reverse=True, key=version_key)
            
            return sorted_versions
        except requests.RequestException as e:
            print(f"⚠️ Erro ao obter versões de {package_id}: {e}")
            # Fallback: return empty list
            return []

    def list_libraries_with_all_versions(self, token: str, search_term: str = None) -> dict:
        """List libraries and fetch ALL versions for each one."""
        # First, get the list of unique library IDs
        libraries = self.list_libraries(token, search_term)
        
        if not libraries:
            return {}
        
        # Get unique package IDs
        unique_ids = list(set(lib.get("Id") for lib in libraries if lib.get("Id")))
        
        # For each package, get all versions
        grouped = {}
        for lib in libraries:
            lib_id = lib.get("Id", "Unknown")
            if lib_id not in grouped:
                # Get all versions for this package
                all_versions = self.get_library_versions(token, lib_id)
                
                # If GetVersions failed, use at least the version we have
                if not all_versions:
                    all_versions = [lib.get("Version", "Unknown")]
                
                grouped[lib_id] = {
                    "id": lib_id,
                    "title": lib.get("Title", lib_id),
                    "authors": lib.get("Authors", ""),
                    "versions": all_versions
                }
        
        return grouped

    def group_libraries_by_id(self, libraries: List[dict]) -> dict:
        """Group libraries by package ID, collecting all versions for each."""
        grouped = {}
        for lib in libraries:
            lib_id = lib.get("Id", "Unknown")
            if lib_id not in grouped:
                grouped[lib_id] = {
                    "id": lib_id,
                    "title": lib.get("Title", lib_id),
                    "authors": lib.get("Authors", ""),
                    "versions": []
                }
            grouped[lib_id]["versions"].append(lib.get("Version", "Unknown"))
        
        # Sort versions descending for each package
        for pkg in grouped.values():
            pkg["versions"] = sorted(pkg["versions"], reverse=True, key=lambda v: [int(x) if x.isdigit() else x for x in v.replace('-', '.').split('.')])
        
        return grouped

    def download_library(self, token: str, package_id: str, version: str, output_dir: str) -> Tuple[bool, str]:
        """Download a library package from Orchestrator - tries multiple endpoints."""
        
        headers = {
            "Authorization": f"Bearer {token}",
            "X-UIPATH-TenantName": self.tenant,
        }
        
        # List of endpoints to try (Libraries have different endpoints than Processes)
        endpoints = [
            # 1. OData Libraries endpoint with key:version format
            f"{self.base_url}/{self.org}/{self.tenant}/orchestrator_/odata/Libraries/UiPath.Server.Configuration.OData.DownloadPackage(key='{package_id}:{version}')",
            # 2. NuGet V2 feed format for Libraries
            f"{self.base_url}/{self.org}/{self.tenant}/orchestrator_/nuget/Libraries/v2/package/{package_id}/{version}",
            # 3. NuGet V3 flat container format
            f"{self.base_url}/{self.org}/{self.tenant}/orchestrator_/nuget/Libraries/v3/flatcontainer/{package_id.lower()}/{version}/{package_id.lower()}.{version}.nupkg",
            # 4. Tenant-level library feed
            f"{self.base_url}/{self.org}/{self.tenant}/orchestrator_/nuget/v3/flatcontainer/{package_id.lower()}/{version}/{package_id.lower()}.{version}.nupkg",
        ]
        
        last_error = None
        for endpoint in endpoints:
            try:
                print(f"Tentando: {endpoint}")
                response = requests.get(endpoint, headers=headers, timeout=120, stream=True, allow_redirects=True)
                
                if response.status_code == 200:
                    filename = f"{package_id}.{version}.nupkg"
                    output_path = os.path.join(output_dir, filename)
                    
                    with open(output_path, "wb") as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    # Verify it's a valid file (not HTML error page)
                    if os.path.getsize(output_path) > 1000:  # NuGet packages are at least a few KB
                        return True, output_path
                    else:
                        os.remove(output_path)
                        last_error = "Downloaded file too small, likely not a valid package"
                else:
                    last_error = f"HTTP {response.status_code}"
                    
            except requests.RequestException as e:
                last_error = str(e)
                continue
        
        return False, f"❌ Erro ao baixar library (todos endpoints falharam): {last_error}"

    def install_nupkg_to_cache(self, nupkg_path: str) -> Tuple[bool, str]:
        """Install a .nupkg file to the local NuGet cache with proper metadata files."""
        import subprocess
        import zipfile
        import json
        import hashlib
        import base64
        
        try:
            # Read package info from nuspec inside nupkg
            with zipfile.ZipFile(nupkg_path, 'r') as zf:
                # Find .nuspec file
                nuspec_files = [f for f in zf.namelist() if f.endswith('.nuspec')]
                if not nuspec_files:
                    return False, "No .nuspec found in package"
                
                # Parse nuspec to get package id and version
                nuspec_content = zf.read(nuspec_files[0]).decode('utf-8')
                
                # Simple XML parsing for id and version
                import re
                id_match = re.search(r'<id>([^<]+)</id>', nuspec_content, re.IGNORECASE)
                version_match = re.search(r'<version>([^<]+)</version>', nuspec_content, re.IGNORECASE)
                
                if not id_match or not version_match:
                    return False, "Could not parse package id/version from nuspec"
                
                package_id = id_match.group(1)
                package_version = version_match.group(1)
            
            # Determine NuGet cache path
            nuget_cache = os.path.expanduser("~/.nuget/packages")
            package_dir = os.path.join(nuget_cache, package_id.lower(), package_version)
            
            # Create directory and extract
            os.makedirs(package_dir, exist_ok=True)
            
            with zipfile.ZipFile(nupkg_path, 'r') as zf:
                zf.extractall(package_dir)
            
            # Copy the nupkg itself
            import shutil
            nupkg_dest = os.path.join(package_dir, f"{package_id.lower()}.{package_version}.nupkg")
            shutil.copy2(nupkg_path, nupkg_dest)
            
            # Calculate SHA512 hash of the nupkg file
            with open(nupkg_path, 'rb') as f:
                sha512_hash = hashlib.sha512(f.read()).digest()
                sha512_base64 = base64.b64encode(sha512_hash).decode('utf-8')
            
            # Create .nupkg.sha512 file (base64 encoded SHA512 hash)
            sha512_file = os.path.join(package_dir, f"{package_id.lower()}.{package_version}.nupkg.sha512")
            with open(sha512_file, 'w') as f:
                f.write(sha512_base64)
            
            # Create .nupkg.metadata file (JSON format required by NuGet)
            metadata_file = os.path.join(package_dir, ".nupkg.metadata")
            metadata_content = {
                "version": 2,
                "contentHash": sha512_base64,
                "source": None  # null indicates local/offline source
            }
            with open(metadata_file, 'w') as f:
                json.dump(metadata_content, f, indent=2)
            
            return True, f"✅ Instalado: {package_id} v{package_version}"
            
        except Exception as e:
            return False, f"❌ Erro ao instalar no cache: {e}"
