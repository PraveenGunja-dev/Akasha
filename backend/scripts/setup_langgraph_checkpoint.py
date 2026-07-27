"""Provision LangGraph's PostgreSQL checkpoint schema as a deployment step."""

import os
import re

from dotenv import load_dotenv
from langgraph.checkpoint.postgres import PostgresSaver


load_dotenv(override=False)


def checkpoint_dsn() -> str:
    dsn = os.getenv("AKASHA_LANGGRAPH_CHECKPOINT_DSN") or os.getenv("DATABASE_URL")
    if not dsn or not dsn.startswith(("postgres://", "postgresql://", "postgresql+")):
        raise RuntimeError("A PostgreSQL checkpoint DSN is required.")
    dsn = dsn.replace("postgres://", "postgresql://", 1)
    return re.sub(r"^postgresql\+[^:]+://", "postgresql://", dsn)


if __name__ == "__main__":
    with PostgresSaver.from_conn_string(checkpoint_dsn()) as saver:
        saver.setup()
    print("LangGraph checkpoint schema is ready.")
