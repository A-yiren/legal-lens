"""LLM 服务 - 接入 MiniMax / OpenAI / 智谱 GLM"""
import json
import re
from typing import List, Dict, Any, Optional, AsyncIterator
from openai import AsyncOpenAI
from app.config import settings
from app.utils.logging import log


def _extract_json(text: str) -> Dict[str, Any]:
    """从 LLM 输出中尽量抽 JSON 对象。
    兼容纯 JSON / ```json 代码块 / 文本中夹杂 JSON 等情况。
    返回 dict；失败返回空 dict。
    """
    if not text:
        return {}
    # 1. 尝试直接 parse
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    # 2. 抽 ```json ... ``` 或 ``` ... ``` 代码块
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    # 3. 找第一个 { 到最后一个 } 之间的内容
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        snippet = text[start:end + 1]
        try:
            return json.loads(snippet)
        except Exception:
            pass
    return {}


class LLMService:
    """LLM 服务 - 通过 OpenAI 兼容协议接入"""

    def __init__(self):
        self._client = None

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            if not settings.llm_api_key:
                log.warning("LLM API key 未配置，LLM 调用将失败")
            self._client = AsyncOpenAI(
                api_key=settings.llm_api_key or "EMPTY",
                base_url=settings.llm_base_url,
                timeout=settings.llm_timeout,
            )
            log.info(f"LLM 客户端已初始化: provider={settings.llm_provider}, model={settings.llm_model}")
        return self._client

    async def chat(
        self,
        system: str,
        user: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, str]] = None,
    ) -> str:
        """非流式对话"""
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        kwargs = {
            "model": settings.llm_model,
            "messages": messages,
            "temperature": temperature if temperature is not None else settings.llm_temperature,
            "max_tokens": max_tokens or settings.llm_max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format

        try:
            response = await self.client.chat.completions.create(**kwargs)
            return response.choices[0].message.content or ""
        except Exception as e:
            log.exception(f"LLM 调用失败: {e}")
            raise

    async def chat_stream(
        self,
        system: str,
        user: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """流式对话"""
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        kwargs = {
            "model": settings.llm_model,
            "messages": messages,
            "temperature": temperature if temperature is not None else settings.llm_temperature,
            "max_tokens": max_tokens or settings.llm_max_tokens,
            "stream": True,
        }
        try:
            stream = await self.client.chat.completions.create(**kwargs)
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            log.exception(f"LLM 流式调用失败: {e}")
            yield f"\n[错误] LLM 调用失败: {e}"

    async def chat_json(
        self,
        system: str,
        user: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """JSON 格式输出（兼容 MiniMax 等不支持 response_format 的服务）"""
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        try:
            # 关键：MiniMax 不支持 response_format=json_object，靠 prompt 强约束 + 后处理提取
            response = await self.client.chat.completions.create(
                model=settings.llm_model,
                messages=messages,
                temperature=temperature if temperature is not None else 0.2,
                max_tokens=max_tokens or settings.llm_max_tokens,
            )
            text = response.choices[0].message.content or ""
            return _extract_json(text)
        except Exception as e:
            log.exception(f"LLM JSON 调用失败: {e}")
            return {}


# 全局实例
llm_service = LLMService()
