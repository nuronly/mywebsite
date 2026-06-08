"""高德地图 Web API 工具模块

提供地理编码、逆地理编码、POI 搜索、距离计算等功能。
所有函数均为纯函数，不依赖 Web 框架。

环境变量:
    AMAP_KEY: 高德开放平台 Web 服务 API Key
"""

import os
import math
import logging

import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# 加载 .env 文件
load_dotenv()

API_KEY = os.environ.get("AMAP_KEY", "")
GEOCODE_URL = "https://restapi.amap.com/v3/geocode/geo"
REGEO_URL = "https://restapi.amap.com/v3/geocode/regeo"
POI_AROUND_URL = "https://restapi.amap.com/v3/place/around"


def _require_key():
    if not API_KEY:
        raise RuntimeError("AMAP_KEY 环境变量未设置")


def geocode(address: str, city: str = "") -> dict | None:
    """地址 -> 坐标

    Returns:
        dict with lng, lat, address, adcode, city  or None
    """
    _require_key()
    params = {"key": API_KEY, "address": address}
    if city:
        params["city"] = city
    try:
        resp = requests.get(GEOCODE_URL, params=params, timeout=10)
        data = resp.json()
        if data.get("status") != "1":
            infocode = data.get("infocode", "")
            info = data.get("info", "未知错误")
            if infocode == "10001":
                raise RuntimeError("高德 API Key 无效")
            if infocode in ("10003", "10005"):
                raise RuntimeError(f"API Key 权限不足: {info}")
            logger.warning("geocode failed for [%s]: %s (code=%s)", address, info, infocode)
            return None
        if not data.get("geocodes"):
            return None
        geo = data["geocodes"][0]
        lng, lat = geo["location"].split(",")
        return {
            "lng": float(lng),
            "lat": float(lat),
            "address": geo.get("formatted_address", address),
            "adcode": geo.get("adcode", ""),
            "city": geo.get("city", ""),
        }
    except requests.RequestException as e:
        logger.error("geocode network error [%s]: %s", address, e)
        return None


def reverse_geocode(lng: float, lat: float) -> dict | None:
    """坐标 -> 地址

    Returns:
        dict with address, district, township, adcode  or None
    """
    _require_key()
    params = {"key": API_KEY, "location": f"{lng},{lat}", "extensions": "base"}
    try:
        resp = requests.get(REGEO_URL, params=params, timeout=10)
        data = resp.json()
        if data.get("status") != "1":
            return None
        regeo = data["regeocode"]
        addr = regeo.get("addressComponent", {})
        return {
            "address": regeo.get("formatted_address", ""),
            "district": addr.get("district", ""),
            "township": addr.get("township", ""),
            "adcode": addr.get("adcode", ""),
        }
    except requests.RequestException as e:
        logger.error("reverse_geocode network error: %s", e)
        return None


def search_pois_around(lng: float, lat: float, keywords: str,
                        radius: int = 2000, limit: int = 10) -> list:
    """周边 POI 搜索

    Returns:
        list of POI dicts (may be empty)
    """
    _require_key()
    params = {
        "key": API_KEY,
        "location": f"{lng},{lat}",
        "keywords": keywords,
        "radius": radius,
        "offset": limit,
        "page": 1,
        "extensions": "all",
    }
    try:
        resp = requests.get(POI_AROUND_URL, params=params, timeout=10)
        data = resp.json()
        if data.get("status") != "1":
            return []
        return data.get("pois", [])
    except requests.RequestException as e:
        logger.error("POI search error [%s]: %s", keywords, e)
        return []


def calc_midpoint(lng1: float, lat1: float, lng2: float, lat2: float):
    """计算两点地理中点"""
    return (lng1 + lng2) / 2, (lat1 + lat2) / 2


def haversine(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    """计算两点间的距离 (km)"""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlng / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def estimate_travel_time_km(distance_km: float, mode: str = "mixed") -> str:
    """根据距离估算出行时间"""
    if mode == "driving":
        speed = 40
    elif mode == "transit":
        speed = 25
    else:
        speed = 30
    minutes = (distance_km / speed) * 60 + 5
    if minutes < 1:
        return "<1分钟"
    elif minutes < 60:
        return f"约{int(minutes)}分钟"
    else:
        h = int(minutes // 60)
        m = int(minutes % 60)
        return f"约{h}小时{m}分钟"
