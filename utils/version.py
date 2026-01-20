from typing import Tuple

def parse_version(version: str) -> Tuple[int, int, int]:
    """Parse semantic version string (X.Y.Z) into a tuple of integers."""
    parts = version.split(".")
    major = int(parts[0]) if len(parts) > 0 else 0
    minor = int(parts[1]) if len(parts) > 1 else 0
    patch = int(parts[2]) if len(parts) > 2 else 0
    return (major, minor, patch)

def increment_version(version: str, bump: str = "patch") -> str:
    """
    Increment semantic version.
    
    Args:
        version (str): Current version string (e.g., "1.0.0")
        bump (str): Type of increment ("patch", "minor", "major")
        
    Returns:
        str: New version string
    """
    major, minor, patch = parse_version(version)
    
    if bump == "major":
        return f"{major + 1}.0.0"
    elif bump == "minor":
        return f"{major}.{minor + 1}.0"
    else:  # patch default
        return f"{major}.{minor}.{patch + 1}"


def update_project_json_version(project_path: str, new_version: str) -> Tuple[bool, str]:
    """
    Update the version in project.json file.
    
    Args:
        project_path: Path to UiPath project folder containing project.json
        new_version: New version string (e.g., "1.2.3")
        
    Returns:
        Tuple of (success, message)
    """
    import os
    import json
    
    project_json_path = os.path.join(project_path, "project.json")
    
    if not os.path.exists(project_json_path):
        return False, f"project.json não encontrado em: {project_path}"
    
    try:
        # Read existing project.json
        with open(project_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        old_version = data.get("projectVersion", "Unknown")
        
        # Update version
        data["projectVersion"] = new_version
        
        # Write back with same formatting
        with open(project_json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        return True, f"Versão atualizada: {old_version} → {new_version}"
        
    except json.JSONDecodeError as e:
        return False, f"Erro ao parsear project.json: {e}"
    except IOError as e:
        return False, f"Erro ao escrever project.json: {e}"
    except Exception as e:
        return False, f"Erro inesperado: {e}"
