from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from typing import Any, Protocol

import httpx
from pydantic import TypeAdapter, ValidationError

from app.schemas import Attraction, Budget, Hotel, Location, Meal, RouteLeg, TripPlanRequest, WeatherInfo
from app.settings import Settings


@dataclass(frozen=True)
class TravelToolDefinition:
    name: str
    category: str
    description: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "category": self.category,
            "description": self.description,
        }


class TravelToolProvider(Protocol):
    name: str

    def list_tools(self) -> tuple[TravelToolDefinition, ...]:
        ...

    def date_for_day(self, request: TripPlanRequest, day: int) -> str | None:
        ...

    def attractions_for_day(self, request: TripPlanRequest, day: int) -> list[Attraction]:
        ...

    def hotel_for_day(self, request: TripPlanRequest, day: int) -> Hotel:
        ...

    def meals_for_day(self, request: TripPlanRequest, day: int) -> list[Meal]:
        ...

    def routes_for_day(
        self,
        request: TripPlanRequest,
        day: int,
        attractions: list[Attraction],
        hotel: Hotel | None = None,
    ) -> list[RouteLeg]:
        ...

    def weather_for_trip(self, request: TripPlanRequest) -> list[WeatherInfo]:
        ...

    def estimate_budget(self, request: TripPlanRequest) -> Budget:
        ...


@dataclass(frozen=True)
class MockTravelToolProvider:
    name: str = "mock"

    def list_tools(self) -> tuple[TravelToolDefinition, ...]:
        return (
            TravelToolDefinition(
                name="date_for_day",
                category="calendar",
                description="Derives the itinerary date for a day when a trip start date is available.",
            ),
            TravelToolDefinition(
                name="attractions_for_day",
                category="poi",
                description="Returns deterministic mock attractions for an itinerary day.",
            ),
            TravelToolDefinition(
                name="hotel_for_day",
                category="lodging",
                description="Returns a deterministic mock hotel matched to destination and budget.",
            ),
            TravelToolDefinition(
                name="meals_for_day",
                category="food",
                description="Returns deterministic mock meal suggestions for breakfast, lunch, and dinner.",
            ),
            TravelToolDefinition(
                name="routes_for_day",
                category="route",
                description="Returns deterministic mock route legs between the hotel and daily attractions.",
            ),
            TravelToolDefinition(
                name="weather_for_trip",
                category="weather",
                description="Returns deterministic mock weather for the trip duration.",
            ),
            TravelToolDefinition(
                name="estimate_budget",
                category="budget",
                description="Estimates itinerary costs from mock attractions, hotel, meals, and transit.",
            ),
        )

    def date_for_day(self, request: TripPlanRequest, day: int) -> str | None:
        if not request.start_date:
            return None
        try:
            start_date = datetime.strptime(request.start_date, "%Y-%m-%d")
        except ValueError:
            return None
        return (start_date + timedelta(days=day - 1)).date().isoformat()

    def attractions_for_day(self, request: TripPlanRequest, day: int) -> list[Attraction]:
        landmark_candidates = _landmark_candidates(request.destination)
        if landmark_candidates:
            start = ((day - 1) * 2) % len(landmark_candidates)
            selected = [landmark_candidates[(start + index) % len(landmark_candidates)] for index in range(2)]
            return [
                Attraction(
                    name=item["name"],
                    address=item["address"],
                    location=Location(longitude=item["longitude"], latitude=item["latitude"]),
                    visit_duration=90 + index * 30,
                    description=(
                        f"{item['name']} is a practical {request.destination} stop matched to "
                        f"{request.interests or 'local culture'} for day {day}."
                    ),
                    category=item["category"],
                    rating=4.6,
                    ticket_price=item["ticket_price"],
                )
                for index, item in enumerate(selected)
            ]

        base_lng = 104.0668
        base_lat = 30.5728
        return [
            Attraction(
                name=f"{request.destination} local highlight {day}-{index}",
                address=f"{request.destination} central area",
                location=Location(
                    longitude=base_lng + day * 0.01 + index * 0.004,
                    latitude=base_lat + day * 0.008 + index * 0.003,
                ),
                visit_duration=90 + index * 30,
                description=f"A practical local stop matched to {request.interests or 'local culture'} for day {day}.",
                category="attraction",
                rating=4.5,
                ticket_price=40 + index * 20,
            )
            for index in range(1, 3)
        ]

    def hotel_for_day(self, request: TripPlanRequest, day: int) -> Hotel:
        return Hotel(
            name=f"{request.destination} {request.accommodation or 'comfort'} stay {day}",
            address=f"{request.destination} transit-friendly district",
            location=Location(longitude=104.0668 + day * 0.006, latitude=30.5728 + day * 0.006),
            price_range=_hotel_price_range(request.budget),
            rating="4.5",
            distance="Within 20 minutes of the main route",
            type=request.accommodation or "comfortable hotel",
            estimated_cost=_hotel_cost(request.budget),
        )

    def meals_for_day(self, request: TripPlanRequest, day: int) -> list[Meal]:
        local_meals = _local_meal_candidates(request.destination)
        if local_meals:
            return [
                Meal(
                    type=meal_type,
                    name=local_meals[(day + index - 1) % len(local_meals)],
                    description=f"Local {meal_type} option matched to {request.interests or 'local food'}.",
                    estimated_cost=cost,
                )
                for index, (meal_type, cost) in enumerate({"breakfast": 25, "lunch": 55, "dinner": 90}.items())
            ]

        costs = {"breakfast": 25, "lunch": 55, "dinner": 90}
        return [
            Meal(
                type=meal_type,
                name=f"{request.destination} {meal_type} option {day}",
                description=f"Local {meal_type} matched to {request.interests or 'general travel'}.",
                estimated_cost=cost,
            )
            for meal_type, cost in costs.items()
        ]

    def routes_for_day(
        self,
        request: TripPlanRequest,
        day: int,
        attractions: list[Attraction],
        hotel: Hotel | None = None,
    ) -> list[RouteLeg]:
        if not attractions:
            return []

        mode = request.transportation or "mixed transit"
        start_name = hotel.name if hotel is not None else f"{request.destination} hotel area"
        stops = [start_name, *[attraction.name for attraction in attractions], start_name]
        return [
            RouteLeg(
                from_name=stops[index],
                to_name=stops[index + 1],
                mode=mode,
                distance_meters=1800 + day * 250 + index * 650,
                duration_minutes=18 + day * 2 + index * 8,
                estimated_cost=_route_leg_cost(mode, index),
                instruction=f"Use {mode} from {stops[index]} to {stops[index + 1]}, then keep a small buffer for traffic.",
            )
            for index in range(len(stops) - 1)
        ]

    def weather_for_trip(self, request: TripPlanRequest) -> list[WeatherInfo]:
        return [
            WeatherInfo(
                date=self.date_for_day(request, day) or f"Day {day}",
                day_weather="Cloudy",
                night_weather="Clear",
                day_temp=24 + (day % 4),
                night_temp=16 + (day % 3),
                wind_direction="East",
                wind_power="1-3",
            )
            for day in range(1, request.days + 1)
        ]

    def estimate_budget(self, request: TripPlanRequest) -> Budget:
        attraction_total = request.days * 100
        hotel_total = request.days * _hotel_cost(request.budget)
        meal_total = request.days * 170
        transportation_total = request.days * 60
        return Budget(
            total_attractions=attraction_total,
            total_hotels=hotel_total,
            total_meals=meal_total,
            total_transportation=transportation_total,
            total=attraction_total + hotel_total + meal_total + transportation_total,
        )


