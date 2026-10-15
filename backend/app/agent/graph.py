from langgraph.graph import END, START, StateGraph
from app.agent import nodes
from app.agent.state import AgentState


def build_graph():
    g = StateGraph(AgentState)
    for name, fn in [("guard", nodes.guard), ("pending", nodes.pending), ("classify", nodes.classify),
                     ("policy", nodes.policy), ("availability", nodes.availability_node), ("book", nodes.book),
                     ("cancel", nodes.cancel), ("list", nodes.list_node), ("other", nodes.other),
                     ("handoff", nodes.handoff), ("check", lambda state: {})]:
        g.add_node(name, fn)
    g.add_edge(START, "guard")
    g.add_conditional_edges("guard", nodes.route_guard, {"handoff": "handoff", "done": END, "pending": "pending"})
    g.add_conditional_edges("pending", nodes.route_pending, {"done": END, "classify": "classify"})
    g.add_conditional_edges("classify", nodes.route_intent, {
        "policy": "policy", "availability": "availability", "book": "book", "cancel": "cancel",
        "list": "list", "handoff": "handoff", "other": "other", "after": "check"})
    for n in ("policy", "availability", "book", "cancel", "list", "check"):
        g.add_conditional_edges(n, nodes.after, {"handoff": "handoff", "done": END})
    g.add_edge("other", END)
    g.add_edge("handoff", END)
    return g.compile()


GRAPH = build_graph()
