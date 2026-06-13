# -*- coding: utf-8 -*-
"""
SQLite-backed LLM provider and role configuration.

This keeps model API keys on the server while the public UI only selects a role.
"""

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from urllib.parse import urlsplit, urlunsplit


BASE_DIR = Path(__file__).parent
DB_PATH = Path(os.getenv("SINOMETA_DB_PATH", BASE_DIR / "data" / "sinometa.db"))


DEFAULT_PROVIDERS = [
    {
        "name": "DeepSeek",
        "provider_type": "openai_compatible",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "api_key_required": 1,
        "is_active": 1,
        "is_default": 1,
    },
    {
        "name": "OpenAI",
        "provider_type": "openai_compatible",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o",
        "api_key_required": 1,
        "is_active": 1,
        "is_default": 0,
    },
    {
        "name": "智谱 GLM",
        "provider_type": "openai_compatible",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4",
        "api_key_required": 1,
        "is_active": 1,
        "is_default": 0,
    },
    {
        "name": "Ollama 本地",
        "provider_type": "ollama_native",
        "base_url": "http://127.0.0.1:11434",
        "model": "qwen2.5:7b",
        "api_key_required": 0,
        "is_active": 1,
        "is_default": 0,
    },
    {
        "name": "vLLM 本地",
        "provider_type": "openai_compatible",
        "base_url": "http://127.0.0.1:8001/v1",
        "model": "Qwen/Qwen2.5-7B-Instruct",
        "api_key_required": 0,
        "is_active": 1,
        "is_default": 0,
    },
    {
        "name": "LM Studio 本地",
        "provider_type": "openai_compatible",
        "base_url": "http://127.0.0.1:1234/v1",
        "model": "local-model",
        "api_key_required": 0,
        "is_active": 1,
        "is_default": 0,
    },
]


DEFAULT_ROLES = [
    {
        "name": "玄机真人",
        "avatar_style": "仙风道骨老者",
        "provider_name": "DeepSeek",
        "specialty": "八字、奇门，事业决策",
        "system_prompt": "你是玄机真人，精通八字与奇门遁甲。你的风格严谨、古雅、引经据典，但必须给出现代人能执行的判断和建议。",
        "is_default": 1,
    },
    {
        "name": "梅花居士",
        "avatar_style": "优雅女士",
        "provider_name": "OpenAI",
        "specialty": "梅花易数，感情婚姻",
        "system_prompt": "你是梅花居士，擅长梅花易数与情感关系分析。你的风格温润细腻，重视当事人的感受，同时保持判断清晰。",
        "is_default": 0,
    },
    {
        "name": "六爻先生",
        "avatar_style": "书生形象",
        "provider_name": "智谱 GLM",
        "specialty": "六爻，具体事件预测",
        "system_prompt": "你是六爻先生，擅长用六爻推演具体事件。你的风格条理清晰、重证据、重逻辑，结论要分层给出。",
        "is_default": 0,
    },
    {
        "name": "逍遥散人",
        "avatar_style": "随性道士",
        "provider_name": "DeepSeek",
        "specialty": "综合解卦，日常小事",
        "system_prompt": "你是逍遥散人，擅长综合多种术数判断日常问题。你的风格风趣、接地气，但不能戏谑重大问题。",
        "is_default": 0,
    },
]


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_dict(row: sqlite3.Row) -> Dict:
    return {key: row[key] for key in row.keys()}


def _mask_key(api_key: str) -> str:
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return f"{api_key[:4]}...{api_key[-4:]}"


