import os
from typing import Any, Callable

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


app = FastAPI(title="Travel MCP Tool Server", version="0.1.0")
amap_client = None


class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int | None = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


class ToolDefinition(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any] = Field(alias="inputSchema")


ToolHandler = Callable[[dict[str, Any]], Any]


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "Travel MCP Tool Server",
        "toolCount": len(TOOLS),
        "provider": "amap" if _amap_client().enabled else "amap-stub",
        "amapEnabled": _amap_client().enabled,
    }


@app.post("/mcp")
def mcp(request: JsonRpcRequest) -> dict[str, object]:
    if request.method == "tools/list":
        return _jsonrpc_result(request.id, {"tools": [tool.model_dump(by_alias=True) for tool in TOOL_DEFINITIONS]})
    if request.method != "tools/call":
        return _jsonrpc_error(request.id, -32601, "Method not found")

    tool_name = str(request.params.get("name") or "")
    arguments = request.params.get("arguments")
    if not isinstance(arguments, dict):
        return _jsonrpc_error(request.id, -32602, "Tool arguments must be an object")

    handler = TOOLS.get(tool_name)
    if handler is None:
        return _jsonrpc_error(request.id, -32601, f"Unknown tool: {tool_name}")

    try:
        result = handler(arguments)
    except ValueError as exc:
        return _jsonrpc_error(request.id, -32602, str(exc))

    return _jsonrpc_result(request.id, {"structuredContent": result})


@app.post("/tools/{tool_name}")
def call_tool_direct(tool_name: str, arguments: dict[str, Any]) -> Any:
    handler = TOOLS.get(tool_name)
    if handler is None:
        raise HTTPException(status_code=404, detail={"code": "TOOL_NOT_FOUND", "message": "Unknown tool"})
    return handler(arguments)


def search_attractions(arguments: dict[str, Any]) -> dict[str, object]:
    destination = _required_text(arguments, "destination")
    day = _int_arg(arguments, "day", 1)
    interests = str(arguments.get("interests") or "local culture")
    real_items = _amap_client().search_pois(destination, interests, day)
    if real_items:
        return {"items": real_items}
    return _stub_attractions(destination, day, interests)


def _stub_attractions(destination: str, day: int, interests: str) -> dict[str, object]:
    base_lng = 104.0668
    base_lat = 30.5728
    items = [
        {
            "name": f"{destination} Amap POI {day}-{index}",
            "address": f"{destination} scenic district",
            "location": {
                "longitude": round(base_lng + day * 0.01 + index * 0.004, 6),
                "latitude": round(base_lat + day * 0.008 + index * 0.003, 6),
            },
            "visitDuration": 90 + index * 30,
            "description": f"Stub attraction matched to {interests}. Replace with Amap POI search later.",
            "category": "attraction",
            "rating": 4.4 + index * 0.1,
            "imageUrl": None,
            "ticketPrice": 30 + index * 25,
        }
        for index in range(1, 3)
    ]
    return {"items": items}


def search_hotel(arguments: dict[str, Any]) -> dict[str, object]:
    destination = _required_text(arguments, "destination")
    day = _int_arg(arguments, "day", 1)
    accommodation = str(arguments.get("accommodation") or "comfortable hotel")
    budget = str(arguments.get("budget") or "moderate")
    return {
        "name": f"{destination} {accommodation} MCP stay {day}",
        "address": f"{destination} transit hub area",
        "location": {"longitude": 104.0668 + day * 0.006, "latitude": 30.5728 + day * 0.006},
        "priceRange": _hotel_price_range(budget),
        "rating": "4.5",
        "distance": "Near the planned route",
        "type": accommodation,
        "estimatedCost": _hotel_cost(budget),
    }


def search_meals(arguments: dict[str, Any]) -> dict[str, object]:
    destination = _required_text(arguments, "destination")
    day = _int_arg(arguments, "day", 1)
    interests = str(arguments.get("interests") or "local food")
    items = [
        {
            "type": meal_type,
            "name": f"{destination} {meal_type} MCP option {day}",
            "address": f"{destination} food street",
            "description": f"Stub {meal_type} option matched to {interests}.",
            "estimatedCost": cost,
        }
        for meal_type, cost in {"breakfast": 25, "lunch": 55, "dinner": 90}.items()
    ]
    return {"items": items}


