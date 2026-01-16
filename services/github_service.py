import streamlit as st
import requests
from github import Github, GithubException
from typing import List, Optional, Dict
from datetime import datetime

class GithubService:
    """GitHub service with GraphQL support for optimized PR fetching."""
    
    GRAPHQL_ENDPOINT = "https://api.github.com/graphql"
    
    def __init__(self, token: str):
        self.token = token
        self.client = Github(token) if token else None

    def is_authenticated(self) -> bool:
        return self.client is not None

    # =========================================
    # GRAPHQL API - Optimized for performance
    # =========================================
    
    def get_org_open_prs_graphql(self, org_name: str, team_repos: List[str] = None) -> List[dict]:
        """
        Fetch ALL open PRs from an organization using GraphQL Search API.
        This is much faster than REST API as it uses a single query.
        
        Args:
            org_name: GitHub organization name
            team_repos: Optional list of repo full names to filter by (e.g., ["org/repo1", "org/repo2"])
        
        Returns:
            List of PRs sorted by updated_at descending
        """
        if not self.token:
            return []
        
        all_prs = []
        cursor = None
        has_next = True
        
        # GraphQL query to search for open PRs in the organization
        query = """
        query($searchQuery: String!, $cursor: String) {
          search(query: $searchQuery, type: ISSUE, first: 100, after: $cursor) {
            pageInfo {
              hasNextPage
              endCursor
            }
            nodes {
              ... on PullRequest {
                number
                title
                url
                isDraft
                createdAt
                updatedAt
                headRefName
                baseRefName
                mergeable
                author {
                  login
                }
                repository {
                  nameWithOwner
                }
                labels(first: 10) {
                  nodes {
                    name
                  }
                }
              }
            }
          }
        }
        """
        
        # Build search query string
        search_query = f"org:{org_name} is:pr is:open"
        
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        
        try:
            while has_next:
                variables = {
                    "searchQuery": search_query,
                    "cursor": cursor
                }
                
                response = requests.post(
                    self.GRAPHQL_ENDPOINT,
                    headers=headers,
                    json={"query": query, "variables": variables},
                    timeout=30
                )
                response.raise_for_status()
                
                data = response.json()
                
                # Check for GraphQL errors
                if "errors" in data:
                    error_msg = data["errors"][0].get("message", "Unknown GraphQL error")
                    st.error(f"❌ GraphQL Error: {error_msg}")
                    break
                
                search_result = data.get("data", {}).get("search", {})
                nodes = search_result.get("nodes", [])
                page_info = search_result.get("pageInfo", {})
                
                # Process each PR
                for node in nodes:
                    if node:  # Skip null nodes
                        formatted = self._format_graphql_pr(node)
                        all_prs.append(formatted)
                
                # Pagination
                has_next = page_info.get("hasNextPage", False)
                cursor = page_info.get("endCursor")
                
        except requests.RequestException as e:
            st.error(f"❌ Erro na requisição GraphQL: {e}")
            return []
        
        # Filter by team repos if provided
        if team_repos:
            team_repos_set = set(team_repos)
            all_prs = [pr for pr in all_prs if pr.get("repo") in team_repos_set]
        
        # Sort by updated_at descending
        all_prs.sort(key=lambda x: x.get("updated_at", datetime.min), reverse=True)
        
        return all_prs
    
    def _format_graphql_pr(self, node: dict) -> dict:
        """Format GraphQL PR node to standard dict format."""
        return {
            "number": node.get("number"),
            "title": node.get("title", ""),
            "author": node.get("author", {}).get("login", "unknown") if node.get("author") else "unknown",
            "created_at": self._parse_datetime(node.get("createdAt")),
            "updated_at": self._parse_datetime(node.get("updatedAt")),
            "labels": [label.get("name", "") for label in node.get("labels", {}).get("nodes", [])],
            "url": node.get("url", ""),
            "draft": node.get("isDraft", False),
            "mergeable": node.get("mergeable") == "MERGEABLE",
            "head_branch": node.get("headRefName", ""),
            "base_branch": node.get("baseRefName", ""),
            "repo": node.get("repository", {}).get("nameWithOwner", ""),
        }
    
    def _parse_datetime(self, dt_str: str) -> datetime:
        """Parse ISO datetime string from GraphQL."""
        if not dt_str:
            return datetime.min
        try:
            # Handle ISO format with Z suffix
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return datetime.min

    # =========================================
    # REST API - Legacy methods (fallback)
    # =========================================

    def get_open_pull_requests(self, repo_name: str) -> List[dict]:
        """Get open pull requests for a specific repository (REST API)."""
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
        """Get open PRs from a list of repositories (REST API - legacy)."""
        all_prs = []
        for repo_name in repo_names:
            try:
                repo = self.client.get_repo(repo_name)
                pulls = repo.get_pulls(state="open", sort="created", direction="desc")
                for pr in pulls:
                    formatted = self._format_pr(pr)
                    formatted["repo"] = repo_name
                    all_prs.append(formatted)
            except Exception:
                continue
                
        return sorted(all_prs, key=lambda x: x["updated_at"], reverse=True)

    def _format_pr(self, pr) -> dict:
        """Format GitHub PR object to dictionary (REST API)."""
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