def _normalize_openai_base_url(base_url: str) -> str:
    url = str(base_url or "").strip().rstrip("/")
    if not url:
        return url

    parsed = urlsplit(url)
    path = parsed.path.rstrip("/")
    suffix = "/chat/completions"
    if path.lower().endswith(suffix):
        path = path[: -len(suffix)] or ""

    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _looks_local_base_url(base_url: str) -> bool:
    host = urlsplit(str(base_url or "")).hostname or ""
    return host in {"127.0.0.1", "localhost", "::1"} or host.startswith(("192.168.", "10.", "172.16.", "172.17.", "172.18.", "172.19.", "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.", "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31."))


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    if not _has_column(conn, table, column):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_providers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                provider_type TEXT NOT NULL DEFAULT 'openai_compatible',
                base_url TEXT NOT NULL,
                model TEXT NOT NULL,
                api_key TEXT NOT NULL DEFAULT '',
                api_key_required INTEGER NOT NULL DEFAULT 1,
                is_active INTEGER NOT NULL DEFAULT 1,
                is_default INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        _add_column_if_missing(
            conn,
            "llm_providers",
            "provider_type",
            "provider_type TEXT NOT NULL DEFAULT 'openai_compatible'",
        )
        _add_column_if_missing(
            conn,
            "llm_providers",
            "api_key_required",
            "api_key_required INTEGER NOT NULL DEFAULT 1",
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                avatar_style TEXT NOT NULL DEFAULT '',
                llm_provider_id INTEGER NOT NULL,
                system_prompt TEXT NOT NULL,
                specialty TEXT NOT NULL DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1,
                is_default INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (llm_provider_id) REFERENCES llm_providers(id)
            )
            """
        )
        now = _now()
        for provider in DEFAULT_PROVIDERS:
            existing = conn.execute(
                "SELECT id FROM llm_providers WHERE name = ?", (provider["name"],)
            ).fetchone()
            if not existing:
                conn.execute(
                    """
                    INSERT INTO llm_providers
                    (name, provider_type, base_url, model, api_key, api_key_required,
                     is_active, is_default, created_at, updated_at)
                    VALUES (?, ?, ?, ?, '', ?, ?, ?, ?, ?)
                    """,
                    (
                        provider["name"],
                        provider["provider_type"],
                        provider["base_url"],
                        provider["model"],
                        provider["api_key_required"],
                        provider["is_active"],
                        provider["is_default"],
                        now,
                        now,
                    ),
                )

        role_count = conn.execute("SELECT COUNT(*) FROM llm_roles").fetchone()[0]
        if role_count == 0:
            now = _now()
            providers = {
                row["name"]: row["id"]
                for row in conn.execute("SELECT id, name FROM llm_providers").fetchall()
            }
            for role in DEFAULT_ROLES:
                provider_id = providers.get(role["provider_name"], 1)
                conn.execute(
                    """
                    INSERT INTO llm_roles
                    (name, avatar_style, llm_provider_id, system_prompt, specialty,
                     is_active, is_default, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)
                    """,
                    (
                        role["name"],
                        role["avatar_style"],
                        provider_id,
                        role["system_prompt"],
                        role["specialty"],
                        role["is_default"],
                        now,
                        now,
                    ),
                )


def list_public_roles() -> List[Dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT r.id, r.name, r.avatar_style, r.specialty, r.is_default,
                   p.name AS provider_name, p.provider_type, p.model AS model,
                   CASE
                     WHEN p.is_active = 1 AND (p.api_key_required = 0 OR p.api_key <> '') THEN 1
                     ELSE 0
                   END AS is_configured
            FROM llm_roles r
            JOIN llm_providers p ON p.id = r.llm_provider_id
            WHERE r.is_active = 1
            ORDER BY r.is_default DESC, r.id ASC
            """
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def list_admin_config() -> Dict[str, List[Dict]]:
    with _connect() as conn:
        provider_rows = conn.execute(
            """
            SELECT id, name, provider_type, base_url, model, api_key, api_key_required,
                   is_active, is_default, created_at, updated_at
            FROM llm_providers
            ORDER BY is_default DESC, id ASC
            """
        ).fetchall()
        role_rows = conn.execute(
            """
            SELECT r.id, r.name, r.avatar_style, r.llm_provider_id, r.system_prompt,
                   r.specialty, r.is_active, r.is_default, r.created_at, r.updated_at,
                   p.name AS provider_name, p.model AS provider_model,
                   p.is_active AS provider_active, p.api_key_required,
                   CASE
                     WHEN p.is_active = 1 AND (p.api_key_required = 0 OR p.api_key <> '') THEN 1
                     ELSE 0
                   END AS provider_configured
            FROM llm_roles r
            LEFT JOIN llm_providers p ON p.id = r.llm_provider_id
            ORDER BY r.is_default DESC, r.id ASC
            """
        ).fetchall()

    providers = []
    for row in provider_rows:
        item = _row_to_dict(row)
        item["api_key_masked"] = _mask_key(item.pop("api_key"))
        providers.append(item)

    return {
        "providers": providers,
        "roles": [_row_to_dict(row) for row in role_rows],
    }