def plan_routes(arguments: dict[str, Any]) -> dict[str, object]:
    destination = _required_text(arguments, "destination")
    day = _int_arg(arguments, "day", 1)
    mode = str(arguments.get("transportation") or "mixed transit")
    hotel = arguments.get("hotel")
    hotel_name = hotel.get("name") if isinstance(hotel, dict) and hotel.get("name") else f"{destination} hotel area"
    attractions = arguments.get("attractions")
    if not isinstance(attractions, list):
        attractions = []
    stop_names = [str(item.get("name")) for item in attractions if isinstance(item, dict) and item.get("name")]
    if not stop_names:
        stop_names = [f"{destination} route stop"]

    real_items = _amap_client().plan_routes(mode, hotel, attractions)
    if real_items:
        return {"items": real_items}

    stops = [hotel_name, *stop_names, hotel_name]
    items = [
        {
            "fromName": stops[index],
            "toName": stops[index + 1],
            "mode": mode,
            "distanceMeters": 1800 + day * 250 + index * 650,
            "durationMinutes": 18 + day * 2 + index * 8,
            "estimatedCost": _route_leg_cost(mode, index),
            "instruction": f"Stub route from {stops[index]} to {stops[index + 1]}; replace with Amap route planning.",
        }
        for index in range(len(stops) - 1)
    ]
    return {"items": items}


def get_weather(arguments: dict[str, Any]) -> dict[str, object]:
    destination = _required_text(arguments, "destination")
    days = _int_arg(arguments, "days", 1)
    start_date = str(arguments.get("startDate") or "")
    real_items = _amap_client().weather(destination, days, start_date)
    if real_items:
        return {"items": real_items}
    items = [
        {
            "date": start_date if index == 1 and start_date else f"Day {index}",
            "dayWeather": "Cloudy",
            "nightWeather": "Clear",
            "dayTemp": 24 + (index % 4),
            "nightTemp": 16 + (index % 3),
            "windDirection": "East",
            "windPower": "1-3",
        }
        for index in range(1, min(days, 30) + 1)
    ]
    return {"items": items}


def estimate_budget(arguments: dict[str, Any]) -> dict[str, object]:
    days = _int_arg(arguments, "days", 1)
    budget = str(arguments.get("budget") or "moderate")
    hotel_total = days * _hotel_cost(budget)
    attraction_total = days * 85
    meal_total = days * 170
    transportation_total = days * 45
    return {
        "totalAttractions": attraction_total,
        "totalHotels": hotel_total,
        "totalMeals": meal_total,
        "totalTransportation": transportation_total,
        "total": attraction_total + hotel_total + meal_total + transportation_total,
    }


TOOLS: dict[str, ToolHandler] = {
    "travel.search_attractions": search_attractions,
    "travel.search_hotel": search_hotel,
    "travel.search_meals": search_meals,
    "travel.plan_routes": plan_routes,
    "travel.get_weather": get_weather,
    "travel.estimate_budget": estimate_budget,
}


TOOL_DEFINITIONS = [
    ToolDefinition(name=name, description=description, inputSchema={"type": "object"})
    for name, description in (
        ("travel.search_attractions", "Search destination attractions for one itinerary day."),
        ("travel.search_hotel", "Find one hotel candidate for one itinerary day."),
        ("travel.search_meals", "Find meal suggestions for one itinerary day."),
        ("travel.plan_routes", "Plan route legs between hotel and attractions."),
        ("travel.get_weather", "Fetch weather forecasts for the trip window."),
        ("travel.estimate_budget", "Estimate trip cost categories."),
    )
]


def _jsonrpc_result(request_id: str | int | None, result: object) -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _jsonrpc_error(request_id: str | int | None, code: int, message: str) -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _required_text(arguments: dict[str, Any], field: str) -> str:
    value = str(arguments.get(field) or "").strip()
    if not value:
        raise ValueError(f"{field} is required")
    return value


def _int_arg(arguments: dict[str, Any], field: str, default: int) -> int:
    try:
        return max(1, int(arguments.get(field) or default))
    except (TypeError, ValueError):
        return default


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


