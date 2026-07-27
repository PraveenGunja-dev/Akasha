"""LangGraph execution path for authenticated Akasha conversations."""

__all__ = ["chat_graph_service", "select_chat_engine"]


def __getattr__(name: str):
    if name in __all__:
        from engine.graph.service import chat_graph_service, select_chat_engine

        return {
            "chat_graph_service": chat_graph_service,
            "select_chat_engine": select_chat_engine,
        }[name]
    raise AttributeError(name)
