"""Obsidian vault 监听器"""
import asyncio
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

from app.config import settings
from app.models import SourceType
from app.services.ingestion import ingestion_service
from app.parsers.md_parser import MDParser
from app.utils.logging import log


class ObsidianEventHandler(FileSystemEventHandler):
    """Obsidian 变更事件处理"""

    def __init__(self, vault_path: Path, loop: asyncio.AbstractEventLoop):
        self.vault_path = vault_path
        self.loop = loop
        self.md_parser = MDParser()
        # 防抖：记录最近处理过的文件
        self._recent: Dict[str, float] = {}
        self._lock = threading.Lock()

    def _should_process(self, file_path: Path) -> bool:
        """是否应该处理（过滤隐藏文件、目录）"""
        if file_path.is_dir():
            return False
        if file_path.suffix.lower() not in (".md", ".markdown"):
            return False
        # 跳过 Obsidian 配置目录
        if ".obsidian" in file_path.parts:
            return False
        # 防抖：1 秒内同文件不重复处理
        import time
        now = time.time()
        with self._lock:
            last = self._recent.get(str(file_path), 0)
            if now - last < 1.0:
                return False
            self._recent[str(file_path)] = now
        return True

    def _schedule(self, file_path: Path, action: str):
        """调度异步任务"""
        log.info(f"[Obsidian] {action}: {file_path.name}")
        try:
            future = asyncio.run_coroutine_threadsafe(
                self._process_file(file_path, action),
                self.loop,
            )
            future.result(timeout=30)
        except Exception as e:
            log.error(f"[Obsidian 处理失败] {file_path.name}: {e}")

    async def _process_file(self, file_path: Path, action: str):
        """处理文件变更"""
        if action == "delete":
            # 删除：先找 doc_id（用文件路径 hash）
            doc_id = self._doc_id_for_path(file_path)
            if doc_id:
                ingestion_service.delete_document(doc_id)
            return

        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            log.error(f"读取 Obsidian 文件失败: {e}")
            return

        # 解析 frontmatter
        try:
            frontmatter, _ = self._parse_frontmatter(content)
        except Exception:
            frontmatter = {}

        # 元数据
        rel_path = file_path.relative_to(self.vault_path)
        metadata = {
            "obsidian_path": str(rel_path),
            "obsidian_vault": str(self.vault_path),
            "frontmatter": frontmatter,
        }

        # 用文件路径生成稳定 doc_id
        doc_id = self._doc_id_for_path(file_path)

        try:
            await ingestion_service.ingest_text(
                text=content,
                name=file_path.name,
                source=SourceType.OBSIDIAN,
                metadata=metadata,
            )
        except Exception as e:
            log.error(f"Obsidian 入库失败: {file_path}: {e}")

    def _doc_id_for_path(self, file_path: Path) -> str:
        """从文件路径生成稳定 doc_id"""
        from app.utils.text import content_hash
        try:
            rel_path = file_path.relative_to(self.vault_path)
            return f"obs-{content_hash(str(rel_path))}"
        except ValueError:
            return f"obs-{content_hash(str(file_path))}"

    def _parse_frontmatter(self, content: str) -> tuple[dict, str]:
        if not content.startswith("---"):
            return {}, content
        try:
            end = content.index("---", 3)
            yaml_text = content[3:end].strip()
            body = content[end+3:].lstrip("\n")
            import yaml
            return yaml.safe_load(yaml_text) or {}, body
        except Exception:
            return {}, content

    def on_created(self, event: FileSystemEvent):
        if not event.is_directory and self._should_process(Path(event.src_path)):
            self._schedule(Path(event.src_path), "create")

    def on_modified(self, event: FileSystemEvent):
        if not event.is_directory and self._should_process(Path(event.src_path)):
            self._schedule(Path(event.src_path), "modify")

    def on_deleted(self, event: FileSystemEvent):
        if not event.is_directory:
            path = Path(event.src_path)
            if path.suffix.lower() in (".md", ".markdown") and ".obsidian" not in path.parts:
                self._schedule(path, "delete")

    def on_moved(self, event):
        if not event.is_directory:
            src = Path(event.src_path)
            dest = Path(event.dest_path)
            if self._should_process(src):
                self._schedule(src, "delete")
            if self._should_process(dest):
                self._schedule(dest, "create")


class ObsidianWatcher:
    """Obsidian vault 监听器 - 单例"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance.observer = None
                    cls._instance.vault_path = None
                    cls._instance.loop = None
                    cls._instance.status = "stopped"
                    cls._instance.last_sync = None
                    cls._instance.files_count = 0
        return cls._instance

    async def start(self, vault_path: str | Path, loop: asyncio.AbstractEventLoop):
        """启动监听"""
        vault_path = Path(vault_path).absolute()
        if not vault_path.exists():
            raise ValueError(f"Obsidian vault 路径不存在: {vault_path}")
        if not vault_path.is_dir():
            raise ValueError(f"不是目录: {vault_path}")

        # 如果已经在监听别的路径，先停
        if self.observer and self.vault_path and self.vault_path != vault_path:
            self.stop()

        if self.observer and self.vault_path == vault_path:
            log.info(f"Obsidian 监听器已在运行: {vault_path}")
            return

        self.vault_path = vault_path
        self.loop = loop
        self.observer = Observer()
        handler = ObsidianEventHandler(vault_path, loop)
        self.observer.schedule(handler, str(vault_path), recursive=True)
        self.observer.start()
        self.status = "watching"

        # 初始全量入库
        await self._initial_sync()

        log.info(f"[Obsidian 监听已启动] {vault_path}")

    async def _initial_sync(self):
        """初始全量同步"""
        log.info(f"[Obsidian 初始同步] {self.vault_path}")
        count = 0
        for md_file in self.vault_path.rglob("*.md"):
            if ".obsidian" in md_file.parts:
                continue
            try:
                content = md_file.read_text(encoding="utf-8")
                from app.parsers.md_parser import MDParser
                frontmatter, _ = self._extract_frontmatter(content)
                rel_path = md_file.relative_to(self.vault_path)
                metadata = {
                    "obsidian_path": str(rel_path),
                    "obsidian_vault": str(self.vault_path),
                    "frontmatter": frontmatter or {},
                }
                from app.utils.text import content_hash
                doc_id = f"obs-{content_hash(str(rel_path))}"
                await ingestion_service.ingest_text(
                    text=content,
                    name=md_file.name,
                    source=SourceType.OBSIDIAN,
                    metadata=metadata,
                )
                count += 1
            except Exception as e:
                log.error(f"初始同步失败 {md_file}: {e}")
        self.files_count = count
        from datetime import datetime
        self.last_sync = datetime.now().isoformat()
        log.info(f"[Obsidian 初始同步完成] {count} 个文件")

    def _extract_frontmatter(self, content: str) -> tuple[dict, str]:
        if not content.startswith("---"):
            return {}, content
        try:
            end = content.index("---", 3)
            import yaml
            return yaml.safe_load(content[3:end].strip()) or {}, content[end+3:].lstrip("\n")
        except Exception:
            return {}, content

    def stop(self):
        """停止监听"""
        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=5)
            self.observer = None
        self.status = "stopped"
        log.info("[Obsidian 监听已停止]")

    def get_status(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "vault_path": str(self.vault_path) if self.vault_path else None,
            "files_count": self.files_count,
            "last_sync": self.last_sync,
        }


# 全局实例
obsidian_watcher = ObsidianWatcher()