class FastMCPTravelToolProvider:
    name = "fastmcp"

    def __init__(self, settings: Settings, fallback: TravelToolProvider | None = None) -> None:
        self._settings = settings
        self._fallback = fallback or MockTravelToolProvider(name="mock:fastmcp_fallback")
        self._client = _FastMCPToolClient(settings)

    def list_tools(self) -> tuple[TravelToolDefinition, ...]:
        return (
            TravelToolDefinition(
                name="date_for_day",
                category="calendar",
                description="Derives the itinerary date locally before FastMCP travel tool enrichment.",
            ),
            TravelToolDefinition(
                name="attractions_for_day",
                category="poi",
                description=f"Calls FastMCP tool {self._settings.fastmcp_attractions_tool}; falls back to mock POI data.",
            ),
            TravelToolDefinition(
                name="hotel_for_day",
                category="lodging",
                description=f"Calls FastMCP tool {self._settings.fastmcp_hotel_tool}; falls back to mock hotel data.",
            ),
            TravelToolDefinition(
                name="meals_for_day",
                category="food",
                description=f"Calls FastMCP tool {self._settings.fastmcp_meals_tool}; falls back to mock meal data.",
            ),
            TravelToolDefinition(
                name="routes_for_day",
                category="route",
                description=f"Calls FastMCP tool {self._settings.fastmcp_routes_tool}; falls back to mock route data.",
            ),
            TravelToolDefinition(
                name="weather_for_trip",
                category="weather",
                description=f"Calls FastMCP tool {self._settings.fastmcp_weather_tool}; falls back to mock weather data.",
            ),
            TravelToolDefinition(
                name="estimate_budget",
                category="budget",
                description=f"Calls FastMCP tool {self._settings.fastmcp_budget_tool}; falls back to mock budget data.",
            ),
        )

    def date_for_day(self, request: TripPlanRequest, day: int) -> str | None:
        return self._fallback.date_for_day(request, day)

    def attractions_for_day(self, request: TripPlanRequest, day: int) -> list[Attraction]:
        arguments = {
            "destination": request.destination,
            "day": day,
            "days": request.days,
            "interests": request.interests,
            "preferences": request.preferences,
            "budget": request.budget,
        }
        try:
            payload = self._client.call_tool(self._settings.fastmcp_attractions_tool, arguments)
            return _validate_list(payload, Attraction)
        except FastMCPToolError:
            return self._fallback.attractions_for_day(request, day)

    def hotel_for_day(self, request: TripPlanRequest, day: int) -> Hotel:
        arguments = {
            "destination": request.destination,
            "day": day,
            "budget": request.budget,
            "accommodation": request.accommodation,
            "transportation": request.transportation,
        }
        try:
            payload = self._client.call_tool(self._settings.fastmcp_hotel_tool, arguments)
            return Hotel.model_validate(payload)
        except (FastMCPToolError, ValidationError, TypeError):
            return self._fallback.hotel_for_day(request, day)

    def meals_for_day(self, request: TripPlanRequest, day: int) -> list[Meal]:
        arguments = {
            "destination": request.destination,
            "day": day,
            "interests": request.interests,
            "budget": request.budget,
        }
        try:
            payload = self._client.call_tool(self._settings.fastmcp_meals_tool, arguments)
            return _validate_list(payload, Meal)
        except FastMCPToolError:
            return self._fallback.meals_for_day(request, day)

    def routes_for_day(
        self,
        request: TripPlanRequest,
        day: int,
        attractions: list[Attraction],
        hotel: Hotel | None = None,
    ) -> list[RouteLeg]:
        arguments = {
            "destination": request.destination,
            "day": day,
            "transportation": request.transportation,
            "hotel": hotel.model_dump(mode="json", by_alias=True) if hotel else None,
            "attractions": [item.model_dump(mode="json", by_alias=True) for item in attractions],
        }
        try:
            payload = self._client.call_tool(self._settings.fastmcp_routes_tool, arguments)
            return _validate_list(payload, RouteLeg)
        except FastMCPToolError:
            return self._fallback.routes_for_day(request, day, attractions, hotel)

    def weather_for_trip(self, request: TripPlanRequest) -> list[WeatherInfo]:
        arguments = {
            "destination": request.destination,
            "startDate": request.start_date,
            "endDate": request.end_date,
            "days": request.days,
        }
        try:
            payload = self._client.call_tool(self._settings.fastmcp_weather_tool, arguments)
            return _validate_list(payload, WeatherInfo)
        except FastMCPToolError:
            return self._fallback.weather_for_trip(request)

    def estimate_budget(self, request: TripPlanRequest) -> Budget:
        arguments = {
            "destination": request.destination,
            "days": request.days,
            "budget": request.budget,
            "transportation": request.transportation,
            "accommodation": request.accommodation,
        }
        try:
            payload = self._client.call_tool(self._settings.fastmcp_budget_tool, arguments)
            return Budget.model_validate(payload)
        except (FastMCPToolError, ValidationError, TypeError):
            return self._fallback.estimate_budget(request)


