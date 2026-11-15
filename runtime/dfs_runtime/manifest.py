"""制品加载：dfs.json + SKILL.md + dfs.local.json，做契约校验与摘要计算。

规范要点：
1. 每个 Skill 文件必须声明来源（source.provenance），来源不可留空；
2. 运行时配置（含模型手动设置）写在 dfs.local.json，不入库；
3. 契约不满足一律 fail closed。
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from .validation import validate_json

LOCAL_OVERRIDE_NAME = "dfs.local.json"


class ContractError(Exception):
    """契约不满足：一律 fail closed，不做降级猜测。"""


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractError(f"文件不存在: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ContractError(f"{path.name} 不是合法 JSON: {exc}") from exc


def load_schema(name: str) -> dict:
    return read_json(Path(__file__).with_name("schemas") / name)


@dataclass(frozen=True)
class SkillFile:
    name: str
    text: str
    digest: str
    origin: str
    provenance: dict


@dataclass
class Capsule:
    root: Path
    data: dict
    skills: list[SkillFile]
    local: dict

    # ---- 基本字段 ----
    @property
    def name(self) -> str:
        return self.data["name"]

    @property
    def title(self) -> str:
        return self.data.get("title") or self.name

    @property
    def version(self) -> str:
        return self.data["version"]

    @property
    def tools(self) -> list[str]:
        return list(self.data.get("tools") or [])

    @property
    def max_steps(self) -> int:
        return int((self.data.get("runtime") or {}).get("max_steps", 12))

    @property
    def timeout_s(self) -> int:
        return int((self.data.get("runtime") or {}).get("timeout_s", 120))

    @property
    def input_schema(self) -> dict:
        return self.data["io"]["input_schema"]

    @property
    def output_schema(self) -> dict:
        return self.data["io"]["output_schema"]

    @property
    def ui(self) -> dict:
        ui = dict(self.data.get("ui") or {"kind": "none"})
        ui.setdefault("kind", "none")
        ui.setdefault("title", self.title)
        ui.setdefault("host", "127.0.0.1")
        ui.setdefault("port", 8787)
        ui.setdefault("width", 760)
        ui.setdefault("height", 620)
        return ui

    @property
    def provenance(self) -> list[dict]:
        return list(self.data["source"].get("provenance") or [])

    @property
    def skill_text(self) -> str:
        parts = []
        for skill in self.skills:
            parts.append(f"<!-- file: {skill.name} | origin: {skill.origin} -->\n{skill.text}")
        return "\n\n".join(parts)

    @property
    def source_digest(self) -> str:
        digest = hashlib.sha256()
        for skill in self.skills:
            digest.update(skill.name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(skill.text.encode("utf-8"))
            digest.update(b"\0")
        return "sha256:" + digest.hexdigest()

    # ---- 模型解析（CLI > 环境变量 > dfs.local.json > dfs.json） ----
    def resolve_model(self, cli_overrides: dict | None = None) -> dict:
        cfg: dict = {"auth": "bearer", **self.data["model"]}
        cfg.update((self.local.get("model") or {}) if self.local else {})

        for key, env_name in (("model", "DFS_MODEL"), ("base_url", "DFS_BASE_URL"), ("auth", "DFS_AUTH")):
            value = os.environ.get(env_name)
            if value:
                cfg[key] = value

        if os.environ.get("DFS_API_KEY"):
            cfg["api_key"] = os.environ["DFS_API_KEY"]
        else:
            env_name = cfg.get("api_key_env") or ""
            if env_name and os.environ.get(env_name):
                cfg["api_key"] = os.environ[env_name]

        if cli_overrides:
            cfg.update({key: value for key, value in cli_overrides.items() if value})

        cfg.setdefault("auth", "bearer")
        cfg.setdefault("temperature", 0.2)
        cfg.setdefault("max_tokens", 1024)
        cfg.setdefault("api_key", "")
        return cfg

    def summary(self) -> dict:
        model = self.resolve_model()
        return {
            "name": self.name,
            "title": self.title,
            "version": self.version,
            "root": str(self.root),
            "skills": [
                {
                    "file": s.name,
                    "digest": s.digest,
                    "origin": s.origin,
                    "upstream_url": s.provenance.get("upstream_url", ""),
                    "license": s.provenance.get("license", ""),
                }
                for s in self.skills
            ],
            "source_digest": self.source_digest,
            "model": {
                "provider": model.get("provider"),
                "model": model.get("model"),
                "base_url": model.get("base_url", ""),
                "auth": model.get("auth"),
                "api_key": _mask(model.get("api_key")),
            },
            "ui": self.ui,
            "max_steps": self.max_steps,
            "tools": self.tools,
            "input_required": self.input_schema.get("required", []),
            "output_required": self.output_schema.get("required", []),
        }


def _mask(api_key: str | None) -> str:
    if not api_key:
        return "(空)"
    if len(api_key) <= 8:
        return "***"
    return f"{api_key[:4]}…{api_key[-4:]}"


def load_local_override(root: Path) -> dict:
    path = root / LOCAL_OVERRIDE_NAME
    if not path.exists():
        return {}
    data = read_json(path)
    if not isinstance(data, dict):
        raise ContractError(f"{LOCAL_OVERRIDE_NAME} 顶层必须是 JSON 对象")
    unknown = [key for key in data if key != "model"]
    if unknown:
        raise ContractError(f"{LOCAL_OVERRIDE_NAME} 含未知字段: {unknown}（只允许 model）")
    if "model" in data and not isinstance(data["model"], dict):
        raise ContractError(f"{LOCAL_OVERRIDE_NAME} 的 model 必须是对象")
    return data


def _check_provenance(data: dict, skills: list[SkillFile]) -> None:
    declared = data["source"]["provenance"]
    files = [item["file"] for item in declared]
    if len(set(files)) != len(files):
        raise ContractError("source.provenance 中存在重复的 file")

    covered = set(files)
    actual = {skill.name for skill in skills}
    missing = sorted(actual - covered)
    if missing:
        raise ContractError(f"以下 Skill 文件未声明来源（source.provenance）: {missing}")
    extra = sorted(covered - actual)
    if extra:
        raise ContractError(f"source.provenance 声明了不存在的 Skill 文件: {extra}")

    for item in declared:
        origin = item["origin"]
        if origin in ("github", "clawhub", "other") and not item.get("upstream_url"):
            raise ContractError(f"来源为 {origin} 的 Skill 必须填写 upstream_url: {item['file']}")
        skill = next(s for s in skills if s.name == item["file"])
        if item.get("digest") and item["digest"] != skill.digest:
            raise ContractError(
                f"{item['file']} 的 provenance.digest 与文件内容不一致（来源被篡改或文件已更新）"
            )


def load_capsule(root: str | Path) -> Capsule:
    root_path = Path(root).expanduser().resolve()
    if not root_path.is_dir():
        raise ContractError(f"制品目录不存在: {root_path}")

    manifest_path = root_path / "dfs.json"
    if not manifest_path.exists():
        raise ContractError(f"缺少 dfs.json: {manifest_path}")

    data = read_json(manifest_path)
    try:
        validate_json(load_schema("manifest.schema.json"), data, "dfs.json")
    except ValueError as exc:
        raise ContractError(f"dfs.json 不符合契约: {exc}") from exc

    skills: list[SkillFile] = []
    provenance_by_file = {item["file"]: item for item in data["source"]["provenance"]}
    for relative in data["source"]["skills"]:
        path = (root_path / relative).resolve()
        if root_path not in path.parents and path != root_path:
            raise ContractError(f"Skill 路径越出制品目录: {relative}")
        if not path.exists():
            raise ContractError(f"Skill 文件不存在: {relative}")
        text = path.read_text(encoding="utf-8")
        item = provenance_by_file.get(relative, {})
        skills.append(
            SkillFile(
                name=relative,
                text=text,
                digest="sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
                origin=str(item.get("origin", "other")),
                provenance=dict(item),
            )
        )

    _check_provenance(data, skills)
    return Capsule(root=root_path, data=data, skills=skills, local=load_local_override(root_path))


def load_plan(path: str | Path) -> dict:
    plan = read_json(Path(path).expanduser().resolve())
    try:
        validate_json(load_schema("plan.schema.json"), plan, "plan.json")
    except ValueError as exc:
        raise ContractError(f"plan.json 不符合契约: {exc}") from exc
    return plan
