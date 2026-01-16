import re
import os
from typing import Optional, Dict
from git import Repo, GitCommandError

def infer_upstream_url(origin_url: str) -> str:
    """
    Infer upstream URL by removing '-fork' or '-Fork' suffix from the repository name.
    
    Example:
        origin: https://github.com/myorg/MyProject-Fork.git
        upstream: https://github.com/myorg/MyProject.git
    """
    # Pattern looks for -fork (case insensitive) optionally followed by .git at the end of the string
    pattern = r"(-fork)(\.git)?$"
    base = re.sub(pattern, "", origin_url, flags=re.IGNORECASE)
    
    # Ensure .git suffix if it was present or if we want to standardize
    if origin_url.endswith(".git") and not base.endswith(".git"):
        base += ".git"
        
    return base

def detect_remote_info(repo_path: str) -> Dict[str, str]:
    """
    Analyze a local git repository to detect origin and infer upstream.
    
    Returns:
        dict: {
            "origin": str,
            "is_fork": bool,
            "inferred_upstream": str,
            "current_upstream": str (if exists)
        }
    """
    result = {
        "origin": "",
        "is_fork": False,
        "inferred_upstream": "",
        "current_upstream": ""
    }
    
    try:
        if not os.path.exists(os.path.join(repo_path, ".git")):
            return result
            
        repo = Repo(repo_path)
        
        # Get Origin
        try:
            origin_url = repo.remotes.origin.url
            result["origin"] = origin_url
            
            # Check if it looks like a fork
            if re.search(r"-fork", origin_url, re.IGNORECASE):
                result["is_fork"] = True
                result["inferred_upstream"] = infer_upstream_url(origin_url)
        except (AttributeError, ValueError):
            pass # No origin remote
            
        # Get Upstream if exists
        try:
            upstream_url = repo.remotes.upstream.url
            result["current_upstream"] = upstream_url
        except (AttributeError, ValueError):
            pass # No upstream remote
            
    except Exception:
        pass
        
    return result
