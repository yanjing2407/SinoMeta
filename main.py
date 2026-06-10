# -*- coding: utf-8 -*-
"""
术数系统 Web 服务
================
FastAPI 后端，提供起盘和解卦接口
启动: python main.py
"""

import sys
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent))

from integrate import multi_divination, stream_interpret

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="术数起盘系统")

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
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"


# ==================== 工具函数 ====================

def make_serializable(obj):
    if isinstance(obj, dict):
        return {str(k): make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [make_serializable(i) for i in obj]
    if isinstance(obj, (int, float, str, bool, type(None))):
        return obj
    return str(obj)


def do_multi_divination(req):
    """统一起盘：如提供出生时间且选了八字，八字用出生时间，其余用起卦时间"""
    has_birth = all([
        req.birth_year, req.birth_month, req.birth_day,
        req.birth_hour is not None
    ])

    liuyao_nums = tuple(req.liuyao_nums) if req.liuyao_nums and len(req.liuyao_nums) >= 2 else None
    meihua_nums = tuple(req.meihua_nums) if req.meihua_nums and len(req.meihua_nums) >= 2 else None

    if has_birth and '八字' in req.methods:
        other_methods = [m for m in req.methods if m != '八字']
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
            )
            results.update(r.get('术数结果', {}))

        r_bazi = multi_divination(
            event=req.event,
            year=req.birth_year, month=req.birth_month, day=req.birth_day,
            hour=req.birth_hour, minute=req.birth_minute or 0,
            longitude=req.longitude, latitude=req.latitude,
            gender=req.gender, methods=['八字'],
        )
        results.update(r_bazi.get('术数结果', {}))

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
        )


# ==================== 页面路由 ====================

@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


# ==================== API 路由 ====================

@app.post("/api/divine")
async def divine(req: DivineRequest):
    """起盘接口"""
    result = do_multi_divination(req)
    return make_serializable(result)


@app.post("/api/interpret")
async def interpret(req: InterpretRequest):
    """解卦接口（SSE流式）"""
    if not req.api_key:
        return {"error": "请先配置API Key"}

    result = do_multi_divination(req)

    def event_stream():
        try:
            for token in stream_interpret(
                result,
                api_key=req.api_key, base_url=req.base_url, model=req.model,
                prompt_type="interpret",
            ):
                yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/advice")
async def advice(req: InterpretRequest):
    """破局建议接口（SSE流式）"""
    if not req.api_key:
        return {"error": "请先配置API Key"}

    result = do_multi_divination(req)

    def event_stream():
        try:
            for token in stream_interpret(
                result,
                api_key=req.api_key, base_url=req.base_url, model=req.model,
                prompt_type="advice",
            ):
                yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

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
