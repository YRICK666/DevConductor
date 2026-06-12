"""Shared Pydantic configuration for external contracts."""

from pydantic import BaseModel, ConfigDict


class ContractModel(BaseModel):
    """Base model for contracts with no domain behavior."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )
