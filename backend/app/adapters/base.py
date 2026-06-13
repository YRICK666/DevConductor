"""Vendor-neutral agent adapter interface."""

from typing import Protocol

from backend.app.schemas.agent import AgentExecutionRequest, AgentExecutionResult


class AgentAdapter(Protocol):
    """Common interface implemented by concrete coding-agent adapters."""

    @property
    def name(self) -> str:
        """Stable adapter name."""

    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        """Run the agent in an already prepared workspace."""
