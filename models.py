"""Pydantic 数据模型"""

from pydantic import BaseModel, Field


class MeetRequest(BaseModel):
    """碰面地点查询请求"""

    addr1: str = Field(
        ...,
        min_length=1,
        description="第一个地址",
        examples=["北京朝阳区望京"],
    )
    addr2: str = Field(
        ...,
        min_length=1,
        description="第二个地址",
        examples=["北京海淀区中关村"],
    )
    type: str = Field(
        default="咖啡,餐厅,茶馆,商场",
        description="POI 类型，逗号分隔",
    )
    radius: int = Field(
        default=2000,
        ge=500,
        le=10000,
        description="搜索半径（米）",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=20,
        description="每种类型返回数量上限",
    )


class LocationInfo(BaseModel):
    """地点信息"""

    lng: float
    lat: float
    address: str


class POIInfo(BaseModel):
    """POI 场所信息"""

    id: str
    name: str
    type: str
    category: str
    address: str
    lng: float
    lat: float
    rating: str
    avg_cost: str
    distance_from_a: float
    distance_from_b: float
    distance_from_midpoint: float
    travel_time_a: str
    travel_time_b: str


class MeetData(BaseModel):
    """碰面结果数据"""

    location_a: LocationInfo
    location_b: LocationInfo
    midpoint: LocationInfo
    distance_ab: float
    pois: list[POIInfo]
    tips: list[str]


class MeetResponse(BaseModel):
    """碰面查询响应"""

    success: bool
    data: MeetData | None = None
    error: str | None = None