def _amap_client() -> "AmapWebServiceClient":
    global amap_client
    if amap_client is None:
        amap_client = AmapWebServiceClient(
            key=os.getenv("AMAP_WEB_SERVICE_KEY", ""),
            base_url=os.getenv("AMAP_BASE_URL", "https://restapi.amap.com").rstrip("/"),
            timeout_seconds=float(os.getenv("AMAP_TIMEOUT_SECONDS", "8")),
        )
    return amap_client


class AmapWebServiceClient:
    def __init__(self, key: str, base_url: str, timeout_seconds: float) -> None:
        self._key = key.strip()
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds

    @property
    def enabled(self) -> bool:
        return bool(self._key)

    def search_pois(self, destination: str, interests: str, day: int) -> list[dict[str, object]]:
        if not self.enabled:
            return []
        keywords = _poi_keywords(destination, interests)
        payload = self._get(
            "/v3/place/text",
            {
                "keywords": keywords,
                "city": destination,
                "citylimit": "true",
                "offset": 8,
                "page": max(1, day),
                "extensions": "all",
            },
        )
        pois = payload.get("pois") if isinstance(payload, dict) else None
        if not isinstance(pois, list):
            return []

        items: list[dict[str, object]] = []
        for index, poi in enumerate(pois[:4], start=1):
            if not isinstance(poi, dict):
                continue
            name = str(poi.get("name") or "").strip()
            if not name:
                continue
            location = _parse_location(str(poi.get("location") or ""))
            biz_ext = poi.get("biz_ext") if isinstance(poi.get("biz_ext"), dict) else {}
            photos = poi.get("photos") if isinstance(poi.get("photos"), list) else []
            image_url = next(
                (
                    _safe_text(photo.get("url"))
                    for photo in photos
                    if isinstance(photo, dict) and _safe_text(photo.get("url"))
                ),
                "",
            )
            rating = _optional_float(biz_ext.get("rating") if isinstance(biz_ext, dict) else None)
            cost = _optional_int(biz_ext.get("cost") if isinstance(biz_ext, dict) else None)
            items.append(
                {
                    "name": name,
                    "address": _safe_text(poi.get("address")),
                    "location": location,
                    "visitDuration": 90 + index * 15,
                    "description": f"Amap POI result for {destination}; type={_safe_text(poi.get('type')) or 'attraction'}.",
                    "category": _safe_text(poi.get("type")) or "attraction",
                    "rating": rating,
                    "imageUrl": image_url or None,
                    "ticketPrice": cost or 0,
                }
            )
        return items

    def weather(self, destination: str, days: int, start_date: str) -> list[dict[str, object]]:
        if not self.enabled:
            return []
        adcode = self._adcode_for_destination(destination)
        if not adcode:
            return []
        payload = self._get("/v3/weather/weatherInfo", {"city": adcode, "extensions": "all"})
        forecasts = payload.get("forecasts") if isinstance(payload, dict) else None
        if not isinstance(forecasts, list) or not forecasts:
            return []
        casts = forecasts[0].get("casts") if isinstance(forecasts[0], dict) else None
        if not isinstance(casts, list):
            return []

        items: list[dict[str, object]] = []
        for index, cast in enumerate(casts[: min(days, 4)], start=1):
            if not isinstance(cast, dict):
                continue
            items.append(
                {
                    "date": _safe_text(cast.get("date")) or (start_date if index == 1 and start_date else f"Day {index}"),
                    "dayWeather": _safe_text(cast.get("dayweather")),
                    "nightWeather": _safe_text(cast.get("nightweather")),
                    "dayTemp": _optional_int(cast.get("daytemp")) or 0,
                    "nightTemp": _optional_int(cast.get("nighttemp")) or 0,
                    "windDirection": _safe_text(cast.get("daywind")),
                    "windPower": _safe_text(cast.get("daypower")),
                }
            )
        return items

    def plan_routes(self, mode: str, hotel: Any, attractions: Any) -> list[dict[str, object]]:
        if not self.enabled:
            return []
        stops = _route_stops(hotel, attractions)
        if len(stops) < 2:
            return []

        items: list[dict[str, object]] = []
        for index in range(len(stops) - 1):
            origin = stops[index]
            destination = stops[index + 1]
            route = self._route_leg(mode, origin, destination)
            if route is None:
                return []
            items.append(
                {
                    "fromName": origin["name"],
                    "toName": destination["name"],
                    "mode": mode,
                    "distanceMeters": route["distanceMeters"],
                    "durationMinutes": route["durationMinutes"],
                    "estimatedCost": _route_leg_cost(mode, index),
                    "instruction": route["instruction"],
                }
            )
        return items

    def _route_leg(self, mode: str, origin: dict[str, Any], destination: dict[str, Any]) -> dict[str, object] | None:
        normalized = mode.lower()
        endpoint = "/v3/direction/driving" if any(item in normalized for item in ("car", "taxi", "ride", "drive")) else "/v3/direction/walking"
        payload = self._get(
            endpoint,
            {
                "origin": f"{origin['longitude']},{origin['latitude']}",
                "destination": f"{destination['longitude']},{destination['latitude']}",
                "extensions": "base",
            },
        )
        route = payload.get("route") if isinstance(payload, dict) else None
        paths = route.get("paths") if isinstance(route, dict) else None
        if not isinstance(paths, list) or not paths:
            return None
        path = paths[0] if isinstance(paths[0], dict) else {}
        steps = path.get("steps") if isinstance(path, dict) else None
        instruction = ""
        if isinstance(steps, list) and steps and isinstance(steps[0], dict):
            instruction = _safe_text(steps[0].get("instruction"))
        return {
            "distanceMeters": _optional_int(path.get("distance")) or 0,
            "durationMinutes": round((_optional_int(path.get("duration")) or 0) / 60),
            "instruction": instruction or f"Amap route from {origin['name']} to {destination['name']}.",
        }

    def _adcode_for_destination(self, destination: str) -> str:
        payload = self._get("/v3/geocode/geo", {"address": destination})
        geocodes = payload.get("geocodes") if isinstance(payload, dict) else None
        if isinstance(geocodes, list) and geocodes and isinstance(geocodes[0], dict):
            return _safe_text(geocodes[0].get("adcode"))
        return ""

    def _get(self, path: str, params: dict[str, object]) -> dict[str, Any]:
        if not self.enabled:
            return {}
        request_params = {"key": self._key, "output": "JSON", **params}
        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.get(f"{self._base_url}{path}", params=request_params)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError):
            return {}
        if not isinstance(payload, dict) or str(payload.get("status")) != "1":
            return {}
        return payload


