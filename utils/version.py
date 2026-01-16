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
