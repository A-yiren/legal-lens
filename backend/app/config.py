"""应用配置 - 从 .env 读取"""
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent
BACKEND_ROOT = Path(__file__).parent.parent
STORAGE_ROOT = PROJECT_ROOT / "storage"


class Settings(BaseSettings):
    """全局配置"""
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 基础
    app_name: str = "律瞳 LegalLens"
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"

    # 服务
    host: str = "0.0.0.0"
    port: int = 8765

    # 存储路径
    storage_root: Path = STORAGE_ROOT
    upload_dir: Path = STORAGE_ROOT / "uploads"
    sqlite_path: Path = STORAGE_ROOT / "sqlite" / "legal_lens.db"
    qdrant_path: Path = STORAGE_ROOT / "qdrant"

    # 文档解析
    max_file_size_mb: int = 100
    chunk_size: int = 512  # 字符
    chunk_overlap: int = 64

    # Embedding - bge-small-zh 体积小、CPU 快，中文效果好
    # 生产环境可换 BAAI/bge-m3（效果更好但 2.3GB）
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_device: str = "cpu"  # cpu / cuda
    embedding_use_fp16: bool = False  # CPU 模式关 FP16
    embedding_dim: int = 512  # bge-small-zh-v1.5 = 512
    embedding_batch_size: int = 8

    # Rerank - MVP 暂未启用（bge-reranker-v2-m3 模型 2.3GB 较重）
    rerank_model: str = "BAAI/bge-reranker-base"  # 280MB
    use_rerank: bool = False  # 默认关闭，需要时可开启
    rerank_top_k: int = 20  # 召回数量
    rerank_final_k: int = 5  # 最终送入 LLM 的数量

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "legal_knowledge"

    # LLM - MiniMax
    llm_provider: str = "MiniMax"  # MiniMax / openai / zhipu
    llm_api_key: str = ""
    llm_base_url: str = "https://api.minimaxi.com/v1"
    llm_model: str = "abab6.5s-chat"
    llm_temperature: float = 0.3
    llm_max_tokens: int = 4000
    llm_timeout: int = 60

    # Obsidian
    obsidian_vault_path: Optional[Path] = None
    obsidian_watch_enabled: bool = True
    obsidian_sync_interval: int = 60  # 秒

    # CORS
    cors_origins: list[str] = ["*"]

    def setup_dirs(self):
        """创建必要的目录"""
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.qdrant_path.mkdir(parents=True, exist_ok=True)
        return self


settings = Settings().setup_dirs()
