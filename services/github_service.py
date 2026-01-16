import streamlit as st
from github import Github, GithubException
from typing import List, Optional, Dict

class GithubService:
    def __init__(self, token: str):
        self.token = token
        self.client = Github(token) if token else None

    def is_authenticated(self) -> bool:
        return self.client is not None

    def get_open_pull_requests(self, repo_name: str) -> List[dict]:
        """Get open pull requests for a specific repository."""
        if not self.client:
            return []
            
        try:
            repo = self.client.get_repo(repo_name)
            pulls = repo.get_pulls(state="open", sort="created", direction="desc")
            
            pr_list = []
            for pr in pulls:
                pr_list.append(self._format_pr(pr))
            
            return pr_list
        except GithubException as e:
            st.error(f"❌ Erro ao buscar PRs de {repo_name}: {e}")
            return []

    def get_team_repos(self, org_name: str, team_slug: str) -> List[str]:
        """Get all repositories accessible by a team."""
        if not self.client:
            return []
            
        try:
            org = self.client.get_organization(org_name)
            team = org.get_team_by_slug(team_slug)
            return [repo.full_name for repo in team.get_repos()]
        except GithubException as e:
            st.error(f"❌ Erro ao buscar repos do time {team_slug}: {e}")
            return []

    def get_all_team_prs(self, repo_names: List[str]) -> List[dict]:
        """Get open PRs from a list of repositories."""
        all_prs = []
        for repo_name in repo_names:
            # We reuse the logic but suppress individual errors to avoid spamming UI
            # or we could just wrap in try/except here
            try:
                repo = self.client.get_repo(repo_name)
                pulls = repo.get_pulls(state="open", sort="created", direction="desc")
                for pr in pulls:
                    formatted = self._format_pr(pr)
                    formatted["repo"] = repo_name # Add repo name for context
                    all_prs.append(formatted)
            except Exception:
                continue
                
        return sorted(all_prs, key=lambda x: x["updated_at"], reverse=True)

    def _format_pr(self, pr) -> dict:
        """Format GitHub PR object to dictionary."""
        return {
            "number": pr.number,
            "title": pr.title,
            "author": pr.user.login,
            "created_at": pr.created_at,
            "updated_at": pr.updated_at,
            "labels": [label.name for label in pr.labels],
            "url": pr.html_url,
            "draft": pr.draft,
            "mergeable": pr.mergeable,
            "head_branch": pr.head.ref,
            "base_branch": pr.base.ref,
        }
