"""
UiPath Team Coordinator
=======================
Painel de Controle para gerenciar repositórios Git, Dependências e Deploy de automações UiPath.

Author: DevOps Engineer
Version: 2.0.0 (Modularized)
"""

import os
import tempfile
from typing import Optional

import streamlit as st
from dotenv import load_dotenv
from git import Repo

# Services
from services.project_scanner import scan_local_projects
from services.dependency_scanner import (
    scan_project_dependencies, 
    filter_custom_dependencies,
    resolve_best_version,
    get_display_version,
    format_projects_list,
    DependencyInfo
)
from services.github_service import GithubService
from services.orchestrator import OrchestratorService
from services.package_manager import PackageManager

# Utils
from utils.version import increment_version
from utils.git_helpers import detect_remote_info

# =============================================
# CONFIGURATION & INITIALIZATION
# =============================================

# Load environment variables
load_dotenv()

# Page configuration
st.set_page_config(
    page_title="UiPath Team Coordinator",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        background: linear-gradient(90deg, #FF6B35, #F7931E);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 1rem;
    }
    .section-header {
        font-size: 1.5rem;
        font-weight: 600;
        color: #1E3A5F;
        border-bottom: 2px solid #FF6B35;
        padding-bottom: 0.5rem;
        margin: 1.5rem 0 1rem 0;
    }
    .status-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        margin: 0.5rem 0;
    }
    .success-msg { color: #4caf50; font-weight: bold; }
    .error-msg { color: #f44336; font-weight: bold; }
    
    /* Project Card Style */
    .project-card {
        border: 1px solid #ddd;
        border-radius: 8px;
        padding: 15px;
        margin-bottom: 10px;
        background-color: #f8f9fa;
    }
    .project-title {
        font-size: 1.1em;
        font-weight: bold;
        color: #333;
    }
    .project-meta {
        font-size: 0.9em;
        color: #666;
    }
</style>
""", unsafe_allow_html=True)


# =============================================
# ENVIRONMENT VARIABLES
# =============================================

def get_env_config() -> dict:
    """Load and return environment configuration."""
    return {
        "github_token": os.getenv("GITHUB_TOKEN", ""),
        "github_org": os.getenv("GITHUB_ORG", ""),
        "github_team": os.getenv("GITHUB_TEAM", ""),
        "orch_url": os.getenv("ORCH_URL", "https://cloud.uipath.com"),
        "orch_org": os.getenv("ORCH_ORG_NAME", ""),
        "orch_tenant": os.getenv("ORCH_TENANT_NAME", ""),
        "orch_client_id": os.getenv("ORCH_CLIENT_ID", ""),
        "orch_client_secret": os.getenv("ORCH_CLIENT_SECRET", ""),
        "orch_scope": os.getenv("ORCH_SCOPE", "OR.Default"),
        "custom_nuget_feed": os.getenv("CUSTOM_NUGET_FEED", ""),
        "default_clone_dir": os.getenv("DEFAULT_CLONE_DIR", "C:\\UiPath\\Repos"),
        "default_output_dir": os.getenv("DEFAULT_OUTPUT_DIR", "C:\\UiPath\\Packages"),
        # Custom libs sync settings
        "default_reference_dir": os.getenv("DEFAULT_REFERENCE_DIR", ""),
        "default_libs_download_dir": os.getenv("DEFAULT_LIBS_DOWNLOAD_DIR", "C:\\UiPath\\CustomLibs"),
        "custom_lib_prefixes": os.getenv("CUSTOM_LIB_PREFIXES", ""),
    }


def check_credentials(config: dict) -> dict:
    """Check which credentials are configured."""
    return {
        "GitHub Token": bool(config["github_token"]),
        "Orchestrator URL": bool(config["orch_url"]),
        "Orchestrator Org": bool(config["orch_org"]),
        "Orchestrator Tenant": bool(config["orch_tenant"]),
        "Orchestrator Client ID": bool(config["orch_client_id"]),
        "Orchestrator Client Secret": bool(config["orch_client_secret"]),
    }


# =============================================
# SIDEBAR
# =============================================

def render_sidebar(config: dict):
    """Render the sidebar with configuration status."""
    st.sidebar.markdown("## 🔧 Configurações")
    
    # Check credentials status
    creds = check_credentials(config)
    
    st.sidebar.markdown("### Status das Credenciais")
    for name, status in creds.items():
        icon = "✅" if status else "❌"
        st.sidebar.markdown(f"{icon} {name}")
    
    st.sidebar.markdown("---")
    
    # Custom Feed URL override
    st.sidebar.markdown("### 📦 NuGet Feed")
    
    # Construct default feed from Orchestrator config if available
    default_feed = config["custom_nuget_feed"]
    if not default_feed and all([config["orch_url"], config["orch_org"], config["orch_tenant"]]):
        default_feed = f"{config['orch_url']}/{config['orch_org']}/{config['orch_tenant']}/orchestrator_/nuget/v3/index.json"
    
    custom_feed = st.sidebar.text_input(
        "Custom Feed URL",
        value=default_feed,
        help="URL do feed NuGet (Preenchido automaticamente com o Orchestrator Feed se disponível)"
    )
    
    # Allow overriding scopes in UI for debugging
    custom_scope = st.sidebar.text_input(
        "Orchestrator Scopes",
        value=config["orch_scope"],
        help="Escopos para autenticação (ex: OR.Settings.Read OR.Folders.Read). Ajuste conforme sua External App."
    )
    if custom_scope:
        config["orch_scope"] = custom_scope
    
    st.sidebar.markdown("---")
    
    # Default directories
    st.sidebar.markdown("### 📁 Diretórios Padrão")
    st.sidebar.text_input("Clone Dir", value=config["default_clone_dir"], disabled=True)
    st.sidebar.text_input("Output Dir", value=config["default_output_dir"], disabled=True)
    
    return custom_feed


# =============================================
# HELPER FUNCTIONS
# =============================================

def load_local_projects(base_dir: str):
    """Scan and cache local projects."""
    if "local_projects" not in st.session_state:
        st.session_state["local_projects"] = scan_local_projects(base_dir)
    return st.session_state["local_projects"]


def refresh_projects(base_dir: str):
    """Force refresh of local projects."""
    st.session_state["local_projects"] = scan_local_projects(base_dir)

# =============================================
# SECTIONS
# =============================================

def section_git_operations(config: dict):
    """Git Operations section."""
    st.markdown('<p class="section-header">🔄 Git Operations</p>', unsafe_allow_html=True)
    
    tab1, tab2, tab3 = st.tabs(["📥 Clone Repository", "⬇️ Update from Remote", "🔃 Sync Fork"])
    
    with tab1:
        st.markdown("#### Clone de Repositório")
        
        col1, col2 = st.columns([2, 1])
        with col1:
            repo_url = st.text_input("URL do Repositório", placeholder="https://github.com/org/repo.git")
        with col2:
            target_dir = st.text_input("Diretório Base", value=config["default_clone_dir"])
            
        if st.button("📥 Clonar Repositório", type="primary"):
            if repo_url and target_dir:
                with st.spinner("Clonando..."):
                    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
                    full_target = os.path.join(target_dir, repo_name)
                    
                    try:
                        # Inject token into URL for private repo authentication
                        clone_url = repo_url
                        if config.get("github_token") and "https://" in repo_url:
                            # Format: https://TOKEN@github.com/org/repo.git
                            clone_url = repo_url.replace("https://", f"https://{config['github_token']}@")
                        
                        Repo.clone_from(clone_url, full_target)
                        st.success(f"✅ Clonado em: {full_target}")
                        refresh_projects(config["default_clone_dir"])
                    except Exception as e:
                        st.error(f"❌ Erro: {e}")
    
    with tab2:
        st.markdown("#### 🔄 Atualizar Projetos Locais")
        st.info("ℹ️ Atualiza os repositórios locais com as últimas mudanças do remote (git pull)")
        
        # Load projects
        projects = load_local_projects(config["default_clone_dir"])
        
        if not projects:
            st.warning("⚠️ Nenhum projeto encontrado. Clone algum repositório primeiro.")
        else:
            col_refresh, col_update_all = st.columns([1, 1])
            with col_refresh:
                if st.button("🔄 Refresh Lista", key="refresh_update"):
                    refresh_projects(config["default_clone_dir"])
                    st.rerun()
            with col_update_all:
                update_all = st.button("⬇️ Atualizar TODOS", type="primary")
            
            st.markdown("---")
            
            # Track update results
            if update_all:
                progress = st.progress(0)
                status_text = st.empty()
                results = {"success": 0, "failed": 0, "errors": []}
                
                for idx, project in enumerate(projects):
                    status_text.text(f"Atualizando {project['name']}...")
                    success, msg = git_pull_project(project['path'], config.get("github_token"))
                    
                    if success:
                        results["success"] += 1
                    else:
                        results["failed"] += 1
                        results["errors"].append(f"{project['name']}: {msg}")
                    
                    progress.progress((idx + 1) / len(projects))
                
                status_text.empty()
                st.success(f"✅ {results['success']} projetos atualizados com sucesso!")
                if results["failed"] > 0:
                    st.warning(f"⚠️ {results['failed']} projetos com erros:")
                    for err in results["errors"]:
                        st.text(f"  • {err}")
            else:
                # Display individual projects with update buttons
                for project in projects:
                    with st.container():
                        cols = st.columns([0.35, 0.08, 0.57])
                        
                        with cols[0]:
                            st.markdown(f"**📁 {project['name']}**")
                            st.caption(f"v{project['version']}")
                        
                        with cols[1]:
                            # Check if repo has changes
                            try:
                                repo = Repo(project['path'])
                                is_dirty = repo.is_dirty(untracked_files=True)
                                if is_dirty:
                                    st.warning("⚠️")
                                else:
                                    st.success("✓")
                            except Exception:
                                st.error("❌")
                                is_dirty = False
                        
                        with cols[2]:
                            btn_cols = st.columns(3)
                            
                            # Pull button
                            with btn_cols[0]:
                                if st.button("⬇️ Pull", key=f"pull_{project['name']}"):
                                    with st.spinner("Pulling..."):
                                        success, msg = git_pull_project(project['path'], config.get("github_token"))
                                        if success:
                                            st.toast(f"✅ {msg}")
                                        else:
                                            st.error(f"❌ {msg}")
                            
                            # Push button (with commit message popup)
                            with btn_cols[1]:
                                with st.popover("⬆️ Push"):
                                    st.markdown("**Commit & Push**")
                                    commit_msg = st.text_area(
                                        "Mensagem do Commit",
                                        placeholder="Descreva as alterações...",
                                        key=f"commit_msg_{project['name']}",
                                        height=80
                                    )
                                    if st.button("🚀 Enviar", key=f"push_btn_{project['name']}", type="primary"):
                                        if commit_msg.strip():
                                            success, msg = git_commit_push(project['path'], commit_msg, config.get("github_token"))
                                            if success:
                                                st.success(f"✅ {msg}")
                                            else:
                                                st.error(f"❌ {msg}")
                                        else:
                                            st.warning("⚠️ Digite uma mensagem de commit")
                            
                            # Undo button
                            with btn_cols[2]:
                                with st.popover("↩️ Undo"):
                                    st.markdown("**⚠️ Descartar Mudanças**")
                                    st.caption("Isso vai desfazer TODAS as alterações locais não commitadas.")
                                    if st.button("🗑️ Confirmar Undo", key=f"undo_btn_{project['name']}", type="primary"):
                                        success, msg = git_undo_changes(project['path'])
                                        if success:
                                            st.success(f"✅ {msg}")
                                            st.rerun()
                                        else:
                                            st.error(f"❌ {msg}")
                        
                        st.markdown("---")

    with tab3:
        st.markdown("#### Sincronizar Fork com Upstream")
        
        # Project Selector
        projects = load_local_projects(config["default_clone_dir"])
        project_options = {p["name"]: p for p in projects}
        
        # Display Grid Project Cards
        if projects:
            st.markdown("##### 📁 Projetos Locais Disponíveis")
            for project in projects:
                with st.container():
                     cols = st.columns([0.1, 0.6, 0.3])
                     cols[0].markdown("📁")
                     cols[1].markdown(f"**{project['name']}** (v{project['version']})")
                     if project.get('is_fork'):
                         cols[2].markdown("`🍴 Fork`")
        
        st.markdown("---")

        col_sel, col_btn = st.columns([3, 1])
        with col_sel:
            selected_name = st.selectbox("Selecione o Projeto Local para Sync", options=list(project_options.keys()) if projects else [], key="sync_select")
        with col_btn:
            st.write("") # Spacer
            st.write("")
            if st.button("🔄 Refresh Lista", key="refresh_sync"):
                refresh_projects(config["default_clone_dir"])
                st.rerun()

        if selected_name:
            project = project_options[selected_name]
            st.info(f"📁 Path: `{project['path']}`")
            
            # Auto-detect upstream
            remote_info = detect_remote_info(project['path'])
            default_upstream = remote_info.get("current_upstream") or remote_info.get("inferred_upstream") or ""
            
            col1, col2 = st.columns(2)
            with col1:
                upstream_url = st.text_input("URL do Upstream", value=default_upstream)
                if remote_info.get("is_fork"):
                    st.caption("ℹ️ Detectado que é um fork. Upstream sugerido.")
            
            with col2:
                branch = st.text_input("Branch", value="main")
                
            if st.button("🔃 Sincronizar (Fetch Upstream + Reset + Push)", type="primary"):
                if upstream_url:
                    with st.spinner("Sincronizando..."):
                        try:
                            repo = Repo(project['path'])
                            
                            # Add/Update upstream
                            if "upstream" in repo.remotes:
                                repo.remotes.upstream.set_url(upstream_url)
                            else:
                                repo.create_remote("upstream", upstream_url)
                                
                            repo.remotes.upstream.fetch()
                            repo.git.reset("--hard", f"upstream/{branch}")
                            repo.remotes.origin.push(force=True)
                            
                            st.success(f"✅ Sincronizado com upstream/{branch} com sucesso!")
                        except Exception as e:
                            st.error(f"❌ Erro Git: {e}")
                else:
                    st.warning("⚠️ Informe a URL do Upstream")


def git_pull_project(project_path: str, github_token: str = None) -> tuple:
    """
    Perform git pull on a project.
    Returns (success: bool, message: str)
    """
    try:
        repo = Repo(project_path)
        
        # Check if repo is dirty (has uncommitted changes)
        if repo.is_dirty():
            return False, "Há mudanças não commitadas. Faça commit ou stash primeiro."
        
        # Get current branch
        current_branch = repo.active_branch.name
        
        # Configure credentials if token provided
        origin = repo.remotes.origin
        original_url = origin.url
        
        # Inject token for private repos
        if github_token and "https://" in original_url and "@" not in original_url:
            auth_url = original_url.replace("https://", f"https://{github_token}@")
            origin.set_url(auth_url)
        
        try:
            # Fetch and pull
            origin.fetch()
            origin.pull(current_branch)
            message = f"Atualizado branch '{current_branch}'"
        finally:
            # Restore original URL (don't leave token in config)
            if github_token and "https://" in original_url:
                origin.set_url(original_url)
        
        return True, message
        
    except Exception as e:
        return False, str(e)


def git_commit_push(project_path: str, commit_message: str, github_token: str = None) -> tuple:
    """
    Perform git add, commit, and push on a project.
    Returns (success: bool, message: str)
    """
    try:
        repo = Repo(project_path)
        
        # Check if there are any changes to commit
        if not repo.is_dirty(untracked_files=True):
            return False, "Não há mudanças para commitar."
        
        # Get current branch
        current_branch = repo.active_branch.name
        
        # Stage all changes (git add .)
        repo.git.add('--all')
        
        # Commit
        repo.index.commit(commit_message)
        
        # Configure credentials and push
        origin = repo.remotes.origin
        original_url = origin.url
        
        # Inject token for private repos
        if github_token and "https://" in original_url and "@" not in original_url:
            auth_url = original_url.replace("https://", f"https://{github_token}@")
            origin.set_url(auth_url)
        
        try:
            # Push
            origin.push(current_branch)
            message = f"Commit e push realizados no branch '{current_branch}'"
        finally:
            # Restore original URL (don't leave token in config)
            if github_token and "https://" in original_url:
                origin.set_url(original_url)
        
        return True, message
        
    except Exception as e:
        return False, str(e)


def git_undo_changes(project_path: str) -> tuple:
    """
    Discard all local uncommitted changes (git checkout . and clean untracked).
    Returns (success: bool, message: str)
    """
    try:
        repo = Repo(project_path)
        
        # Check if there are any changes to undo
        if not repo.is_dirty(untracked_files=True):
            return False, "Não há mudanças para desfazer."
        
        # Discard all tracked file changes (git checkout .)
        repo.git.checkout('--', '.')
        
        # Remove untracked files (git clean -fd)
        repo.git.clean('-fd')
        
        return True, "Todas as mudanças locais foram descartadas."
        
    except Exception as e:
        return False, str(e)


def section_pull_requests(config: dict):
    """Pull Request Dashboard section - using GraphQL for optimized performance."""
    st.markdown('<p class="section-header">📋 Pull Request Dashboard</p>', unsafe_allow_html=True)
    
    if not config["github_token"]:
        st.warning("⚠️ Configure o GITHUB_TOKEN no arquivo .env")
        return

    gh_service = GithubService(config["github_token"])
    
    # Inputs
    cols = st.columns([2, 2, 1, 1])
    with cols[0]:
        org_name = st.text_input("Organização", value=config["github_org"], placeholder="Ex: smarthis-ai")
    with cols[1]:
        team_slug = st.text_input("Team Slug", value=config["github_team"], placeholder="Ex: fs")
    with cols[2]:
        st.write("")
        st.write("")
        search_btn = st.button("🔄 Buscar PRs", type="primary")
    with cols[3]:
        st.write("")
        st.write("")
        force_refresh = st.button("🗑️ Limpar Cache")

    if force_refresh:
        st.cache_data.clear()
        st.success("✅ Cache limpo! Clique em 'Buscar PRs' novamente.")

    st.markdown("---")

    if search_btn and org_name:
        import time
        start_time = time.time()
        
        # First get team repos (for filtering)
        team_repos = None
        if team_slug:
            with st.spinner("Buscando repositórios do time..."):
                team_repos = gh_service.get_team_repos(org_name, team_slug)
                if team_repos:
                    st.info(f"🔍 Encontrados {len(team_repos)} repositórios no time '{team_slug}'")
                else:
                    st.warning(f"⚠️ Nenhum repositório encontrado para o time '{team_slug}'. Buscando PRs de toda a organização.")
        
        # Use GraphQL to fetch ALL open PRs (much faster!)
        with st.spinner("Buscando PRs via GraphQL (otimizado)..."):
            prs = fetch_org_prs_cached(config["github_token"], org_name, tuple(team_repos) if team_repos else None)
        
        elapsed = time.time() - start_time
        
        if not prs:
            st.info("🎉 Nenhum PR aberto encontrado!")
        else:
            st.markdown(f"### 📊 {len(prs)} Pull Requests Abertos")
            st.caption(f"⚡ Tempo de busca: {elapsed:.2f}s")
            
            for pr in prs:
                with st.expander(f"[{pr.get('repo', 'Unknown')}] #{pr['number']} - {pr['title']}"):
                    c1, c2, c3 = st.columns([2, 2, 1])
                    
                    with c1:
                        st.markdown(f"**👤 Autor:** {pr['author']}")
                        st.markdown(f"**🌿 Branch:** `{pr['head_branch']}` ➝ `{pr['base_branch']}`")
                    
                    with c2:
                        updated_at = pr['updated_at']
                        if hasattr(updated_at, 'strftime'):
                            st.markdown(f"**📅 Atualizado:** {updated_at.strftime('%d/%m/%Y %H:%M')}")
                        else:
                            st.markdown(f"**📅 Atualizado:** {updated_at}")
                        if pr['labels']:
                            st.markdown(f"**🏷️ Labels:** {', '.join(pr['labels'])}")
                    
                    with c3:
                        st.markdown(f"[🔗 Abrir no GitHub]({pr['url']})")
                        if pr['draft']:
                            st.warning("🚧 Draft")
                        else:
                            st.success("✅ Ready")


@st.cache_data(ttl=600, show_spinner=False)
def fetch_org_prs_cached(token: str, org_name: str, team_repos: tuple = None) -> list:
    """
    Cached function to fetch PRs via GraphQL.
    TTL = 600 seconds (10 minutes).
    team_repos must be a tuple (immutable) for caching to work.
    """
    gh_service = GithubService(token)
    return gh_service.get_org_open_prs_graphql(org_name, list(team_repos) if team_repos else None)


def section_build_publish(config: dict, custom_feed: str):
    """Build & Publish section."""
    st.markdown('<p class="section-header">📦 Build & Publish</p>', unsafe_allow_html=True)
    
    tab1, tab2, tab3 = st.tabs(["🔨 Build (Pack)", "🚀 Publish (Upload)", "📚 Libraries (Cache)"])
    
    # --- BUILD TAB ---
    with tab1:
        pm = PackageManager()
        
        projects = load_local_projects(config["default_clone_dir"])
        project_options = {f"{p['name']} (v{p['version']})": p for p in projects}
        
        col1, col2 = st.columns(2)
        with col1:
            selected_label = st.selectbox("Selecione o Projeto", options=list(project_options.keys()) if projects else [])
        with col2:
             st.write("")
             if st.button("🔄 Refresh Projetos", key="refresh_build"):
                refresh_projects(config["default_clone_dir"])
                st.rerun()
        
        if selected_label:
            project = project_options[selected_label]
            current_version = project['version']
            
            st.markdown(f"""
                <div class="project-card">
                    <div class="project-title">🔨 {project['name']}</div>
                    <div class="project-meta">Versão Atual: <b>{current_version}</b> | Path: {project['path']}</div>
                </div>
            """, unsafe_allow_html=True)
            
            st.markdown("#### 🔢 Versionamento")
            
            # Version Bumping
            bump_type = st.radio(
                "Incrementar Versão:", 
                ["Manter Atual", "Patch (+0.0.1)", "Minor (+0.1.0)", "Major (+1.0.0)"], 
                horizontal=True
            )
            
            new_version = current_version
            if "Patch" in bump_type:
                new_version = increment_version(current_version, "patch")
            elif "Minor" in bump_type:
                new_version = increment_version(current_version, "minor")
            elif "Major" in bump_type:
                new_version = increment_version(current_version, "major")
                
            col_v1, col_v2 = st.columns(2)
            with col_v1:
                final_version = st.text_input("Versão Final para Pack", value=new_version)
            with col_v2:
                output_dir = st.text_input("Output Dir", value=config["default_output_dir"])
            
            st.checkbox("Usar dependências locais", value=True, key="use_local_cache", disabled=True)
            
            st.markdown("---")
            
            if st.button("📦 Criar Pacote (Pack)", type="primary"):
                with st.spinner(f"Criando pacote v{final_version}..."):
                    success, cmd, output = pm.run_pack(
                        project_path=project['path'],
                        output_dir=output_dir,
                        version=final_version,
                        custom_feed_url=custom_feed,
                        auth_config=config  # Pass full config for auth
                    )
                    
                    st.code(cmd, language="bash")
                    if success:
                        st.success("✅ Build realizado com sucesso!")
                        st.text_area("Log de Output", output, height=100)
                    else:
                        st.error("❌ Falha no build")
                        st.text_area("Erro", output, height=150)
                        
                        errors = pm.check_dependency_errors(output)
                        if errors:
                            st.warning("⚠️ Erros de Dependência:")
                            for err in errors:
                                st.markdown(f"- {err}")

    # --- PUBLISH TAB ---
    with tab2:
        st.markdown("#### 🚀 Publicação (Tenant Level)")
        st.info("ℹ️ Os pacotes serão publicados no Tenant, ficando disponíveis para todas as pastas (Modern Folders).")
        
        orch_service = OrchestratorService(config)
        pm = PackageManager()
        
        packages_dir = st.text_input("Diretório de Pacotes", value=config["default_output_dir"], key="pub_dir")
        
        all_packages = pm.find_nupkg_files(packages_dir)
        
        # Split into Pending and Uploaded logic
        uploaded_dir = os.path.join(packages_dir, "uploaded")
        uploaded_packages = pm.find_nupkg_files(uploaded_dir) if os.path.exists(uploaded_dir) else []
        
        # We only want to show packages in the root dir as "Pending" (exclude uploaded subfolder if scanned)
        pending_packages = [p for p in all_packages if "uploaded" not in p]
        
        st.markdown(f"### ⏳ Pendentes ({len(pending_packages)})")
        
        # Multi-select for batch upload
        selected_packages = []
        if not pending_packages:
            st.info("Nenhum pacote pendente encontrado.")
        else:
            with st.container():
                for pkg in pending_packages:
                    c1, c2 = st.columns([0.1, 0.9])
                    if c1.checkbox("", key=f"chk_{pkg}"):
                        selected_packages.append(pkg)
                    c2.markdown(f"📦 `{os.path.basename(pkg)}`")
            
            st.markdown("---")
            if st.button(f"🚀 Enviar {len(selected_packages)} Pacotes Selecionados", disabled=len(selected_packages)==0, type="primary"):
                token = orch_service.get_token()
                if token:
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    for idx, pkg_path in enumerate(selected_packages):
                        pkg_name = os.path.basename(pkg_path)
                        status_text.text(f"Enviando {pkg_name}...")
                        
                        success, msg = orch_service.upload_package(token, pkg_path)
                        
                        if success:
                            st.toast(f"✅ {pkg_name} enviado!")
                            pm.move_to_uploaded(pkg_path, packages_dir)
                        else:
                            st.error(f"❌ Falha em {pkg_name}: {msg}")
                            
                        progress_bar.progress((idx + 1) / len(selected_packages))
                        
                    st.success("Operação concluída!")
                    st.rerun()
                
        if uploaded_packages:
            st.markdown("---")
            with st.expander(f"✅ Já Enviados (Pasta /uploaded) - {len(uploaded_packages)}"):
                for pkg in uploaded_packages:
                    st.text(f"✔️ {os.path.basename(pkg)}")

    # --- LIBRARIES TAB ---
    with tab3:
        st.markdown("#### 📚 Gerenciamento de Libraries")
        st.info("ℹ️ Baixe libraries do Orchestrator para o cache local NuGet. Isso resolve problemas de autenticação durante o build.")
        
        orch_service = OrchestratorService(config)
        
        # Search and list libraries
        col_search, col_btn = st.columns([3, 1])
        with col_search:
            search_term = st.text_input(
                "Buscar Library", 
                placeholder="Ex: Smarthis",
                help="Busca pelo ID da library no Orchestrator"
            )
        with col_btn:
            st.write("")
            st.write("")
            search_clicked = st.button("🔍 Buscar", type="primary")
        
        if search_clicked and search_term:
            with st.spinner("Buscando libraries no Orchestrator (incluindo todas versões)..."):
                token = orch_service.get_token()
                if token:
                    # Use the new method that fetches all versions for each package
                    grouped = orch_service.list_libraries_with_all_versions(token, search_term)
                    
                    if grouped:
                        st.session_state["grouped_libraries"] = grouped
                        total_versions = sum(len(pkg["versions"]) for pkg in grouped.values())
                        st.success(f"✅ Encontrados {len(grouped)} pacotes com {total_versions} versões")
                    else:
                        st.warning("Nenhuma library encontrada com esse termo")
                        st.session_state["grouped_libraries"] = {}
                else:
                    st.error("❌ Falha ao autenticar no Orchestrator")
        
        # Display found libraries grouped by package
        if "grouped_libraries" in st.session_state and st.session_state["grouped_libraries"]:
            st.markdown("---")
            st.markdown("### 📋 Libraries Encontradas")
            st.caption("Selecione os pacotes e versões que deseja baixar:")
            
            # Initialize selection state
            if "lib_selections" not in st.session_state:
                st.session_state["lib_selections"] = {}
            
            for pkg_id, pkg_info in st.session_state["grouped_libraries"].items():
                with st.container():
                    col1, col2, col3 = st.columns([0.08, 0.52, 0.40])
                    
                    with col1:
                        is_selected = st.checkbox("", key=f"pkg_sel_{pkg_id}", value=pkg_id in st.session_state.get("lib_selections", {}))
                    
                    with col2:
                        st.markdown(f"**{pkg_id}**")
                        if pkg_info.get("authors"):
                            st.caption(f"por {pkg_info['authors']}")
                    
                    with col3:
                        # Version dropdown
                        versions = pkg_info["versions"]
                        selected_version = st.selectbox(
                            "Versão",
                            options=versions,
                            key=f"pkg_ver_{pkg_id}",
                            label_visibility="collapsed"
                        )
                        
                        # Update selection state
                        if is_selected:
                            st.session_state["lib_selections"][pkg_id] = selected_version
                        elif pkg_id in st.session_state.get("lib_selections", {}):
                            del st.session_state["lib_selections"][pkg_id]
            
            st.markdown("---")
            
            selected_count = len(st.session_state.get("lib_selections", {}))
            
            if st.button(f"📥 Baixar e Instalar {selected_count} Libraries Selecionadas", 
                        disabled=selected_count == 0, 
                        type="primary"):
                token = orch_service.get_token()
                if token:
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    # Create temp directory for downloads
                    import tempfile
                    with tempfile.TemporaryDirectory() as temp_dir:
                        selections = list(st.session_state["lib_selections"].items())
                        for idx, (lib_id, lib_version) in enumerate(selections):
                            
                            status_text.text(f"Baixando {lib_id} v{lib_version}...")
                            
                            # Download
                            success, result = orch_service.download_library(token, lib_id, lib_version, temp_dir)
                            
                            if success:
                                # Install to cache
                                status_text.text(f"Instalando {lib_id} no cache...")
                                install_success, install_msg = orch_service.install_nupkg_to_cache(result)
                                
                                if install_success:
                                    st.toast(f"✅ {lib_id} v{lib_version} instalado!")
                                else:
                                    st.error(f"❌ Erro ao instalar {lib_id}: {install_msg}")
                            else:
                                st.error(f"❌ Erro ao baixar {lib_id}: {result}")
                            
                            progress_bar.progress((idx + 1) / len(selections))
                    
                    st.success("✅ Operação concluída! Agora você pode executar o Build.")
                    # Clear selections
                    st.session_state["lib_selections"] = {}
                else:
                    st.error("❌ Falha ao obter token de autenticação")
        
        # Quick install section
        st.markdown("---")
        with st.expander("⚡ Instalação Rápida (Digite ID e Versão)"):
            col_id, col_ver = st.columns(2)
            with col_id:
                quick_lib_id = st.text_input("Library ID", placeholder="Smarthis.Common.Activities")
            with col_ver:
                quick_lib_version = st.text_input("Versão", placeholder="1.0.0")
            
            if st.button("📥 Baixar e Instalar", key="quick_install"):
                if quick_lib_id and quick_lib_version:
                    token = orch_service.get_token()
                    if token:
                        with st.spinner(f"Baixando {quick_lib_id}..."):
                            import tempfile
                            with tempfile.TemporaryDirectory() as temp_dir:
                                success, result = orch_service.download_library(
                                    token, quick_lib_id, quick_lib_version, temp_dir
                                )
                                
                                if success:
                                    install_success, install_msg = orch_service.install_nupkg_to_cache(result)
                                    if install_success:
                                        st.success(install_msg)
                                    else:
                                        st.error(install_msg)
                                else:
                                    st.error(result)
                    else:
                        st.error("❌ Falha ao autenticar")
                else:
                    st.warning("⚠️ Preencha ID e Versão da library")
        
        # =============================================
        # NEW: Custom Libraries Sync from Reference Folder
        # =============================================
        st.markdown("---")
        with st.expander("🔁 Sincronizar libs custom dos projetos (pasta referência)"):
            st.info("ℹ️ Detecta e baixa automaticamente todas as libs customizadas usadas nos projetos de uma pasta referência.")
            
            # --- Configuration Inputs ---
            col_ref, col_dest = st.columns(2)
            with col_ref:
                # Default: use DEFAULT_REFERENCE_DIR if set, otherwise DEFAULT_CLONE_DIR
                default_ref = config.get("default_reference_dir") or config["default_clone_dir"]
                reference_dir = st.text_input(
                    "📁 Pasta Referência (projetos UiPath)",
                    value=default_ref,
                    help="Pasta contendo subpastas com projetos UiPath (project.json)"
                )
            with col_dest:
                download_dir = st.text_input(
                    "📥 Pasta Destino (.nupkg)",
                    value=config.get("default_libs_download_dir") or "C:\\UiPath\\CustomLibs",
                    help="Onde salvar os arquivos .nupkg baixados"
                )
            
            # Options row
            col_opt1, col_opt2, col_opt3 = st.columns(3)
            with col_opt1:
                install_to_cache = st.checkbox(
                    "Instalar no cache NuGet",
                    value=True,
                    help="Também instala em ~/.nuget/packages após baixar"
                )
            with col_opt2:
                skip_existing = st.checkbox(
                    "Pular se já existe",
                    value=True,
                    help="Não baixa novamente se arquivo já existe na pasta destino"
                )
            with col_opt3:
                use_prefix_filter = st.checkbox(
                    "Filtrar por prefixos",
                    value=True,
                    help="Filtra apenas libs que começam com prefixos custom"
                )
            
            # Prefix input (shown only if filter enabled)
            if use_prefix_filter:
                default_prefixes = config.get("custom_lib_prefixes") or "Smarthis.,FS.,Ball."
                custom_prefixes_input = st.text_input(
                    "Prefixos custom (vírgula)",
                    value=default_prefixes,
                    help="Ex: Smarthis.,FS.,Ball. - Se vazio, exclui apenas pacotes oficiais (UiPath., System., Microsoft.)"
                )
                custom_prefixes = [p.strip() for p in custom_prefixes_input.split(",") if p.strip()]
            else:
                custom_prefixes = None
            
            st.markdown("---")
            
            # --- Detect Dependencies Button ---
            col_detect, col_download = st.columns(2)
            
            with col_detect:
                detect_clicked = st.button("🔎 Detectar dependências", type="primary", key="detect_deps")
            
            if detect_clicked:
                if not reference_dir or not os.path.exists(reference_dir):
                    st.error(f"❌ Pasta referência não encontrada: {reference_dir}")
                else:
                    with st.spinner("Escaneando projetos e dependências..."):
                        # Scan all projects
                        all_deps = scan_project_dependencies(reference_dir)
                        
                        if not all_deps:
                            st.warning("⚠️ Nenhuma dependência encontrada. Verifique se a pasta contém projetos UiPath com project.json.")
                        else:
                            # Filter to custom libs only
                            custom_deps = filter_custom_dependencies(
                                all_deps, 
                                custom_prefixes if use_prefix_filter else None,
                                use_prefix_filter
                            )
                            
                            if not custom_deps:
                                st.warning("⚠️ Nenhuma lib custom encontrada com os filtros atuais.")
                            else:
                                st.success(f"✅ Encontradas {len(custom_deps)} libs custom em {len(all_deps)} dependências totais")
                                
                                # Get token for validation
                                token = orch_service.get_token()
                                if not token:
                                    st.error("❌ Falha ao autenticar no Orchestrator")
                                else:
                                    # Validate each lib against Orchestrator
                                    version_cache = {}
                                    progress = st.progress(0)
                                    status_placeholder = st.empty()
                                    
                                    dep_list = list(custom_deps.items())
                                    for idx, (pkg_id, dep_info) in enumerate(dep_list):
                                        status_placeholder.text(f"Verificando {pkg_id}...")
                                        
                                        # Check if exists in Orchestrator
                                        exists, available_versions = orch_service.check_library_exists(
                                            token, pkg_id, version_cache
                                        )
                                        
                                        dep_info.exists_in_orchestrator = exists
                                        dep_info.available_versions = available_versions
                                        
                                        # Resolve best version
                                        if exists and available_versions:
                                            first_spec = next(iter(dep_info.version_specs))
                                            dep_info.resolved_version = resolve_best_version(
                                                available_versions, first_spec
                                            )
                                        
                                        progress.progress((idx + 1) / len(dep_list))
                                    
                                    status_placeholder.empty()
                                    progress.empty()
                                    
                                    # Store in session state for download
                                    st.session_state["custom_deps_detected"] = custom_deps
                                    st.session_state["sync_download_dir"] = download_dir
                                    st.session_state["sync_install_cache"] = install_to_cache
                                    st.session_state["sync_skip_existing"] = skip_existing
                                    
                                    # Display results table
                                    st.markdown("### 📋 Libs Custom Detectadas")
                                    
                                    # Build table data
                                    table_data = []
                                    for pkg_id, dep_info in sorted(custom_deps.items()):
                                        status = "✅ Encontrada" if dep_info.exists_in_orchestrator else "❌ Não encontrada"
                                        version = get_display_version(dep_info)
                                        projects = format_projects_list(dep_info.projects)
                                        table_data.append({
                                            "Pacote": pkg_id,
                                            "Versão": version,
                                            "Projetos": projects,
                                            "Status": status
                                        })
                                    
                                    # Use st.dataframe for nice display
                                    import pandas as pd
                                    df = pd.DataFrame(table_data)
                                    st.dataframe(df, use_container_width=True, hide_index=True)
                                    
                                    # Summary
                                    found_count = sum(1 for d in custom_deps.values() if d.exists_in_orchestrator)
                                    not_found = len(custom_deps) - found_count
                                    st.info(f"📊 **Resumo:** {found_count} disponíveis para download, {not_found} não encontradas no Orchestrator")
            
            # --- Download Button ---
            with col_download:
                download_clicked = st.button(
                    "📥 Baixar todas as libs", 
                    type="secondary", 
                    key="download_all_custom",
                    disabled="custom_deps_detected" not in st.session_state
                )
            
            if download_clicked and "custom_deps_detected" in st.session_state:
                custom_deps = st.session_state["custom_deps_detected"]
                target_dir = st.session_state.get("sync_download_dir", download_dir)
                do_install = st.session_state.get("sync_install_cache", install_to_cache)
                do_skip = st.session_state.get("sync_skip_existing", skip_existing)
                
                # Filter to only libs that exist
                to_download = {
                    pkg_id: info for pkg_id, info in custom_deps.items() 
                    if info.exists_in_orchestrator and info.resolved_version
                }
                
                if not to_download:
                    st.warning("⚠️ Nenhuma lib disponível para download.")
                else:
                    token = orch_service.get_token()
                    if not token:
                        st.error("❌ Falha ao autenticar no Orchestrator")
                    else:
                        progress = st.progress(0)
                        status_text = st.empty()
                        results = {"success": 0, "skipped": 0, "failed": 0, "errors": []}
                        
                        download_list = list(to_download.items())
                        for idx, (pkg_id, dep_info) in enumerate(download_list):
                            version = dep_info.resolved_version
                            status_text.text(f"Baixando {pkg_id} v{version}...")
                            
                            # Download
                            success, result = orch_service.download_library_persistent(
                                token, pkg_id, version, target_dir, do_skip
                            )
                            
                            if success:
                                # Check if it was skipped (file already existed)
                                expected_file = os.path.join(target_dir, f"{pkg_id}.{version}.nupkg")
                                
                                # Install to cache if enabled
                                if do_install:
                                    status_text.text(f"Instalando {pkg_id} no cache...")
                                    inst_ok, inst_msg = orch_service.install_nupkg_to_cache(result)
                                    if inst_ok:
                                        results["success"] += 1
                                        st.toast(f"✅ {pkg_id} v{version}")
                                    else:
                                        results["failed"] += 1
                                        results["errors"].append(f"{pkg_id}: {inst_msg}")
                                else:
                                    results["success"] += 1
                                    st.toast(f"✅ {pkg_id} v{version}")
                            else:
                                results["failed"] += 1
                                results["errors"].append(f"{pkg_id}: {result}")
                            
                            progress.progress((idx + 1) / len(download_list))
                        
                        status_text.empty()
                        progress.empty()
                        
                        # Final summary
                        st.markdown("### 📊 Resultado do Download")
                        col_s1, col_s2 = st.columns(2)
                        col_s1.metric("✅ Sucesso", results["success"])
                        col_s2.metric("❌ Falhas", results["failed"])
                        
                        if results["errors"]:
                            with st.expander("⚠️ Detalhes dos erros"):
                                for err in results["errors"]:
                                    st.text(f"• {err}")
                        
                        st.success(f"✅ Download concluído! Arquivos salvos em: {target_dir}")
                        
                        # Clear session state
                        if "custom_deps_detected" in st.session_state:
                            del st.session_state["custom_deps_detected"]


def section_tenant_migration(config: dict):
    """Tenant Migration section."""
    st.markdown('<p class="section-header">🔄 Tenant Migration</p>', unsafe_allow_html=True)
    st.info("ℹ️ Migração simplificada usando os novos serviços.")
    
    orch = OrchestratorService(config)
    
    c1, c2 = st.columns(2)
    source_tenant = c1.text_input("Tenant Origem", value=config["orch_tenant"])
    dest_tenant = c2.text_input("Tenant Destino")
    
    pkg_id = st.text_input("ID do Pacote")
    pkg_ver = st.text_input("Versão")
    
    if st.button("Migrar Pacote"):
        if source_tenant and dest_tenant and pkg_id and pkg_ver:
            with st.spinner("Processando..."):
                # 1. Auth Source
                orch.tenant = source_tenant
                t1 = orch.get_token()
                if not t1: return
                
                # 2. Download
                tmp = tempfile.gettempdir()
                ok, path = orch.download_package(t1, pkg_id, pkg_ver, tmp)
                if not ok: 
                    st.error(path)
                    return
                st.info(f"Baixado: {path}")
                
                # 3. Auth Dest
                orch.tenant = dest_tenant
                t2 = orch.get_token()
                if not t2: return
                
                # 4. Upload
                ok, msg = orch.upload_package(t2, path)
                if ok:
                    st.success(f"Migrado com sucesso! {msg}")
                else:
                    st.error(f"Erro no upload: {msg}")
                
                # Cleanup
                try: os.remove(path) 
                except: pass


# =============================================
# MAIN APPLICATION
# =============================================

def main():
    """Main application entry point."""
    st.markdown('<p class="main-header">🤖 UiPath Team Coordinator</p>', unsafe_allow_html=True)
    st.markdown("*Painel de Controle Modular - v2.0*")
    st.markdown("---")
    
    config = get_env_config()
    custom_feed = render_sidebar(config)
    
    tabs = st.tabs([
        "🔄 Git Operations",
        "📋 Pull Requests",
        "📦 Build & Publish",
        "🔄 Migração"
    ])
    
    with tabs[0]:
        section_git_operations(config)
    
    with tabs[1]:
        section_pull_requests(config)
    
    with tabs[2]:
        section_build_publish(config, custom_feed)
    
    with tabs[3]:
        section_tenant_migration(config)
    
    st.markdown("---")
    st.caption("UiPath Team Coordinator | Architecture: Modular Services")


if __name__ == "__main__":
    main()
