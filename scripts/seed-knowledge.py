from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent-runtime"))

from dotenv import load_dotenv  # noqa: E402


def _disable_compose_database_url_for_local_windows() -> None:
    database_url = os.getenv("DATABASE_URL", "")
    if platform.system().lower() == "windows" and "@postgres:" in database_url:
        os.environ["DATABASE_URL"] = ""


load_dotenv(ROOT / "agent-runtime" / ".env")
_disable_compose_database_url_for_local_windows()

from app.knowledge import create_knowledge_retriever  # noqa: E402
from app.settings import Settings  # noqa: E402


DEFAULT_DESTINATIONS = ("Chengdu", "Shanghai", "Hangzhou", "Beijing", "Xi'an", "Guangzhou")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Travel Agent runtime RAG knowledge records.")
    parser.add_argument("--database-url", help="Optional runtime RAG database URL override.")
    parser.add_argument("destinations", nargs="*", default=list(DEFAULT_DESTINATIONS))
    args = parser.parse_args()
    if args.database_url:
        os.environ["DATABASE_URL"] = args.database_url

    retriever = create_knowledge_retriever(Settings())
    result = {
        "backend": retriever.backend,
        "destinations": [],
    }
    for destination in args.destinations:
        inserted = retriever.seed_destination_knowledge(destination)
        result["destinations"].append({"destination": destination, "inserted": inserted})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if retriever.backend == "postgres" else 1


if __name__ == "__main__":
    raise SystemExit(main())
