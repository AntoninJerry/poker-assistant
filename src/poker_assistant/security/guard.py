"""Security and compliance guardrails.

Ensures the assistant operates in read-only mode and does not automate
interactions with poker clients, per gaming compliance requirements.
"""

from dataclasses import dataclass


class SecurityViolationError(RuntimeError):
    """Raised when a security policy is violated."""


@dataclass
class SecurityGuard:
    """Static security checks."""

    @staticmethod
    def ensure_compliance() -> None:
        """Run startup compliance checks.

        Currently a placeholder for future system inspections.
        """

        # Explicitly assert our policy in logs or telemetry in the future.
        # No-op for now.
        return