class FastMCPToolError(RuntimeError):
    pass


class _FastMCPToolClient:
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.fastmcp_base_url.strip().rstrip("/")
        self._auth_token = settings.fastmcp_auth_token
        self._timeout_seconds = settings.fastmcp_timeout_seconds

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if not self._base_url:
            raise FastMCPToolError("FastMCP base URL is not configured")

        headers = {"Content-Type": "application/json"}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"

        payload = {
            "jsonrpc": "2.0",
            "id": f"travel-agent-cloud:{tool_name}",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }
        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.post(self._base_url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise FastMCPToolError("FastMCP tool call failed") from exc

        if isinstance(data, dict) and data.get("error"):
            raise FastMCPToolError("FastMCP tool returned an error")
        return _extract_tool_result(data)


def create_travel_tool_provider(settings: Settings) -> TravelToolProvider:
    provider = settings.travel_tool_provider.strip().lower()
    if provider in {"", "mock"}:
        return MockTravelToolProvider()
    if provider in {"fastmcp", "mcp"}:
        if settings.fastmcp_base_url.strip():
            return FastMCPTravelToolProvider(settings)
        return MockTravelToolProvider(name="mock:fastmcp_unconfigured")

    # Unknown providers intentionally degrade to mock while keeping the requested
    # name observable in logs/config for future FastMCP-backed implementations.
    return MockTravelToolProvider(name=f"mock:{provider}")


def _extract_tool_result(data: Any) -> Any:
    result = data.get("result") if isinstance(data, dict) else data
    if isinstance(result, dict):
        if "structuredContent" in result:
            return result["structuredContent"]
        if "data" in result:
            return result["data"]
        content = result.get("content")
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict):
                text = first.get("text")
                if isinstance(text, str):
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        return text
        return result
    return result


