# 🤖 UiPath Team Coordinator

Painel de Controle para gerenciar repositórios Git, Dependências e Deploy de automações UiPath.

![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=Streamlit&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![UiPath](https://img.shields.io/badge/UiPath-FA4616?style=for-the-badge&logo=uipath&logoColor=white)

---

## 📋 Funcionalidades

- **Git Operations**: Clone de repositórios e sincronização de forks
- **Pull Request Dashboard**: Visualização de PRs abertos via GitHub API
- **Build & Publish**: Empacotamento de projetos UiPath com suporte a feeds NuGet customizados
- **Tenant Migration**: Migração de pacotes entre tenants do Orchestrator

---

## 🔧 Pré-requisitos

### 1. Python 3.8+

Certifique-se de ter o Python instalado:

```bash
python --version
```

Se não tiver, baixe em: https://www.python.org/downloads/

> ⚠️ **Importante**: Durante a instalação do Python, marque a opção **"Add Python to PATH"**

### 2. UiPath CLI (Opcional - para Build/Publish)

Para usar as funcionalidades de Build, você precisa do UiPath CLI instalado.

#### Instalação via dotnet (Recomendado)

```bash
# Requer .NET 8 SDK instalado
# https://dotnet.microsoft.com/download

# Instalar UiPath CLI para Windows (usa o feed oficial da UiPath)
dotnet tool install -g UiPath.CLI.Windows --add-source "https://pkgs.dev.azure.com/uipath/Public.Feeds/_packaging/UiPath-Official/nuget/v3/index.json"
```

> ⚠️ **Importante**: Após a instalação, **feche e reabra o terminal** para o comando ficar disponível.

#### Verificar instalação

```bash
uipcli --version
```

> 📝 **Nota**: O comando é `uipcli`, não `uipath`.

#### Atualizar para nova versão

```bash
dotnet tool update -g UiPath.CLI.Windows --add-source "https://pkgs.dev.azure.com/uipath/Public.Feeds/_packaging/UiPath-Official/nuget/v3/index.json"
```

### 3. Git (Opcional - para Git Operations)

Para usar as funcionalidades de Git:

```bash
git --version
```

Se não estiver instalado, baixe em: https://git-scm.com/downloads

---

## 🚀 Instalação

### Passo 1: Clonar/Baixar o Projeto

```bash
# Se você tem git instalado:
git clone <URL_DO_REPOSITORIO>
cd CoordenacaoTech

# Ou simplesmente navegue até a pasta do projeto:
cd c:\Users\User\.gemini\antigravity\scratch\CoordenacaoTech
```

### Passo 2: Criar Ambiente Virtual (Recomendado)

```bash
# Criar ambiente virtual
python -m venv venv

# Ativar ambiente virtual (Windows)
venv\Scripts\activate

# Ativar ambiente virtual (Linux/Mac)
source venv/bin/activate
```

### Passo 3: Instalar Dependências

```bash
pip install -r requirements.txt
```

Isso instalará:
- `streamlit` - Interface web
- `python-dotenv` - Carregamento de variáveis de ambiente
- `GitPython` - Operações Git
- `PyGithub` - API do GitHub
- `requests` - Requisições HTTP

### Passo 4: Configurar Variáveis de Ambiente

```bash
# Copiar o template
copy .env.example .env

# No Linux/Mac:
cp .env.example .env
```

Edite o arquivo `.env` com suas credenciais:

```env
# GitHub (para PR Dashboard)
GITHUB_TOKEN=ghp_seuTokenAqui

# Orchestrator (para Build/Publish e Migration)
ORCH_URL=https://cloud.uipath.com
ORCH_TENANT_NAME=SeuTenant
ORCH_CLIENT_ID=seu_client_id
ORCH_CLIENT_SECRET=seu_client_secret

# Feed NuGet customizado (opcional)
CUSTOM_NUGET_FEED=https://seu.feed.url/nuget
```

---

## ▶️ Executando a Aplicação

```bash
# Certifique-se que o ambiente virtual está ativado
venv\Scripts\activate

# Execute o Streamlit
streamlit run app.py
```

A aplicação abrirá automaticamente no navegador em: **http://localhost:8501**

---

## 🔑 Obtendo Credenciais

### GitHub Token

1. Acesse: https://github.com/settings/tokens
2. Clique em **"Generate new token (classic)"**
3. Selecione os scopes: `repo`, `read:org`
4. Copie o token gerado

### Orchestrator Client ID/Secret

1. Acesse o Automation Cloud: https://cloud.uipath.com
2. Vá em **Admin → External Applications**
3. Clique em **"Add Application"**
4. Selecione **"Confidential Application"**
5. Adicione os scopes necessários:
   - `OR.Folders`
   - `OR.Assets`
   - `OR.Jobs`
   - `OR.Execution`
6. Copie o Client ID e Client Secret

---

## 📁 Estrutura do Projeto

```
CoordenacaoTech/
├── app.py              # Aplicação principal Streamlit
├── requirements.txt    # Dependências Python
├── .env.example        # Template de configuração
├── .env               # Suas credenciais (não versionar!)
└── README.md          # Este arquivo
```

---

## 🛠️ Troubleshooting

### Erro: "streamlit não é reconhecido como comando"

Certifique-se de que o ambiente virtual está ativado:
```bash
venv\Scripts\activate
```

### Erro: "uipath não é reconhecido como comando"

O UiPath CLI não está instalado ou não está no PATH. Veja a seção de pré-requisitos.

### Erro de dependência no Build

Se aparecer "Unable to resolve dependency":
1. Verifique se a URL do Feed está correta
2. Confirme que você tem acesso ao feed
3. Tente limpar o cache NuGet: `dotnet nuget locals all --clear`

### Erro de autenticação no Orchestrator

1. Verifique se as credenciais no `.env` estão corretas
2. Confirme que a External Application tem os scopes necessários
3. Verifique se o tenant name está correto

---

## 📝 Licença

Este projeto é para uso interno da equipe de RPA.

---

## 👥 Contato

Em caso de dúvidas, entre em contato com a equipe de DevOps.
