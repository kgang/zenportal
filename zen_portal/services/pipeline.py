"""Pipeline protocol for composable multi-step operations."""

from typing import Protocol, TypeVar, Generic
from dataclasses import dataclass

T = TypeVar('T')
U = TypeVar('U')


class Step(Protocol[T, U]):
    """A single pipeline step: T → U."""

    def invoke(self, input: T) -> "StepResult[U]":
        """Execute this step."""
        ...


@dataclass
class StepResult(Generic[T]):
    """Result from a step, with optional early exit."""

    value: T | None
    ok: bool = True
    error: str | None = None

    @classmethod
    def success(cls, value: T) -> "StepResult[T]":
        """Create a successful result."""
        return cls(value=value, ok=True)

    @classmethod
    def fail(cls, error: str) -> "StepResult[T]":
        """Create a failed result."""
        return cls(value=None, ok=False, error=error)


def run_pipeline(steps: list[Step], initial: T) -> StepResult:
    """Run a pipeline of steps sequentially.

    Args:
        steps: List of steps to execute
        initial: Initial input value

    Returns:
        Final StepResult (success with last value, or first failure)
    """
    current = initial
    for step in steps:
        result = step.invoke(current)
        if not result.ok:
            return result
        current = result.value
    return StepResult.success(current)