def _validate_list(value: Any, item_type: type) -> list:
    payload = value.get("items") if isinstance(value, dict) and "items" in value else value
    try:
        return TypeAdapter(list[item_type]).validate_python(payload)
    except (ValidationError, TypeError) as exc:
        raise FastMCPToolError("FastMCP tool returned invalid list payload") from exc


def _hotel_price_range(budget: str) -> str:
    normalized = budget.lower()
    if normalized in {"premium", "luxury", "high"}:
        return "800-1200"
    if normalized in {"low", "economy", "budget"}:
        return "200-350"
    return "400-700"


def _hotel_cost(budget: str) -> int:
    normalized = budget.lower()
    if normalized in {"premium", "luxury", "high"}:
        return 950
    if normalized in {"low", "economy", "budget"}:
        return 280
    return 520


def _route_leg_cost(mode: str, index: int) -> int:
    normalized = mode.lower()
    if normalized in {"walk", "walking", "bike", "bicycle", "cycling", "on foot"}:
        return 0
    if any(keyword in normalized for keyword in ("taxi", "ride", "car")):
        return 25 + index * 10
    return 3 + index * 2


def _destination_key(destination: str) -> str:
    normalized = destination.strip().lower()
    aliases = {
        "成都": "chengdu",
        "chengdu": "chengdu",
        "上海": "shanghai",
        "shanghai": "shanghai",
        "杭州": "hangzhou",
        "hangzhou": "hangzhou",
        "北京": "beijing",
        "beijing": "beijing",
        "西安": "xian",
        "xi'an": "xian",
        "xian": "xian",
        "广州": "guangzhou",
        "guangzhou": "guangzhou",
    }
    return aliases.get(normalized, normalized)


