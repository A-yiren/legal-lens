"""Obsidian 集成 API"""
import asyncio
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Body

from app.watchers.obsidian_watcher import obsidian_watcher
from app.utils.logging import log


router = APIRouter(prefix="/api/obsidian", tags=["obsidian"])


@router.post("/configure")
async def configure(vault_path: str = Body(..., embed=True)):
    """配置 Obsidian vault 路径并启动监听"""
    try:
        loop = asyncio.get_event_loop()
        await obsidian_watcher.start(vault_path, loop)
        status = obsidian_watcher.get_status()
        return {
            "status": "configured",
            **status,
        }
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        log.exception(f"配置 Obsidian 失败: {e}")
        raise HTTPException(500, f"配置失败: {e}")


@router.post("/stop")
async def stop():
    """停止 Obsidian 监听"""
    obsidian_watcher.stop()
    return {"status": "stopped"}


@router.get("/status")
async def status():
    """获取 Obsidian 监听状态"""
    return obsidian_watcher.get_status()


@router.post("/sync")
async def manual_sync():
    """手动触发全量同步"""
    if obsidian_watcher.status != "watching":
        raise HTTPException(400, "Obsidian 未配置或未启动")
    try:
        await obsidian_watcher._initial_sync()
        return {"status": "synced", **obsidian_watcher.get_status()}
    except Exception as e:
        log.exception(f"手动同步失败: {e}")
        raise HTTPException(500, f"同步失败: {e}")
