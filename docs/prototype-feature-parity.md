# Prototype Feature Parity

Source prototype:

`Hello-Agents/hello-agents-main/code/chapter13/helloagents-trip-planner`

This project should first preserve the prototype's user-facing travel planning capabilities, then evolve them into the cloud-native product.

## Migration Shape

The prototype is a two-layer app: Vue frontend plus a FastAPI backend centered on a `MultiAgentTripPlanner`. Its main behavior is:

1. attraction agent calls AMap text search;
2. weather agent calls AMap weather;
3. hotel agent calls AMap text search;
4. planner agent merges those tool results into a structured itinerary JSON.

Travel Agent Cloud keeps the same user-facing behavior, but maps it onto a deployable architecture:

| Prototype concept | Travel Agent Cloud equivalent |
| --- | --- |
| `SimpleAgent` attraction/weather/hotel/planner agents | LangGraph nodes: `attraction_agent`, `weather_agent`, `hotel_agent`, `meal_agent`, `route_agent`, `budget_agent`, `planner_agent` |
| `MCPTool` wrapping `amap-mcp-server` | `services/travel-mcp` FastMCP-compatible tool service |
| Text tool output merged by planner prompt | Structured tool payloads merged by `agent-runtime`, with optional LangChain tool-calling inside nodes |
| In-memory/session frontend state | PostgreSQL-backed conversations, trip plans, versions, exports, jobs, and user accounts |
| Single backend process | Full-stack deployable services: frontend, agent-runtime, worker, Postgres, Redis, RabbitMQ, object storage, travel-mcp |

This means we should copy the prototype's product behavior and prompts where useful, but not copy the `helloagent` framework or its persistence model. Provider-specific AMap details stay inside `services/travel-mcp`; orchestration and product records stay inside `agent-runtime`.

## Prototype Capabilities To Preserve

| Area | Prototype behavior | Travel Agent Cloud status |
| --- | --- | --- |
| Trip input | Destination city, start date, end date, auto-calculated travel days | Supported with destination, dates, days, transport, stay, interests, free text |
| Preferences | Transport preference, accommodation preference, travel style tags, extra requirements | Supported with transport, accommodation, interests, profile preferences, free text |
| Planning progress | Step-style progress text while generating: attractions, weather, hotels, itinerary | Supported with backend trip-plan jobs, SSE progress streaming, and polling fallback |
| Agent planning | Multi-agent flow: attraction search, weather query, hotel search, final planner | Supported through LangGraph workflow nodes and FastMCP travel tools, with deterministic fallback data when tools fail |
| Map tools | Amap MCP tools for POI, weather, walking/driving/transit routes | FastMCP travel tool server is wired with Amap support and deterministic fallback data |
| Result overview | Overview, date range, suggestions, budget | Supported |
| Budget | Attraction, hotel, meal, transportation, total cost | Supported |
| Daily itinerary | Per-day description, transport, accommodation, attractions, hotel, meals, routes | Supported with section-level data source badges for attractions, hotels/meals, and routes |
| Attraction details | Name, address, duration, description, rating, ticket price, image | Supported; AMap POI photos render when available, with stable placeholders and export-safe fallback |
| Hotel details | Name, address, type, price range, rating, distance | Supported |
| Weather | Day/night weather, temperatures, wind | Supported |
| Map view | Map markers and route polylines for attractions | Supported with All days and per-day modes; AMap SDK preview is used when frontend map keys and coordinates are available, with schematic fallback |
| Editing | Edit itinerary, move/delete attractions, save/cancel changes | Supported for trip/day fields, hotels, attractions, meals, weather, and route segments |
| Export | Export result as image and PDF | Supported for Markdown, PNG, and PDF; media export uses the schematic map and export-safe image placeholders to avoid third-party canvas/CORS failures |

## Recommended Implementation Order

1. Expand data-source transparency from section-level badges into targeted retry actions for individual failed data sources.
2. Browser-verify SSE progress updates through Docker Compose, local Vite proxying, and production ingress.
3. Browser-verify PNG/PDF export across long itineraries, Chinese text, AMap-enabled runs, fallback-map runs, and remote POI photos.
4. Continue improving FastMCP tool coverage for POI, hotel, meal, weather, route, and budget calls while keeping provider-specific details inside the tool layer.
5. Move more planner-agent prompt behavior from the prototype into the LangGraph `planner_agent`, while keeping typed request/response contracts stable.

## Non-Goals For Direct Copy

- Do not copy the prototype's sessionStorage-only persistence model; Travel Agent Cloud uses authenticated users and PostgreSQL.
- Do not expose raw tool call payloads to the frontend; keep traces privacy-safe.
- Do not couple the public API to Amap names. Keep provider-specific names inside the tool provider layer.
