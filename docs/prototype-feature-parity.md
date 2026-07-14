# Prototype Feature Parity

Source prototype:

`Hello-Agents/hello-agents-main/code/chapter13/helloagents-trip-planner`

This project should first preserve the prototype's user-facing travel planning capabilities, then evolve them into the cloud-native product.

## Prototype Capabilities To Preserve

| Area | Prototype behavior | Travel Agent Cloud status |
| --- | --- | --- |
| Trip input | Destination city, start date, end date, auto-calculated travel days | Supported with destination, dates, days, transport, stay, interests, free text |
| Preferences | Transport preference, accommodation preference, travel style tags, extra requirements | Supported with transport, accommodation, interests, profile preferences, free text |
| Planning progress | Step-style progress text while generating: attractions, weather, hotels, itinerary | Partially supported with loading states; detailed node progress should come from agent trace events |
| Agent planning | Multi-agent flow: attraction search, weather query, hotel search, final planner | Partially supported through graph nodes and travel tools; real LangGraph/tool orchestration is in progress |
| Map tools | Amap MCP tools for POI, weather, walking/driving/transit routes | FastMCP travel tool server is wired with Amap support and deterministic fallback data |
| Result overview | Overview, date range, suggestions, budget | Supported |
| Budget | Attraction, hotel, meal, transportation, total cost | Supported |
| Daily itinerary | Per-day description, transport, accommodation, attractions, hotel, meals, routes | Supported with mock route summaries |
| Attraction details | Name, address, duration, description, rating, ticket price, image | Mostly supported; image rendering still needs parity work |
| Hotel details | Name, address, type, price range, rating, distance | Supported |
| Weather | Day/night weather, temperatures, wind | Supported |
| Map view | Map markers and route polylines for attractions | Per-day AMap SDK preview is supported when frontend map keys are configured; schematic fallback remains available |
| Editing | Edit itinerary, move/delete attractions, save/cancel changes | Supported for trip/day fields, hotels, attractions, meals, weather, and route segments |
| Export | Export result as image and PDF | Markdown export supported; image/PDF export parity pending |

## Recommended Implementation Order

1. Make the LangGraph engine a real workflow runner behind the existing API.
2. Stabilize the travel tool interface around POI, hotel, meal, weather, route, and budget calls. Initial route contracts are now in place.
3. Add prototype-compatible image/PDF export after map rendering is stable.
4. Add image rendering for attraction details after a stable asset provider is selected.

## Non-Goals For Direct Copy

- Do not copy the prototype's sessionStorage-only persistence model; Travel Agent Cloud uses authenticated users and PostgreSQL.
- Do not expose raw tool call payloads to the frontend; keep traces privacy-safe.
- Do not couple the public API to Amap names. Keep provider-specific names inside the tool provider layer.