def save_provider(data: Dict) -> Dict:
    name = str(data.get("name", "")).strip()
    provider_type = str(data.get("provider_type", "openai_compatible")).strip() or "openai_compatible"
    base_url = str(data.get("base_url", "")).strip().rstrip("/")
    model = str(data.get("model", "")).strip()
    api_key = str(data.get("api_key", "")).strip()
    api_key_required = 1 if data.get("api_key_required", True) else 0
    is_active = 1 if data.get("is_active", True) else 0
    is_default = 1 if data.get("is_default", False) else 0
    provider_id = data.get("id") or None

    if provider_type not in {"openai_compatible", "ollama_native"}:
        raise ValueError("接口类型不支持")
    if not name or not base_url or not model:
        raise ValueError("模型名称、Base URL、模型标识不能为空")
    if provider_type == "openai_compatible":
        base_url = _normalize_openai_base_url(base_url)
    if _looks_local_base_url(base_url) and not api_key:
        api_key_required = 0

    with _connect() as conn:
        now = _now()
        if is_default:
            conn.execute("UPDATE llm_providers SET is_default = 0")

        if provider_id:
            existing = conn.execute(
                "SELECT api_key FROM llm_providers WHERE id = ?", (provider_id,)
            ).fetchone()
            if not existing:
                raise ValueError("模型配置不存在")
            if not api_key:
                api_key = existing["api_key"]
            conn.execute(
                """
                UPDATE llm_providers
                SET name = ?, provider_type = ?, base_url = ?, model = ?, api_key = ?,
                    api_key_required = ?, is_active = ?, is_default = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    name,
                    provider_type,
                    base_url,
                    model,
                    api_key,
                    api_key_required,
                    is_active,
                    is_default,
                    now,
                    provider_id,
                ),
            )
        else:
            cur = conn.execute(
                """
                INSERT INTO llm_providers
                (name, provider_type, base_url, model, api_key, api_key_required,
                 is_active, is_default, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    provider_type,
                    base_url,
                    model,
                    api_key,
                    api_key_required,
                    is_active,
                    is_default,
                    now,
                    now,
                ),
            )
            provider_id = cur.lastrowid

    return {"id": provider_id}


def save_role(data: Dict) -> Dict:
    name = str(data.get("name", "")).strip()
    avatar_style = str(data.get("avatar_style", "")).strip()
    specialty = str(data.get("specialty", "")).strip()
    system_prompt = str(data.get("system_prompt", "")).strip()
    provider_id = int(data.get("llm_provider_id") or 0)
    is_active = 1 if data.get("is_active", True) else 0
    is_default = 1 if data.get("is_default", False) else 0
    role_id = data.get("id") or None

    if not name or not system_prompt or not provider_id:
        raise ValueError("角色名称、关联模型、System Prompt 不能为空")

    with _connect() as conn:
        provider = conn.execute(
            "SELECT id FROM llm_providers WHERE id = ?", (provider_id,)
        ).fetchone()
        if not provider:
            raise ValueError("关联模型不存在")

        now = _now()
        if is_default:
            conn.execute("UPDATE llm_roles SET is_default = 0")

        if role_id:
            existing = conn.execute("SELECT id FROM llm_roles WHERE id = ?", (role_id,)).fetchone()
            if not existing:
                raise ValueError("角色不存在")
            conn.execute(
                """
                UPDATE llm_roles
                SET name = ?, avatar_style = ?, llm_provider_id = ?, system_prompt = ?,
                    specialty = ?, is_active = ?, is_default = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    name,
                    avatar_style,
                    provider_id,
                    system_prompt,
                    specialty,
                    is_active,
                    is_default,
                    now,
                    role_id,
                ),
            )
        else:
            cur = conn.execute(
                """
                INSERT INTO llm_roles
                (name, avatar_style, llm_provider_id, system_prompt, specialty,
                 is_active, is_default, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    avatar_style,
                    provider_id,
                    system_prompt,
                    specialty,
                    is_active,
                    is_default,
                    now,
                    now,
                ),
            )
            role_id = cur.lastrowid

    return {"id": role_id}


def get_role_config(role_id: Optional[int]) -> Optional[Dict]:
    where = "r.id = ? AND r.is_active = 1"
    params = (role_id,)
    if not role_id:
        where = "r.is_active = 1"
        params = ()

    with _connect() as conn:
        row = conn.execute(
            f"""
            SELECT r.id AS role_id, r.name AS role_name, r.system_prompt, r.specialty,
                   p.id AS provider_id, p.name AS provider_name, p.provider_type,
                   p.base_url, p.model, p.api_key, p.api_key_required,
                   p.is_active AS provider_active
            FROM llm_roles r
            JOIN llm_providers p ON p.id = r.llm_provider_id
            WHERE {where}
            ORDER BY r.is_default DESC, r.id ASC
            LIMIT 1
            """,
            params,
        ).fetchone()

    if not row:
        return None
    return _row_to_dict(row)
