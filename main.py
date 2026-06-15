# -*- coding: utf-8 -*-
"""
术数系统 Web 服务
================
FastAPI 后端，提供起盘和解卦接口
启动: python main.py
"""

import sys
import json
import os
import logging
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent))

from integrate import multi_divination, stream_interpret
from llm_store import (
    _looks_local_base_url,
    get_role_config,
    init_db,
    list_admin_config,
    list_public_roles,
    save_provider,
    save_role,
)

STATIC_DIR = Path(__file__).parent / "static"
LOG_PATH = Path(os.getenv("SINOMETA_LOG_PATH", Path(__file__).parent / "data" / "sinometa.log"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger("sinometa")
logging.basicConfig(
    level=os.getenv("SINOMETA_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
if not any(isinstance(handler, RotatingFileHandler) for handler in logger.handlers):
    file_handler = RotatingFileHandler(
        LOG_PATH,
        maxBytes=1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    logger.addHandler(file_handler)

app = FastAPI(title="术数起盘系统")
init_db()

# CORS（允许手机等设备访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== 请求模型 ====================

class DivineRequest(BaseModel):
    event: str
    year: int
    month: int
    day: int
    hour: int
    minute: int = 0
    longitude: float = 120.0
    latitude: float = 30.0
    gender: str = "男"
    methods: list = ["八字", "奇门", "梅花"]
    birth_year: Optional[int] = None
    birth_month: Optional[int] = None
    birth_day: Optional[int] = None
    birth_hour: Optional[int] = None
    birth_minute: Optional[int] = 0
    liuyao_nums: Optional[list] = None
    meihua_nums: Optional[list] = None
    azimuth: Optional[float] = None


class InterpretRequest(DivineRequest):
    role_id: Optional[int] = None
    lenient_mode: bool = False
    mode: str = 'concise'  # 'concise' 或 'expert'


class ProviderPayload(BaseModel):
    id: Optional[int] = None
    name: str
    provider_type: str = "openai_compatible"
    base_url: str
    model: str
    api_key: str = ""
    api_key_required: bool = True
    is_active: bool = True
    is_default: bool = False


class RolePayload(BaseModel):
    id: Optional[int] = None
    name: str
    avatar_style: str = ""
    llm_provider_id: int
    system_prompt: str
    specialty: str = ""
    is_active: bool = True
    is_default: bool = False


# ==================== 工具函数 ====================

def make_serializable(obj):
    if isinstance(obj, dict):
        return {str(k): make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [make_serializable(i) for i in obj]
    if isinstance(obj, (int, float, str, bool, type(None))):
        return obj
    return str(obj)


def require_admin(request: Request, authorization: str = Header(default="")):
    token = os.getenv("SINOMETA_ADMIN_TOKEN", "").strip()
    if not token:
        host = (request.url.hostname or "").lower()
        if host in {"127.0.0.1", "::1", "localhost"}:
            return
        raise HTTPException(status_code=403, detail="请先设置 SINOMETA_ADMIN_TOKEN")

    expected = f"Bearer {token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="后台令牌无效")


def resolve_active_role(role_id: Optional[int]):
    role = get_role_config(role_id)
    if not role:
        raise HTTPException(status_code=400, detail="角色不存在或已停用")
    if not role["provider_active"]:
        raise HTTPException(status_code=400, detail="角色关联的模型已停用")
    if role["api_key_required"] and not role["api_key"]:
        raise HTTPException(status_code=400, detail="请先在后台配置该角色关联模型的 API Key")
    return role


def allow_lenient_mode(req: InterpretRequest, role: dict) -> bool:
    return bool(req.lenient_mode and _looks_local_base_url(role.get("base_url", "")))


def do_multi_divination(req):
    """统一起盘：八字/紫微用出生时间，其余用起卦时间"""
    has_birth = all([
        req.birth_year, req.birth_month, req.birth_day,
        req.birth_hour is not None
    ])

    liuyao_nums = tuple(req.liuyao_nums) if req.liuyao_nums and len(req.liuyao_nums) >= 2 else None
    meihua_nums = tuple(req.meihua_nums) if req.meihua_nums and len(req.meihua_nums) >= 2 else None

    birth_methods = {'八字', '紫微'}
    need_birth = has_birth and bool(birth_methods & set(req.methods))

    if need_birth:
        birth_set = [m for m in req.methods if m in birth_methods]
        other_methods = [m for m in req.methods if m not in birth_methods]
        results = {}

        if other_methods:
            r = multi_divination(
                event=req.event,
                year=req.year, month=req.month, day=req.day,
                hour=req.hour, minute=req.minute,
                longitude=req.longitude, latitude=req.latitude,
                gender=req.gender, methods=other_methods,
                liuyao_nums=liuyao_nums,
                meihua_nums=meihua_nums,
                azimuth=req.azimuth,
                birth_year=req.birth_year,
            )
            results.update(r.get('术数结果', {}))

        r_birth = multi_divination(
            event=req.event,
            year=req.birth_year, month=req.birth_month, day=req.birth_day,
            hour=req.birth_hour, minute=req.birth_minute or 0,
            longitude=req.longitude, latitude=req.latitude,
            gender=req.gender, methods=birth_set,
            birth_year=req.birth_year,
        )
        results.update(r_birth.get('术数结果', {}))

        return {
            '事件': req.event,
            '时空坐标': {
                '时间': f'{req.year}-{req.month:02d}-{req.day:02d} {req.hour:02d}:{req.minute:02d}',
                '经度': req.longitude, '纬度': req.latitude,
                '城市估算': '',
            },
            '术数结果': results,
        }
    else:
        return multi_divination(
            event=req.event,
            year=req.year, month=req.month, day=req.day,
            hour=req.hour, minute=req.minute,
            longitude=req.longitude, latitude=req.latitude,
            gender=req.gender, methods=req.methods,
            liuyao_nums=liuyao_nums,
            meihua_nums=meihua_nums,
            azimuth=req.azimuth,
            birth_year=req.birth_year,
        )


# ==================== 页面路由 ====================

@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/admin")
async def admin_page():
    return FileResponse(STATIC_DIR / "admin.html")


# ==================== API 路由 ====================

@app.post("/api/divine")
async def divine(req: DivineRequest):
    """起盘接口"""
    result = do_multi_divination(req)
    return make_serializable(result)


@app.get("/api/roles")
async def roles():
    """前台角色列表"""
    try:
        return {"roles": list_public_roles()}
    except Exception as exc:
        logger.exception("Role list failed")
        raise HTTPException(status_code=500, detail=f"角色加载失败：{exc}")


@app.get("/api/admin/config")
async def admin_config(request: Request, authorization: str = Header(default="")):
    """后台配置列表"""
    require_admin(request, authorization)
    return list_admin_config()


@app.post("/api/admin/providers")
async def admin_save_provider(
    payload: ProviderPayload, request: Request, authorization: str = Header(default="")
):
    """新增或更新模型配置"""
    require_admin(request, authorization)
    try:
        return save_provider(payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/admin/roles")
async def admin_save_role(
    payload: RolePayload, request: Request, authorization: str = Header(default="")
):
    """新增或更新角色配置"""
    require_admin(request, authorization)
    try:
        return save_role(payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/interpret")
async def interpret(req: InterpretRequest):
    """解卦接口（SSE流式）"""
    role = resolve_active_role(req.role_id)
    lenient_mode = allow_lenient_mode(req, role)

    result = do_multi_divination(req)
    trace_id = uuid.uuid4().hex[:8]

    def event_stream():
        logger.info(
            "LLM stream start trace=%s endpoint=interpret role=%s provider=%s type=%s model=%s base_url=%s lenient=%s mode=%s",
            trace_id,
            role.get("role_name"),
            role.get("provider_name"),
            role.get("provider_type"),
            role.get("model"),
            role.get("base_url"),
            lenient_mode,
            req.mode,
        )
        try:
            for token in stream_interpret(
                result,
                api_key=role["api_key"],
                base_url=role["base_url"],
                model=role["model"],
                system_prompt=role["system_prompt"],
                provider_type=role["provider_type"],
                prompt_type="interpret",
                lenient_mode=lenient_mode,
                mode=req.mode,
            ):
                yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
            logger.info("LLM stream done trace=%s endpoint=interpret", trace_id)
            yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.exception("LLM stream failed trace=%s endpoint=interpret", trace_id)
            yield f"data: {json.dumps({'error': str(e), 'trace_id': trace_id}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/advice")
async def advice(req: InterpretRequest):
    """破局建议接口（SSE流式）"""
    role = resolve_active_role(req.role_id)
    lenient_mode = allow_lenient_mode(req, role)

    result = do_multi_divination(req)
    trace_id = uuid.uuid4().hex[:8]

    def event_stream():
        logger.info(
            "LLM stream start trace=%s endpoint=advice role=%s provider=%s type=%s model=%s base_url=%s lenient=%s mode=%s",
            trace_id,
            role.get("role_name"),
            role.get("provider_name"),
            role.get("provider_type"),
            role.get("model"),
            role.get("base_url"),
            lenient_mode,
            req.mode,
        )
        try:
            for token in stream_interpret(
                result,
                api_key=role["api_key"],
                base_url=role["base_url"],
                model=role["model"],
                system_prompt=role["system_prompt"],
                provider_type=role["provider_type"],
                prompt_type="advice",
                lenient_mode=lenient_mode,
                mode=req.mode,
            ):
                yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
            logger.info("LLM stream done trace=%s endpoint=advice", trace_id)
            yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.exception("LLM stream failed trace=%s endpoint=advice", trace_id)
            yield f"data: {json.dumps({'error': str(e), 'trace_id': trace_id}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ==================== 静态文件（必须在所有路由之后挂载） ====================

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ==================== 启动 ====================

if __name__ == "__main__":
    import uvicorn
    import socket

    def find_free_port(start=8000, end=8100):
        for port in range(start, end):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(('0.0.0.0', port))
                    return port
                except OSError:
                    continue
        return start

    port = find_free_port()
    print("=" * 50)
    print("  术数起盘系统")
    print(f"  访问 http://localhost:{port}")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=port)
