from __future__ import annotations


class IQLDatasetError(RuntimeError):
    pass


def require_logged_actions(columns) -> None:
    cols = {str(c) for c in columns}
    if not cols.intersection({"Action", "action", "AgentAction", "agent_action"}):
        raise IQLDatasetError(
            "IQL requires a logged behavior-action column. "
            "The current SOC dataset contains IncidentGrade/reward information "
            "but no historical agent action, so IQL cannot be trained faithfully "
            "without fabricating behavior data."
        )
