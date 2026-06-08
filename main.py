"""碰面地点查找器 - FastAPI Web 应用"""

import logging
import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from models import MeetRequest, MeetResponse, MeetData, LocationInfo, POIInfo
from amap import (
    geocode,
    reverse_geocode,
    search_pois_around,
    calc_midpoint,
    haversine,
    estimate_travel_time_km,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="碰面地点查找器", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")


def _parse_coord(location_str: str) -> tuple[float, float]:
    """解析高德 location 字符串 'lng,lat' -> (lng, lat)"""
    lng_str, lat_str = location_str.split(",")
    return float(lng_str), float(lat_str)


def _safe_str(value, default="-"):
    """安全提取字符串值，处理列表/None 情况"""
    if isinstance(value, list):
        return str(value[0]) if value else default
    return str(value) if value else default


@app.exception_handler(RuntimeError)
async def runtime_error_handler(request: Request, exc: RuntimeError):
    logger.error("RuntimeError: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"success": False, "data": None, "error": str(exc)},
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(
        status_code=400,
        content={"success": False, "data": None, "error": str(exc)},
    )


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def root():
    return FileResponse("static/index.html")


@app.post("/api/meet", response_model=MeetResponse)
async def find_meet_place(req: MeetRequest):
    """核心接口：输入两个地址，返回碰面地点推荐"""
    logger.info("查询碰面地点: [%s] <-> [%s]", req.addr1, req.addr2)

    # Step 1: 地理编码
    geo1 = geocode(req.addr1)
    geo2 = geocode(req.addr2)

    if not geo1:
        raise ValueError(f"无法解析地址 A：「{req.addr1}」，请提供更详细的地址")
    if not geo2:
        raise ValueError(f"无法解析地址 B：「{req.addr2}」，请提供更详细的地址")

    # Step 2: 计算中点
    mid_lng, mid_lat = calc_midpoint(
        geo1["lng"], geo1["lat"], geo2["lng"], geo2["lat"]
    )
    distance_ab = haversine(geo1["lng"], geo1["lat"], geo2["lng"], geo2["lat"])

    mid_info = reverse_geocode(mid_lng, mid_lat)
    mid_address = (
        mid_info["address"] if mid_info
        else f"({mid_lng:.4f}, {mid_lat:.4f})"
    )

    # Step 3: 搜索周边 POI
    categories = [c.strip() for c in req.type.split(",") if c.strip()]
    all_pois = []
    seen_ids = set()

    for cat in categories:
        pois = search_pois_around(mid_lng, mid_lat, cat, req.radius, req.limit)
        for poi in pois:
            pid = poi.get("id") or poi.get("name")
            if pid not in seen_ids:
                seen_ids.add(pid)
                poi["_category"] = cat
                all_pois.append(poi)

    # 无结果时扩大半径重试
    if not all_pois:
        logger.info("扩大搜索半径重试...")
        for cat in categories:
            pois = search_pois_around(
                mid_lng, mid_lat, cat, req.radius * 2, req.limit
            )
            for poi in pois:
                pid = poi.get("id") or poi.get("name")
                if pid not in seen_ids:
                    seen_ids.add(pid)
                    poi["_category"] = cat
                    all_pois.append(poi)

    # Step 4: 构建 POI 信息列表
    poi_infos = []
    for poi in all_pois:
        try:
            p_lng, p_lat = _parse_coord(poi["location"])
        except (ValueError, KeyError):
            continue

        biz = poi.get("biz_ext") or {}
        rating = _safe_str(biz.get("rating", "-"))
        cost = _safe_str(biz.get("cost", ""))
        avg_cost = f"¥{cost}" if cost and cost != "-" else "-"

        dist_a = haversine(geo1["lng"], geo1["lat"], p_lng, p_lat)
        dist_b = haversine(geo2["lng"], geo2["lat"], p_lng, p_lat)
        dist_mid = haversine(mid_lng, mid_lat, p_lng, p_lat)

        poi_infos.append(
            POIInfo(
                id=poi.get("id", poi.get("name", "")),
                name=poi.get("name", "未知"),
                type=poi.get("type", ""),
                category=poi.get("_category", ""),
                address=poi.get("address", ""),
                lng=p_lng,
                lat=p_lat,
                rating=rating,
                avg_cost=avg_cost,
                distance_from_a=round(dist_a, 1),
                distance_from_b=round(dist_b, 1),
                distance_from_midpoint=round(dist_mid, 1),
                travel_time_a=estimate_travel_time_km(dist_a, "mixed"),
                travel_time_b=estimate_travel_time_km(dist_b, "mixed"),
            )
        )

    # 按评分降序排序
    poi_infos.sort(
        key=lambda p: float(p.rating) if p.rating.replace(".", "").isdigit() else 0,
        reverse=True,
    )

    # Step 5: 生成建议
    tips = ["优先选择评分高、双方距离接近的场所"]
    if distance_ab < 3:
        tips.append(f"两地仅相距 {distance_ab:.1f}km，步行或骑行即可")
    elif distance_ab < 10:
        tips.append(f"两地相距 {distance_ab:.1f}km，推荐地铁出行")

    return MeetResponse(
        success=True,
        data=MeetData(
            location_a=LocationInfo(
                lng=geo1["lng"], lat=geo1["lat"], address=geo1["address"]
            ),
            location_b=LocationInfo(
                lng=geo2["lng"], lat=geo2["lat"], address=geo2["address"]
            ),
            midpoint=LocationInfo(
                lng=mid_lng, lat=mid_lat, address=mid_address
            ),
            distance_ab=round(distance_ab, 1),
            pois=poi_infos,
            tips=tips,
        ),
    )
