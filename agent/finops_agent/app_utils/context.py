"""
Description: Request-local context variables for request scoping.
Why: Allows background threads and tool executions to access user access boundaries thread-safely.
How: Uses the standard library `contextvars` module.
"""

import contextvars

# Context variable containing a set of allowed project IDs for the active user
ALLOWED_PROJECTS_VAR: contextvars.ContextVar[set[str] | None] = contextvars.ContextVar(
    "allowed_projects", default=None
)
