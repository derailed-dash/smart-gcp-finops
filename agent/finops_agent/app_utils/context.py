"""Request-local context variable definitions for security and project scoping.

What:
    Defines context variables (such as ``ALLOWED_PROJECTS_VAR``) used to store and propagate user-specific
    access control boundaries across asynchronous and thread boundaries.

Why:
    Ensures that background tasks, agent tool executions, and BigQuery/CAI queries strictly enforce
    the active user's authorization boundaries without passing context explicitly through every function call.

How:
    Utilizes Python's standard library ``contextvars`` module to maintain isolated, thread-safe state per
    request execution context.
"""

import contextvars

# Context variable containing a set of allowed project IDs for the active user
ALLOWED_PROJECTS_VAR: contextvars.ContextVar[set[str] | None] = contextvars.ContextVar(
    "allowed_projects", default=None
)
