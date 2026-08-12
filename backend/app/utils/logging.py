"""日志配置"""
import sys
from loguru import logger
from app.config import settings


def setup_logging():
    """统一日志格式"""
    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    )
    # 文件日志
    log_file = settings.storage_root / "logs" / "app.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger.add(
        str(log_file),
        level=settings.log_level,
        rotation="10 MB",
        retention="30 days",
        encoding="utf-8",
    )
    return logger


log = setup_logging()
