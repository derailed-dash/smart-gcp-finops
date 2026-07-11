# Expose the custom `agent_runtime` application instance from `agent_runtime_app`
# as the package's default `app` entrypoint.
# Why: When `google-agents-cli` launches the API server inside the container,
# the `AgentLoader` imports this module to resolve the `app` instance. Exposing
# `agent_runtime` here ensures our custom subclass (which overrides routing/logging)
# is used instead of the raw, unconfigured `agent.app`.
from .agent_runtime_app import agent_runtime as app

__all__ = ["app"]
