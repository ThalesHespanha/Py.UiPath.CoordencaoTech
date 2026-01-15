"""
UiPath Team Coordinator
=======================
Painel de Controle para gerenciar repositórios Git, Dependências e Deploy de automações UiPath.

Author: DevOps Engineer
Version: 1.0.0
"""

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Tuple

import streamlit as st
import requests
from dotenv import load_dotenv
from git import Repo, GitCommandError
from github import Github, GithubException


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
    .error-highlight {
        background-color: #ffebee;
        border-left: 4px solid #f44336;
        padding: 1rem;
        margin: 1rem 0;
        border-radius: 4px;
    }
    .success-highlight {
        background-color: #e8f5e9;
        border-left: 4px solid #4caf50;
        padding: 1rem;
        margin: 1rem 0;
        border-radius: 4px;
    }
    .warning-highlight {
        background-color: #fff3e0;
        border-left: 4px solid #ff9800;
        padding: 1rem;
        margin: 1rem 0;
        border-radius: 4px;
    }
    .pr-card {
        background: white;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .metric-container {
        display: flex;
        justify-content: space-around;
        flex-wrap: wrap;
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
        "orch_url": os.getenv("ORCH_URL", "https://cloud.uipath.com"),
        "orch_tenant": os.getenv("ORCH_TENANT_NAME", ""),
        "orch_client_id": os.getenv("ORCH_CLIENT_ID", ""),
        "orch_client_secret": os.getenv("ORCH_CLIENT_SECRET", ""),
        "orch_scope": os.getenv("ORCH_SCOPE", "OR.Folders OR.Assets OR.Jobs OR.Execution"),
        "custom_nuget_feed": os.getenv("CUSTOM_NUGET_FEED", ""),
        "default_clone_dir": os.getenv("DEFAULT_CLONE_DIR", "C:\\UiPath\\Repos"),
        "default_output_dir": os.getenv("DEFAULT_OUTPUT_DIR", "C:\\UiPath\\Packages"),
    }


def check_credentials(config: dict) -> dict:
    """Check which credentials are configured."""
    return {
        "GitHub Token": bool(config["github_token"]),
        "Orchestrator URL": bool(config["orch_url"]),
        "Orchestrator Tenant": bool(config["orch_tenant"]),
        "Orchestrator Client ID": bool(config["orch_client_id"]),
        "Orchestrator Client Secret": bool(config["orch_client_secret"]),
    }


# =============================================
# ORCHESTRATOR API FUNCTIONS
# =============================================

def get_orchestrator_token(config: dict) -> Optional[str]:
    """Authenticate with Orchestrator and get access token."""
    token_url = f"{config['orch_url']}/identity/connect/token"
    
    payload = {
        "grant_type": "client_credentials",
        "client_id": config["orch_client_id"],
        "client_secret": config["orch_client_secret"],
        "scope": config["orch_scope"],
    }
    
    try:
        response = requests.post(token_url, data=payload, timeout=30)
        response.raise_for_status()
        return response.json().get("access_token")
    except requests.RequestException as e:
        st.error(f"❌ Erro ao autenticar no Orchestrator: {e}")
        return None


def upload_package_to_orchestrator(
    config: dict,
    token: str,
    nupkg_path: str,
    folder_id: Optional[int] = None
) -> Tuple[bool, str]:
    """Upload a .nupkg package to Orchestrator."""
    upload_url = f"{config['orch_url']}/{config['orch_tenant']}/orchestrator_/odata/Processes/UiPath.Server.Configuration.OData.UploadPackage"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "X-UIPATH-TenantName": config["orch_tenant"],
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


def download_package_from_orchestrator(
    config: dict,
    token: str,
    package_id: str,
    version: str,
    output_dir: str
) -> Tuple[bool, str]:
    """Download a package from Orchestrator."""
    download_url = f"{config['orch_url']}/{config['orch_tenant']}/orchestrator_/odata/Processes/UiPath.Server.Configuration.OData.DownloadPackage(key='{package_id}',version='{version}')"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "X-UIPATH-TenantName": config["orch_tenant"],
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


def list_orchestrator_packages(config: dict, token: str) -> List[dict]:
    """List packages from Orchestrator."""
    url = f"{config['orch_url']}/{config['orch_tenant']}/orchestrator_/odata/Processes"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "X-UIPATH-TenantName": config["orch_tenant"],
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json().get("value", [])
    except requests.RequestException as e:
        st.error(f"❌ Erro ao listar pacotes: {e}")
        return []


# =============================================
# GIT OPERATIONS
# =============================================

def clean_temp_files(repo_path: str) -> List[str]:
    """Remove temporary files and directories from repository."""
    patterns_to_remove = [".local", ".screenshots", ".objects", "__pycache__", ".vs"]
    removed = []
    
    for root, dirs, files in os.walk(repo_path, topdown=True):
        for pattern in patterns_to_remove:
            if pattern in dirs:
                dir_path = os.path.join(root, pattern)
                try:
                    shutil.rmtree(dir_path)
                    removed.append(dir_path)
                except Exception as e:
                    st.warning(f"⚠️ Não foi possível remover {dir_path}: {e}")
                dirs.remove(pattern)
    
    return removed


def clone_repository(repo_url: str, target_dir: str, clean_temps: bool = True) -> Tuple[bool, str]:
    """Clone a Git repository."""
    try:
        # Ensure target directory exists
        os.makedirs(target_dir, exist_ok=True)
        
        # Clone the repository
        repo = Repo.clone_from(repo_url, target_dir, progress=None)
        
        message = f"✅ Repositório clonado em: {target_dir}"
        
        # Clean temporary files if requested
        if clean_temps:
            removed = clean_temp_files(target_dir)
            if removed:
                message += f"\n🧹 Removidos {len(removed)} diretórios temporários"
        
        return True, message
    except GitCommandError as e:
        return False, f"❌ Erro Git: {e}"
    except Exception as e:
        return False, f"❌ Erro: {e}"


def sync_fork(repo_path: str, upstream_url: str, branch: str = "main") -> Tuple[bool, str]:
    """Sync a forked repository with upstream."""
    try:
        repo = Repo(repo_path)
        
        # Add or update upstream remote
        if "upstream" not in [r.name for r in repo.remotes]:
            repo.create_remote("upstream", upstream_url)
        else:
            repo.remotes.upstream.set_url(upstream_url)
        
        # Fetch upstream
        repo.remotes.upstream.fetch()
        
        # Reset hard to upstream branch
        repo.git.reset("--hard", f"upstream/{branch}")
        
        # Force push to origin
        repo.remotes.origin.push(force=True)
        
        return True, f"✅ Fork sincronizado com upstream/{branch} e push forçado para origin"
    except GitCommandError as e:
        return False, f"❌ Erro Git: {e}"
    except Exception as e:
        return False, f"❌ Erro: {e}"


# =============================================
# BUILD & PUBLISH FUNCTIONS
# =============================================

def run_uipath_pack(
    project_path: str,
    output_dir: str,
    version: str,
    use_local_cache: bool = True,
    custom_feed_url: Optional[str] = None
) -> Tuple[bool, str, str]:
    """Run UiPath CLI pack command."""
    
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    # Build the command with proper quoting for paths with spaces
    cmd_parts = [
        "uipcli",
        "package", "pack",
        f'"{project_path}"',
        "--output",
        f'"{output_dir}"',
        "--version",
        version,
    ]
    
    # Add custom feed source if provided
    if custom_feed_url and custom_feed_url.strip():
        cmd_parts.extend(["--source", f'"{custom_feed_url.strip()}"'])
    
    cmd = " ".join(cmd_parts)
    
    try:
        # Run the command
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        output = result.stdout + result.stderr
        success = result.returncode == 0
        
        return success, cmd, output
    except subprocess.TimeoutExpired:
        return False, cmd, "❌ Timeout: O comando excedeu o limite de 5 minutos"
    except Exception as e:
        return False, cmd, f"❌ Erro: {e}"


def find_nupkg_files(directory: str) -> List[str]:
    """Find all .nupkg files in a directory."""
    nupkg_files = []
    if os.path.exists(directory):
        for file in os.listdir(directory):
            if file.endswith(".nupkg"):
                nupkg_files.append(os.path.join(directory, file))
    return sorted(nupkg_files, key=os.path.getmtime, reverse=True)


def check_dependency_errors(output: str) -> List[str]:
    """Check for dependency errors in build output."""
    errors = []
    
    patterns = [
        r"Unable to resolve dependency",
        r"Could not find package",
        r"Package '.*' is not found",
        r"Missing dependency",
        r"NU1101",  # NuGet error code for package not found
        r"NU1102",  # NuGet error code for package version not found
    ]
    
    for line in output.split("\n"):
        for pattern in patterns:
            if re.search(pattern, line, re.IGNORECASE):
                errors.append(line.strip())
                break
    
    return errors


# =============================================
# GITHUB FUNCTIONS
# =============================================

def get_github_client(token: str) -> Optional[Github]:
    """Create GitHub client."""
    try:
        return Github(token)
    except Exception as e:
        st.error(f"❌ Erro ao conectar ao GitHub: {e}")
        return None


def get_open_pull_requests(github_client: Github, repo_name: str) -> List[dict]:
    """Get open pull requests for a repository."""
    try:
        repo = github_client.get_repo(repo_name)
        pulls = repo.get_pulls(state="open", sort="created", direction="desc")
        
        pr_list = []
        for pr in pulls:
            pr_list.append({
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
            })
        
        return pr_list
    except GithubException as e:
        st.error(f"❌ Erro ao buscar PRs: {e}")
        return []


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
    custom_feed = st.sidebar.text_input(
        "Custom Feed URL",
        value=config["custom_nuget_feed"],
        help="URL do feed NuGet customizado (Orchestrator ou Artifactory)"
    )
    
    st.sidebar.markdown("---")
    
    # Default directories
    st.sidebar.markdown("### 📁 Diretórios Padrão")
    st.sidebar.text_input("Clone Dir", value=config["default_clone_dir"], disabled=True)
    st.sidebar.text_input("Output Dir", value=config["default_output_dir"], disabled=True)
    
    return custom_feed


# =============================================
# MAIN APPLICATION SECTIONS
# =============================================

def section_git_operations(config: dict):
    """Git Operations section."""
    st.markdown('<p class="section-header">🔄 Git Operations</p>', unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["📥 Clone Repository", "🔃 Sync Fork"])
    
    with tab1:
        st.markdown("#### Clone de Repositório")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            repo_url = st.text_input(
                "URL do Repositório",
                placeholder="https://github.com/org/repo.git",
                key="clone_repo_url"
            )
        
        with col2:
            target_dir = st.text_input(
                "Diretório de Destino",
                value=config["default_clone_dir"],
                key="clone_target_dir"
            )
        
        clean_temps = st.checkbox(
            "🧹 Limpar arquivos temporários após clone (.local, .screenshots)",
            value=True,
            key="clone_clean_temps"
        )
        
        if st.button("📥 Clonar Repositório", type="primary", key="btn_clone"):
            if repo_url and target_dir:
                with st.spinner("Clonando repositório..."):
                    # Extract repo name for folder
                    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
                    full_target = os.path.join(target_dir, repo_name)
                    
                    success, message = clone_repository(repo_url, full_target, clean_temps)
                    
                    if success:
                        st.success(message)
                    else:
                        st.error(message)
            else:
                st.warning("⚠️ Preencha a URL do repositório e o diretório de destino")
    
    with tab2:
        st.markdown("#### Sincronizar Fork com Upstream")
        st.info("ℹ️ Esta operação faz: Fetch Upstream → Reset Hard → Push Force")
        
        col1, col2 = st.columns(2)
        
        with col1:
            fork_path = st.text_input(
                "Caminho do Fork Local",
                placeholder="C:\\UiPath\\Repos\\meu-fork",
                key="sync_fork_path"
            )
            upstream_url = st.text_input(
                "URL do Upstream",
                placeholder="https://github.com/original-org/original-repo.git",
                key="sync_upstream_url"
            )
        
        with col2:
            branch = st.text_input(
                "Branch",
                value="main",
                key="sync_branch"
            )
        
        if st.button("🔃 Sincronizar Fork", type="primary", key="btn_sync"):
            if fork_path and upstream_url:
                with st.spinner("Sincronizando fork..."):
                    success, message = sync_fork(fork_path, upstream_url, branch)
                    
                    if success:
                        st.success(message)
                    else:
                        st.error(message)
            else:
                st.warning("⚠️ Preencha o caminho do fork e a URL do upstream")


def section_pull_requests(config: dict):
    """Pull Request Dashboard section."""
    st.markdown('<p class="section-header">📋 Pull Request Dashboard</p>', unsafe_allow_html=True)
    
    if not config["github_token"]:
        st.warning("⚠️ Configure o GITHUB_TOKEN no arquivo .env para usar esta funcionalidade")
        return
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        repo_name = st.text_input(
            "Repositório (owner/repo)",
            placeholder="uipath/my-automation",
            key="pr_repo_name"
        )
    
    with col2:
        st.write("")
        st.write("")
        refresh = st.button("🔄 Atualizar", key="btn_refresh_prs")
    
    if repo_name and (refresh or "pr_list" not in st.session_state):
        github_client = get_github_client(config["github_token"])
        
        if github_client:
            with st.spinner("Buscando Pull Requests..."):
                prs = get_open_pull_requests(github_client, repo_name)
                st.session_state["pr_list"] = prs
    
    if "pr_list" in st.session_state and st.session_state["pr_list"]:
        prs = st.session_state["pr_list"]
        
        st.markdown(f"**{len(prs)} Pull Request(s) Aberto(s)**")
        
        for pr in prs:
            with st.expander(f"#{pr['number']} - {pr['title']}", expanded=False):
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.markdown(f"**Autor:** {pr['author']}")
                    st.markdown(f"**Branch:** `{pr['head_branch']}` → `{pr['base_branch']}`")
                
                with col2:
                    st.markdown(f"**Criado:** {pr['created_at'].strftime('%d/%m/%Y %H:%M')}")
                    st.markdown(f"**Atualizado:** {pr['updated_at'].strftime('%d/%m/%Y %H:%M')}")
                
                with col3:
                    draft_badge = "🚧 Draft" if pr['draft'] else "✅ Ready"
                    st.markdown(f"**Status:** {draft_badge}")
                    
                    if pr['labels']:
                        labels_str = ", ".join([f"`{l}`" for l in pr['labels']])
                        st.markdown(f"**Labels:** {labels_str}")
                
                st.markdown(f"[🔗 Abrir no GitHub]({pr['url']})")
    
    elif "pr_list" in st.session_state:
        st.info("📭 Nenhum Pull Request aberto encontrado")


def section_build_publish(config: dict, custom_feed: str):
    """Build & Publish section."""
    st.markdown('<p class="section-header">📦 Build & Publish</p>', unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["🔨 Build (Pack)", "🚀 Publish (Upload)"])
    
    with tab1:
        st.markdown("#### Empacotar Projeto UiPath")
        
        col1, col2 = st.columns(2)
        
        with col1:
            project_path = st.text_input(
                "Caminho do project.json",
                placeholder="C:\\UiPath\\MyProject\\project.json",
                key="build_project_path"
            )
            version = st.text_input(
                "Versão",
                value="1.0.0",
                placeholder="1.0.0",
                key="build_version"
            )
        
        with col2:
            output_dir = st.text_input(
                "Diretório de Output",
                value=config["default_output_dir"],
                key="build_output_dir"
            )
            
            use_local_cache = st.checkbox(
                "📂 Usar Dependências Locais (.nuget cache)",
                value=True,
                key="build_use_local_cache"
            )
        
        # Custom Feed URL
        st.markdown("---")
        st.markdown("**🌐 Feed de Dependências Customizado (Opcional)**")
        
        feed_url = st.text_input(
            "Custom Feed URL",
            value=custom_feed,
            placeholder="https://cloud.uipath.com/.../nuget/v3/index.json",
            help="Se informado, será adicionado --source ao comando pack",
            key="build_feed_url"
        )
        
        if feed_url:
            st.info(f"ℹ️ O comando usará: `--source \"{feed_url}\"`")
        
        st.markdown("---")
        
        if st.button("📦 Pack", type="primary", key="btn_pack"):
            if project_path and output_dir and version:
                with st.spinner("Empacotando projeto..."):
                    success, cmd, output = run_uipath_pack(
                        project_path=project_path,
                        output_dir=output_dir,
                        version=version,
                        use_local_cache=use_local_cache,
                        custom_feed_url=feed_url if feed_url else None
                    )
                    
                    # Show command executed
                    st.markdown("**Comando executado:**")
                    st.code(cmd, language="bash")
                    
                    # Show output
                    st.markdown("**Output:**")
                    st.code(output, language="text")
                    
                    # Check for dependency errors
                    dep_errors = check_dependency_errors(output)
                    
                    if dep_errors:
                        st.markdown("""
                        <div class="error-highlight">
                            <h4>⚠️ Erro de Dependência Detectado!</h4>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        st.error("**Dependências não encontradas:**")
                        for error in dep_errors:
                            st.markdown(f"- `{error}`")
                        
                        st.warning("""
                        **💡 Sugestões:**
                        1. Verifique se o pacote está disponível no Feed configurado
                        2. Certifique-se de que a URL do Feed está correta
                        3. Verifique suas credenciais de acesso ao Feed
                        4. Tente limpar o cache NuGet local e rebuild
                        """)
                    
                    elif success:
                        st.success("✅ Pacote criado com sucesso!")
                        
                        # List generated packages
                        packages = find_nupkg_files(output_dir)
                        if packages:
                            st.markdown("**📦 Pacotes gerados:**")
                            for pkg in packages[:5]:  # Show last 5
                                st.markdown(f"- `{os.path.basename(pkg)}`")
                    else:
                        st.error("❌ Falha ao criar pacote. Verifique o output acima.")
            else:
                st.warning("⚠️ Preencha todos os campos obrigatórios")
    
    with tab2:
        st.markdown("#### Upload para Orchestrator")
        
        if not all([config["orch_client_id"], config["orch_client_secret"]]):
            st.warning("⚠️ Configure ORCH_CLIENT_ID e ORCH_CLIENT_SECRET no arquivo .env")
            return
        
        # List available packages
        packages_dir = st.text_input(
            "Diretório dos Pacotes",
            value=config["default_output_dir"],
            key="publish_packages_dir"
        )
        
        if packages_dir and os.path.exists(packages_dir):
            packages = find_nupkg_files(packages_dir)
            
            if packages:
                st.markdown(f"**📦 {len(packages)} pacote(s) encontrado(s):**")
                
                selected_package = st.selectbox(
                    "Selecione o pacote para upload",
                    options=packages,
                    format_func=lambda x: os.path.basename(x),
                    key="publish_selected_package"
                )
                
                folder_id = st.text_input(
                    "Folder ID (opcional)",
                    placeholder="123",
                    help="ID da pasta do Orchestrator (deixe vazio para pasta padrão)",
                    key="publish_folder_id"
                )
                
                if st.button("🚀 Upload para Orchestrator", type="primary", key="btn_upload"):
                    with st.spinner("Autenticando e enviando..."):
                        # Get token
                        token = get_orchestrator_token(config)
                        
                        if token:
                            success, message = upload_package_to_orchestrator(
                                config=config,
                                token=token,
                                nupkg_path=selected_package,
                                folder_id=int(folder_id) if folder_id else None
                            )
                            
                            if success:
                                st.success(message)
                            else:
                                st.error(message)
            else:
                st.info("📭 Nenhum pacote .nupkg encontrado no diretório")
        elif packages_dir:
            st.warning("⚠️ Diretório não encontrado")


def section_tenant_migration(config: dict):
    """Tenant Migration section."""
    st.markdown('<p class="section-header">🔄 Tenant Migration</p>', unsafe_allow_html=True)
    
    if not all([config["orch_client_id"], config["orch_client_secret"]]):
        st.warning("⚠️ Configure as credenciais do Orchestrator no arquivo .env")
        return
    
    st.info("ℹ️ Migre pacotes entre tenants: Download do tenant origem → Upload no tenant destino")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 📥 Tenant Origem")
        
        source_tenant = st.text_input(
            "Nome do Tenant Origem",
            value=config["orch_tenant"],
            key="mig_source_tenant"
        )
        
        package_id = st.text_input(
            "Package ID",
            placeholder="MyAutomation",
            key="mig_package_id"
        )
        
        package_version = st.text_input(
            "Versão",
            placeholder="1.0.0",
            key="mig_package_version"
        )
    
    with col2:
        st.markdown("#### 📤 Tenant Destino")
        
        dest_tenant = st.text_input(
            "Nome do Tenant Destino",
            placeholder="ProductionTenant",
            key="mig_dest_tenant"
        )
        
        dest_folder_id = st.text_input(
            "Folder ID no Destino (opcional)",
            placeholder="456",
            key="mig_dest_folder_id"
        )
    
    st.markdown("---")
    
    # Temporary directory for migration
    temp_dir = st.text_input(
        "Diretório Temporário",
        value=tempfile.gettempdir(),
        key="mig_temp_dir"
    )
    
    if st.button("🔄 Migrar Pacote", type="primary", key="btn_migrate"):
        if all([source_tenant, package_id, package_version, dest_tenant]):
            with st.spinner("Migrando pacote..."):
                # Step 1: Get token for source tenant
                source_config = config.copy()
                source_config["orch_tenant"] = source_tenant
                
                st.markdown("**1️⃣ Autenticando no tenant origem...**")
                source_token = get_orchestrator_token(source_config)
                
                if not source_token:
                    st.error("❌ Falha ao autenticar no tenant origem")
                    return
                
                st.success("✅ Autenticado no tenant origem")
                
                # Step 2: Download package
                st.markdown("**2️⃣ Baixando pacote...**")
                success, result = download_package_from_orchestrator(
                    source_config, source_token, package_id, package_version, temp_dir
                )
                
                if not success:
                    st.error(result)
                    return
                
                downloaded_path = result
                st.success(f"✅ Pacote baixado: {os.path.basename(downloaded_path)}")
                
                # Step 3: Get token for destination tenant
                st.markdown("**3️⃣ Autenticando no tenant destino...**")
                dest_config = config.copy()
                dest_config["orch_tenant"] = dest_tenant
                
                dest_token = get_orchestrator_token(dest_config)
                
                if not dest_token:
                    st.error("❌ Falha ao autenticar no tenant destino")
                    return
                
                st.success("✅ Autenticado no tenant destino")
                
                # Step 4: Upload to destination
                st.markdown("**4️⃣ Enviando pacote para destino...**")
                success, message = upload_package_to_orchestrator(
                    dest_config,
                    dest_token,
                    downloaded_path,
                    int(dest_folder_id) if dest_folder_id else None
                )
                
                if success:
                    st.success(message)
                    st.balloons()
                    
                    # Cleanup
                    try:
                        os.remove(downloaded_path)
                        st.info("🧹 Arquivo temporário removido")
                    except:
                        pass
                else:
                    st.error(message)
        else:
            st.warning("⚠️ Preencha todos os campos obrigatórios")


# =============================================
# MAIN APPLICATION
# =============================================

def main():
    """Main application entry point."""
    # Header
    st.markdown('<p class="main-header">🤖 UiPath Team Coordinator</p>', unsafe_allow_html=True)
    st.markdown("*Painel de Controle para gerenciar repositórios Git, Dependências e Deploy de automações UiPath*")
    st.markdown("---")
    
    # Load configuration
    config = get_env_config()
    
    # Render sidebar and get custom feed URL
    custom_feed = render_sidebar(config)
    
    # Create tabs for main sections
    tabs = st.tabs([
        "🔄 Git Operations",
        "📋 Pull Requests",
        "📦 Build & Publish",
        "🔄 Tenant Migration"
    ])
    
    with tabs[0]:
        section_git_operations(config)
    
    with tabs[1]:
        section_pull_requests(config)
    
    with tabs[2]:
        section_build_publish(config, custom_feed)
    
    with tabs[3]:
        section_tenant_migration(config)
    
    # Footer
    st.markdown("---")
    st.markdown(
        """
        <div style="text-align: center; color: #666; font-size: 0.9rem;">
            <p>UiPath Team Coordinator v1.0.0 | Built with Streamlit 💙</p>
        </div>
        """,
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()
