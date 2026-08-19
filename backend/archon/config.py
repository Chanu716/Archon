from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from pathlib import Path

class Settings(BaseSettings):
    ARCHON_VERSION: str = "0.1.0"
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://archon:archon_secret@localhost:5432/archon"
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "neo4j_secret"
    NEO4J_DATABASE: str = "neo4j"  # AuraDB uses 'neo4j' as default; set to instance name if needed
    
    # LLM
    LLM_PROVIDER: str = "ollama"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OPENROUTER_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    LLM_MODEL: str = "llama3"
    LLM_TEMPERATURE: float = 0.1

    # GitHub OAuth
    GITHUB_CLIENT_ID: Optional[str] = None
    GITHUB_CLIENT_SECRET: Optional[str] = None
    FRONTEND_URL: str = "https://nohcra.netlify.app"
    
    # Embeddings
    EMBEDDING_PROVIDER: str = "ollama"
    EMBEDDING_MODEL: str = "nomic-embed-text"
    EMBEDDING_DIMENSIONS: int = 768
    
    # Storage
    REPOS_BASE_PATH: str = "/repos"
    
    # Git
    GIT_MAX_COMMITS: int = 1000
    GIT_SINCE_DAYS: int = 365
    
    # Risk Heuristic
    RISK_WEIGHT_COMPLEXITY: float = 0.40
    RISK_WEIGHT_COUPLING: float = 0.30
    RISK_WEIGHT_CHURN: float = 0.30
    RISK_THRESHOLD_LOW: float = 0.30
    RISK_THRESHOLD_MODERATE: float = 0.60
    RISK_THRESHOLD_HIGH: float = 0.80
    
    # App
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = False
    # Comma-separated list of allowed CORS origins (e.g. https://nohcra.netlify.app)
    ALLOWED_ORIGINS: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()

# Ensure repos base path exists locally if running outside docker
if settings.REPOS_BASE_PATH == "/repos" and not Path("/repos").exists():
    # fallback for local development without docker
    local_repos = Path(__file__).parent.parent.parent / "repos"
    local_repos.mkdir(exist_ok=True)
    settings.REPOS_BASE_PATH = str(local_repos.absolute())
