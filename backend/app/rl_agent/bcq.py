from __future__ import annotations


class BCQDatasetError(RuntimeError):
    pass


def require_logged_actions(columns) -> None:
    cols = {str(c) for c in columns}
    if not cols.intersection({"Action", "action", "AgentAction", "agent_action"}):
        raise BCQDatasetError(
            "BCQ requires logged behavior actions so the learned policy can be "
            "constrain decisions to actions supported by the offline batch. "
            "The current SOC dataset has no historical agent-action column."
        )
