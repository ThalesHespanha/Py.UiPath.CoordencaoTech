import os
import json
from pathlib import Path
from typing import List, Dict, Optional

def scan_local_projects(base_dir: str) -> List[Dict]:
    """
    Scan default directory for UiPath projects by looking for project.json files.
    
    Args:
        base_dir (str): Directory to scan
        
    Returns:
        List[Dict]: List of project info dictionaries
    """
    projects = []
    
    if not os.path.exists(base_dir):
        return projects
        
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
                            
                        projects.append({
                            "name": data.get("name", item),
                            "folder_name": item,
                            "path": item_path,
                            "version": data.get("projectVersion", "1.0.0"),
                            "description": data.get("description", ""),
                            "is_fork": item.lower().endswith("-fork") or item.lower().endswith("fork")
                        })
                    except Exception:
                        # Skip if project.json is invalid
                        continue
                        
    except Exception as e:
        print(f"Error scanning projects: {e}")
        
    # Sort by name
    return sorted(projects, key=lambda x: x["name"].lower())