def _poi_keywords(destination: str, interests: str) -> str:
    terms = [item.strip() for item in interests.replace("，", ",").split(",") if item.strip()]
    if not terms:
        return f"{destination} 景点"
    return f"{destination} {terms[0]}"


def _route_stops(hotel: Any, attractions: Any) -> list[dict[str, Any]]:
    stops: list[dict[str, Any]] = []
    hotel_stop = _place_stop(hotel, "Hotel")
    if hotel_stop:
        stops.append(hotel_stop)
    if isinstance(attractions, list):
        for attraction in attractions:
            stop = _place_stop(attraction, "Attraction")
            if stop:
                stops.append(stop)
    if hotel_stop and len(stops) > 1:
        stops.append(hotel_stop)
    return stops


def _place_stop(value: Any, fallback_name: str) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    location = value.get("location")
    if not isinstance(location, dict):
        return None
    longitude = _optional_float(location.get("longitude"))
    latitude = _optional_float(location.get("latitude"))
    if longitude is None or latitude is None:
        return None
    return {
        "name": _safe_text(value.get("name")) or fallback_name,
        "longitude": longitude,
        "latitude": latitude,
    }


def _parse_location(value: str) -> dict[str, float] | None:
    try:
        longitude, latitude = value.split(",", 1)
        return {"longitude": float(longitude), "latitude": float(latitude)}
    except (ValueError, TypeError):
        return None


def _safe_text(value: Any) -> str:
    if value is None or isinstance(value, list | dict):
        return ""
    return str(value).strip()


def _optional_int(value: Any) -> int | None:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None
