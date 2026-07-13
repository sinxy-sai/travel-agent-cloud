from app.agent_engines.basic import BasicTravelAgentEngine
from app.agent_engines.types import TravelAgentEngine
from app.settings import Settings
from app.travel_tools import TravelToolProvider


def create_travel_agent_engine(settings: Settings, travel_tools: TravelToolProvider) -> TravelAgentEngine:
    engine = settings.agent_engine.strip().lower()
    if engine in {"", "basic"}:
        return BasicTravelAgentEngine(settings, travel_tools)

    return BasicTravelAgentEngine(settings, travel_tools, name=f"basic:{engine}")
