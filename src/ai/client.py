"""OpenAI 兼容 chat 客户端。

只依赖 requests，不引入 SDK：既能连本地代理（如 magpie），也能连 DeepSeek /
通义 / OpenAI 官方。配置来自 config.yaml 的 ai 段（见 src.config.load_ai_config）。
"""
import json
import threading
import time

import requests


_SEM: threading.BoundedSemaphore | None = None
_SEM_LOCK = threading.Lock()


def _llm_semaphore() -> threading.BoundedSemaphore:
    """模块级全局限流。

    容量取 ``ai.concurrency``。LLMClient.from_config() 有多个调用点，
    如果按实例限流会得到多个独立上限，所以这里只允许一个信号量。
    """
    global _SEM
    if _SEM is None:
        with _SEM_LOCK:
            if _SEM is None:
                from src.config import load_ai_config
                try:
                    capacity = int(load_ai_config().get("concurrency", 4))
                except Exception:
                    capacity = 4
                _SEM = threading.BoundedSemaphore(max(1, capacity))
    return _SEM


class LLMError(Exception):
    """模型调用失败（网络、鉴权、返回格式）。"""


def extract_json(text: str) -> dict:
    """从模型输出里抠出第一个完整 JSON 对象。

    模型偶尔会在 JSON 前后加解释或 ```json 围栏，这里不做正则替换，
    只按括号配对找最外层对象，失败抛 LLMError。
    """
    if not text:
        raise LLMError("模型返回为空")
    start = text.find("{")
    if start < 0:
        raise LLMError(f"返回里没有 JSON: {text[:120]}")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError as exc:
                    raise LLMError(f"JSON 解析失败: {exc}") from exc
    raise LLMError("JSON 不完整（括号未闭合）")


class LLMClient:
    def __init__(self, base_url: str, api_key: str = "", model: str = "",
                 timeout: float = 90.0, temperature: float = 0.3, max_retries: int = 2):
        if not base_url:
            raise LLMError("未配置 ai.base_url，请先在 config.yaml 里填写")
        if not model:
            raise LLMError("未配置 ai.model")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or ""
        self.model = model
        self.timeout = timeout
        self.temperature = temperature
        self.max_retries = max_retries

    @classmethod
    def from_config(cls) -> "LLMClient":
        from src.config import load_ai_config
        cfg = load_ai_config()
        return cls(base_url=cfg["base_url"], api_key=cfg["api_key"], model=cfg["model"],
                   timeout=cfg["timeout"], temperature=cfg["temperature"])

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _post(self, payload: dict) -> str:
        last = None
        for attempt in range(self.max_retries + 1):
            try:
                with _llm_semaphore():
                    resp = requests.post(self.base_url + "/chat/completions",
                                         headers=self._headers(), json=payload,
                                         timeout=self.timeout)
                if resp.status_code >= 400:
                    raise LLMError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                data = resp.json()
                return ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            except requests.RequestException as exc:
                last = exc
                if attempt < self.max_retries:
                    time.sleep(1.5 * (attempt + 1))
        raise LLMError(f"请求失败: {last}")

    def chat(self, messages: list, max_tokens: int = 1200,
             temperature: float | None = None, json_mode: bool = False) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": self.temperature if temperature is None else temperature,
        }
        if json_mode:
            try:
                return self._post({**payload, "response_format": {"type": "json_object"}})
            except LLMError as exc:
                # 部分代理不支持 response_format，退回纯提示词约束
                if "HTTP 4" not in str(exc):
                    raise
        return self._post(payload)

    def chat_json(self, messages: list, max_tokens: int = 1200) -> dict:
        return extract_json(self.chat(messages, max_tokens=max_tokens, json_mode=True))
