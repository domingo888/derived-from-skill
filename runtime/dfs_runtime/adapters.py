"""模型适配器：制品只认「绑定的那个模型」，不做自动降级。

鉴权规范：
- auth=bearer：必须提供 API Key（可用环境变量或 dfs.local.json 手动设置）；
- auth=none：允许空 Key，用于本地无鉴权端点（Ollama / LM Studio / LocalAI 等）。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request


class AdapterError(Exception):
    """模型调用失败。运行时不降级到其他模型，直接中止。"""


class BaseAdapter:
    provider = "base"

    def chat(self, system: str, user: str) -> str:
        raise NotImplementedError

    def describe(self) -> dict:
        return {"provider": self.provider}


class MockAdapter(BaseAdapter):
    """离线回放：只使用计划里记录的 mock_output，不做任何真实推理。"""

    provider = "mock"

    def chat(self, system: str, user: str) -> str:
        raise AdapterError(
            "mock 适配器不支持真实推理：计划中的 llm 步骤需要提供 mock_output，"
            "或改用 provider=openai-compatible 的绑定模型"
        )


class OpenAICompatAdapter(BaseAdapter):
    """OpenAI 兼容的 /chat/completions 端点。"""

    provider = "openai-compatible"

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str = "",
        auth: str = "bearer",
        temperature: float = 0.2,
        max_tokens: int = 1024,
        timeout_s: int = 120,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or ""
        self.auth = auth or "bearer"
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout_s = timeout_s

    def describe(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "auth": self.auth,
        }

    def chat(self, system: str, user: str) -> str:
        if not self.base_url:
            raise AdapterError(
                "缺少 base_url：可用 dfs.json.model.base_url、dfs.local.json（dfs model --base-url）"
                "或环境变量 DFS_BASE_URL 设置"
            )
        if not self.model:
            raise AdapterError("缺少 model：用 dfs model --model 指定绑定的模型名")
        if self.auth == "bearer" and not self.api_key:
            raise AdapterError(
                "鉴权模式为 bearer 但未提供 API Key：设置环境变量 DFS_API_KEY，"
                "或用 dfs model --auth none 连接本地无鉴权端点"
            )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        headers = {"Content-Type": "application/json"}
        if self.auth == "bearer" and self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        request = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise AdapterError(f"模型端点返回 HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise AdapterError(f"无法连接模型端点 {self.base_url}: {exc.reason}") from exc
        except TimeoutError as exc:
            raise AdapterError(f"模型端点超时（{self.timeout_s}s）") from exc

        try:
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AdapterError(f"模型响应结构异常: {str(body)[:200]}") from exc


def build_adapter(model_cfg: dict, timeout_s: int = 120) -> BaseAdapter:
    """model_cfg 必须是已解析完成的配置（见 Capsule.resolve_model）。"""
    provider = str(model_cfg.get("provider") or "").strip().lower()

    if provider == "mock":
        return MockAdapter()
    if provider == "openai-compatible":
        return OpenAICompatAdapter(
            model=str(model_cfg.get("model") or ""),
            base_url=str(model_cfg.get("base_url") or ""),
            api_key=str(model_cfg.get("api_key") or ""),
            auth=str(model_cfg.get("auth") or "bearer"),
            temperature=float(model_cfg.get("temperature", 0.2)),
            max_tokens=int(model_cfg.get("max_tokens", 1024)),
            timeout_s=timeout_s,
        )
    raise AdapterError(f"未知 model.provider: {provider!r}（支持 openai-compatible / mock）")
