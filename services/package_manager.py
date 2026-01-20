import os
import shutil
import re
import subprocess
import tempfile
from typing import Tuple, List, Optional
from pathlib import Path

class PackageManager:
    @staticmethod
    def run_pack(
        project_path: str,
        output_dir: str,
        version: str,
        use_local_cache: bool = True,
        custom_feed_url: Optional[str] = None,
        auth_config: Optional[dict] = None,
        use_orchestrator_feeds: bool = False  # New flag to optionally try Orch feeds
    ) -> Tuple[bool, str, str]:
        """Run UiPath CLI pack command.
        
        Uses only public NuGet feeds + local cache by default.
        Orchestrator packages should be pre-downloaded via the Libraries tab.
        """
        
        os.makedirs(output_dir, exist_ok=True)
        
        cmd_parts = [
            "uipcli",
            "package", "pack",
            f'"{project_path}"',
            "--output",
            f'"{output_dir}"',
            "--version",
            version,
        ]
        
        temp_config_path = None
        
        try:
            # Get local NuGet cache path
            local_cache_path = os.path.expanduser("~/.nuget/packages")
            
            # Create a nuget.config with:
            # 1. Local cache (for pre-downloaded custom packages)
            # 2. Public Official UiPath Feeds
            # 3. NuGet.org
            # 
            # This ensures uipcli pack can find custom packages that were
            # pre-downloaded via the Libraries tab.
            
            nuget_config_content = f"""<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <packageSources>
    <clear />
    <!-- Local NuGet cache (pre-downloaded custom packages) -->
    <add key="LocalCache" value="{local_cache_path}" />
    <!-- Public Official UiPath Feeds -->
    <add key="UiPathOfficial" value="https://pkgs.dev.azure.com/uipath/Public.Feeds/_packaging/UiPath-Official/nuget/v3/index.json" />
    <add key="UiPathGallery" value="https://gallery.uipath.com/api/v3/index.json" />
    <!-- Public NuGet.org -->
    <add key="NuGetOrg" value="https://api.nuget.org/v3/index.json" />
  </packageSources>
  <config>
    <!-- Use local cache as global packages folder -->
    <add key="globalPackagesFolder" value="{local_cache_path}" />
  </config>
</configuration>"""

            # Optionally add Orchestrator feeds if user wants to try them
            if use_orchestrator_feeds and auth_config:
                org = auth_config.get("orch_org", "")
                tenant = auth_config.get("orch_tenant", "")
                base_url = auth_config.get("orch_url", "https://cloud.uipath.com").rstrip("/")
                
                if org and tenant:
                    # Add library authentication params (may or may not work)
                    cmd_parts.extend([
                        "--libraryOrchestratorAccountForApp", f'"{org}"',
                        "--libraryOrchestratorApplicationId", f'"{auth_config.get("orch_client_id", "")}"',
                        "--libraryOrchestratorApplicationSecret", f'"{auth_config.get("orch_client_secret", "")}"',
                        "--libraryOrchestratorApplicationScope", f'"{auth_config.get("orch_scope", "OR.Default")}"',
                        "--libraryOrchestratorUrl", f'"{base_url}"',
                        "--libraryOrchestratorTenant", f'"{tenant}"',
                    ])
                    
                    # Add Orchestrator feeds to config
                    orch_feed = f"{base_url}/{org}/{tenant}/orchestrator_/nuget/v3/index.json"
                    lib_feed = f"{base_url}/{org}/{tenant}/orchestrator_/nuget/Libraries/v3/index.json"
                    
                    nuget_config_content = f"""<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <packageSources>
    <clear />
    <add key="OrchestratorLibraries" value="{lib_feed}" />
    <add key="OrchestratorProcesses" value="{orch_feed}" />
    <add key="UiPathOfficial" value="https://pkgs.dev.azure.com/uipath/Public.Feeds/_packaging/UiPath-Official/nuget/v3/index.json" />
    <add key="UiPathGallery" value="https://gallery.uipath.com/api/v3/index.json" />
    <add key="NuGetOrg" value="https://api.nuget.org/v3/index.json" />
  </packageSources>
</configuration>"""

            # Write the nuget config
            fd, temp_config_path = tempfile.mkstemp(suffix=".config", prefix="nuget_")
            os.close(fd)
            with open(temp_config_path, "w") as f:
                f.write(nuget_config_content)
            cmd_parts.extend(["--nugetConfigFilePath", f'"{temp_config_path}"'])
            
            cmd = " ".join(cmd_parts)
            
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            output = result.stdout + result.stderr
            success = result.returncode == 0
            
            return success, cmd, output
            
        except subprocess.TimeoutExpired:
            return False, cmd, "❌ Timeout: O comando excedeu o limite de 5 minutos"
        except Exception as e:
            return False, cmd, f"❌ Erro: {e}"
        finally:
            # Cleanup temp file
            if temp_config_path and os.path.exists(temp_config_path):
                try:
                    os.remove(temp_config_path)
                except:
                    pass

    @staticmethod
    def find_nupkg_files(directory: str) -> List[str]:
        """Find all .nupkg files in a directory."""
        nupkg_files = []
        if os.path.exists(directory):
            for file in os.listdir(directory):
                if file.endswith(".nupkg"):
                    nupkg_files.append(os.path.join(directory, file))
        return sorted(nupkg_files, key=os.path.getmtime, reverse=True)

    @staticmethod
    def move_to_uploaded(nupkg_path: str, base_dir: str) -> str:
        """Move successfully uploaded package to 'uploaded' subfolder."""
        uploaded_dir = Path(base_dir) / "uploaded"
        uploaded_dir.mkdir(exist_ok=True)
        
        dest_path = uploaded_dir / Path(nupkg_path).name
        try:
            shutil.move(nupkg_path, dest_path)
            return str(dest_path)
        except Exception as e:
            return f"Error moving file: {e}"

    @staticmethod
    def check_dependency_errors(output: str) -> List[str]:
        """Check for dependency errors in build output."""
        errors = []
        patterns = [
            r"Unable to resolve dependency",
            r"Could not find package",
            r"Package '.*' is not found",
            r"Missing dependency",
            r"NU1101",
            r"NU1102",
        ]
        
        for line in output.split("\n"):
            for pattern in patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    errors.append(line.strip())
                    break
        return errors
