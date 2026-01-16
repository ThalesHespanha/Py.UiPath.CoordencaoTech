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
        self.scope = config.get("orch_scope", "OR.Folders OR.Assets OR.Jobs OR.Execution")

    def get_token(self) -> Optional[str]:
        """Authenticate with Orchestrator and get access token."""
        token_url = f"{self.base_url}/identity/connect/token"
        
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
        except requests.RequestException as e:
            st.error(f"❌ Erro ao autenticar no Orchestrator: {e}")
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