def _landmark_candidates(destination: str) -> tuple[dict[str, object], ...]:
    landmarks: dict[str, tuple[dict[str, object], ...]] = {
        "chengdu": (
            {"name": "宽窄巷子 Kuanzhai Alley", "address": "成都市青羊区长顺街附近", "longitude": 104.0596, "latitude": 30.6699, "category": "historic district", "ticket_price": 0},
            {"name": "人民公园 People's Park", "address": "成都市青羊区少城路12号", "longitude": 104.0633, "latitude": 30.6598, "category": "park", "ticket_price": 0},
            {"name": "武侯祠 Wuhou Shrine", "address": "成都市武侯区武侯祠大街231号", "longitude": 104.0472, "latitude": 30.6424, "category": "heritage", "ticket_price": 50},
            {"name": "锦里古街 Jinli Street", "address": "成都市武侯区武侯祠大街231号附1号", "longitude": 104.0459, "latitude": 30.6417, "category": "food street", "ticket_price": 0},
            {"name": "成都大熊猫繁育研究基地", "address": "成都市成华区熊猫大道1375号", "longitude": 104.1455, "latitude": 30.7387, "category": "wildlife park", "ticket_price": 55},
            {"name": "太古里 Taikoo Li Chengdu", "address": "成都市锦江区中纱帽街8号", "longitude": 104.0807, "latitude": 30.6538, "category": "city walk", "ticket_price": 0},
        ),
        "shanghai": (
            {"name": "外滩 The Bund", "address": "上海市黄浦区中山东一路", "longitude": 121.4906, "latitude": 31.2396, "category": "landmark", "ticket_price": 0},
            {"name": "豫园 Yuyuan Garden", "address": "上海市黄浦区福佑路168号", "longitude": 121.4920, "latitude": 31.2272, "category": "garden", "ticket_price": 40},
            {"name": "上海博物馆", "address": "上海市黄浦区人民大道201号", "longitude": 121.4753, "latitude": 31.2284, "category": "museum", "ticket_price": 0},
            {"name": "陆家嘴 Lujiazui", "address": "上海市浦东新区陆家嘴环路", "longitude": 121.5055, "latitude": 31.2397, "category": "city skyline", "ticket_price": 0},
        ),
        "hangzhou": (
            {"name": "西湖 West Lake", "address": "杭州市西湖区龙井路1号", "longitude": 120.1486, "latitude": 30.2410, "category": "lake", "ticket_price": 0},
            {"name": "灵隐寺 Lingyin Temple", "address": "杭州市西湖区法云弄1号", "longitude": 120.1012, "latitude": 30.2401, "category": "temple", "ticket_price": 75},
            {"name": "河坊街 Hefang Street", "address": "杭州市上城区河坊街", "longitude": 120.1717, "latitude": 30.2440, "category": "historic street", "ticket_price": 0},
            {"name": "中国茶叶博物馆", "address": "杭州市西湖区龙井路88号", "longitude": 120.1190, "latitude": 30.2280, "category": "museum", "ticket_price": 0},
        ),
        "beijing": (
            {"name": "故宫博物院 Forbidden City", "address": "北京市东城区景山前街4号", "longitude": 116.3970, "latitude": 39.9180, "category": "heritage", "ticket_price": 60},
            {"name": "天坛 Temple of Heaven", "address": "北京市东城区天坛东路甲1号", "longitude": 116.4107, "latitude": 39.8822, "category": "heritage park", "ticket_price": 34},
            {"name": "颐和园 Summer Palace", "address": "北京市海淀区新建宫门路19号", "longitude": 116.2755, "latitude": 39.9999, "category": "garden", "ticket_price": 30},
            {"name": "南锣鼓巷", "address": "北京市东城区南锣鼓巷", "longitude": 116.4030, "latitude": 39.9371, "category": "city walk", "ticket_price": 0},
        ),
        "xian": (
            {"name": "秦始皇帝陵博物院 兵马俑", "address": "西安市临潼区秦陵北路", "longitude": 109.2785, "latitude": 34.3841, "category": "heritage", "ticket_price": 120},
            {"name": "西安城墙", "address": "西安市碑林区南大街", "longitude": 108.9432, "latitude": 34.2583, "category": "heritage wall", "ticket_price": 54},
            {"name": "大雁塔", "address": "西安市雁塔区雁塔路", "longitude": 108.9642, "latitude": 34.2183, "category": "heritage", "ticket_price": 40},
            {"name": "回民街", "address": "西安市莲湖区北院门", "longitude": 108.9439, "latitude": 34.2655, "category": "food street", "ticket_price": 0},
        ),
        "guangzhou": (
            {"name": "陈家祠", "address": "广州市荔湾区中山七路恩龙里34号", "longitude": 113.2465, "latitude": 23.1259, "category": "heritage", "ticket_price": 10},
            {"name": "沙面岛 Shamian Island", "address": "广州市荔湾区沙面北街", "longitude": 113.2382, "latitude": 23.1099, "category": "city walk", "ticket_price": 0},
            {"name": "广州塔 Canton Tower", "address": "广州市海珠区阅江西路222号", "longitude": 113.3309, "latitude": 23.1065, "category": "landmark", "ticket_price": 150},
            {"name": "永庆坊", "address": "广州市荔湾区恩宁路", "longitude": 113.2426, "latitude": 23.1175, "category": "historic district", "ticket_price": 0},
        ),
    }
    return landmarks.get(_destination_key(destination), ())


def _local_meal_candidates(destination: str) -> tuple[str, ...]:
    meals = {
        "chengdu": ("担担面", "钟水饺", "钵钵鸡", "川味火锅", "甜水面"),
        "shanghai": ("小笼包", "生煎", "本帮菜", "葱油拌面", "蟹粉面"),
        "hangzhou": ("片儿川", "龙井虾仁", "东坡肉", "知味小笼", "西湖醋鱼"),
        "beijing": ("豆汁焦圈", "炸酱面", "北京烤鸭", "涮羊肉", "卤煮"),
        "xian": ("肉夹馍", "羊肉泡馍", "凉皮", "biangbiang面", "葫芦鸡"),
        "guangzhou": ("早茶点心", "艇仔粥", "烧鹅", "云吞面", "煲仔饭"),
    }
    return meals.get(_destination_key(destination), ())
