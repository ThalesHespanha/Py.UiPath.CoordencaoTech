import os
import shutil
import re
import subprocess
from typing import Tuple, List, Optional
from pathlib import Path

class PackageManager:
    @staticmethod
    def run_pack(
        project_path: str,
        output_dir: str,
        version: str,
        use_local_cache: bool = True,
        custom_feed_url: Optional[str] = None
    ) -> Tuple[bool, str, str]:
        """Run UiPath CLI pack command."""
        
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
        
        if custom_feed_url and custom_feed_url.strip():
            cmd_parts.extend(["--source", f'"{custom_feed_url.strip()}"'])
        
        cmd = " ".join(cmd_parts)
        
        try:
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
