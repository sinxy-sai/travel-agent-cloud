from typing import Any, Callable

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


app = FastAPI(title="Travel MCP Tool Server", version="0.1.0")


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
        "provider": "amap-stub",
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
    _required_text(arguments, "destination")
    days = _int_arg(arguments, "days", 1)
    start_date = str(arguments.get("startDate") or "")
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
