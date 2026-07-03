"""
LangGraph multi-agent orchestration graph.

Flow
----
START
  └─► supervisor_analyze   (picks which agents to run, in order)
        └─► [conditional] ─► first pending agent   ─┐
                                                      │ (loop back via conditional)
                          ◄────────────────────────────┘
        └─► [all done]   ─► supervisor_synthesize
                                  └─► END

Adding a new agent: drop a file in agents/, no graph changes needed.
"""
from __future__ import annotations

from typing import Dict

from langgraph.graph import END, StateGraph

from agents.supervisor import SupervisorAgent
from graphs.state import AgentState
from utils.logger import setup_logger

logger = setup_logger(__name__)


# ── routing function ────────────────────────────────────────────────────────

def _next_node(state: AgentState) -> str:
    """
    After every node, decide what runs next.

    • Walk agents_to_run in order.
    • Return the name of the first agent not yet in agent_outputs.
    • If all are done, return 'supervisor_synthesize'.
    """
    for name in state.get("agents_to_run", []):
        if name not in state.get("agent_outputs", {}):
            return name
    return "supervisor_synthesize"


# ── graph builder ───────────────────────────────────────────────────────────

def build_graph(agents: Dict) -> object:
    """
    Assemble and compile the LangGraph state machine.

    Args:
        agents: dict[name → BaseAgent instance]  produced by agent_loader.

    Returns:
        Compiled LangGraph (call .invoke(state) to run it).
    """
    logger.info("🔨 Building multi-agent graph …")

    supervisor = SupervisorAgent(available_agents=agents)

    graph = StateGraph(AgentState)

    # ── nodes ────────────────────────────────────────────────────────────────
    graph.add_node("supervisor_analyze", supervisor.analyze)
    graph.add_node("supervisor_synthesize", supervisor.synthesize)

    for name, agent in agents.items():
        graph.add_node(name, agent.run_node)
        logger.debug(f"  node added: {name}")

    # ── path map for conditional routing ─────────────────────────────────────
    # Maps the string returned by _next_node → actual node name in the graph.
    path_map: dict[str, str] = {name: name for name in agents}
    path_map["supervisor_synthesize"] = "supervisor_synthesize"

    # ── edges ────────────────────────────────────────────────────────────────
    graph.set_entry_point("supervisor_analyze")

    # After supervisor_analyze → first agent (or straight to synthesis)
    graph.add_conditional_edges("supervisor_analyze", _next_node, path_map)

    # After each agent → next pending agent (or synthesis)
    for name in agents:
        graph.add_conditional_edges(name, _next_node, path_map)

    # Synthesis → done
    graph.add_edge("supervisor_synthesize", END)

    compiled = graph.compile()
    logger.info(
        f"✅ Graph ready. Agents: {list(agents.keys())}"
    )
    return compiled
