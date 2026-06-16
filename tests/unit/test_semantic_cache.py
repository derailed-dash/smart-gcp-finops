"""
Description: Unit tests for the GenAI Semantic Caching engine.
Why: Ensures high reliability, semantic accuracy, and thread-safe caching operations.
How: Uses `pytest` and mocks the Google GenAI client to verify hit/miss and saving workflows.
"""

import time
from unittest.mock import MagicMock, patch

import pytest
from google.adk.agents.callback_context import CallbackContext
from google.adk.events.event import Event
from google.genai.types import Content, Part

from app.agent import (
    _AGENT_QUERY_CACHE,
    after_agent_save_cache,
    before_agent_cache_lookup,
)


@pytest.fixture(autouse=True)
def clean_cache():
    """Ensure the agent query cache is clean before and after each test."""
    _AGENT_QUERY_CACHE.clear()
    yield
    _AGENT_QUERY_CACHE.clear()


@pytest.mark.asyncio
async def test_semantic_cache_hit():
    """Verify that a semantically equivalent query triggers a cache hit and bypass."""
    # 1. Populating the cache with a record
    _AGENT_QUERY_CACHE["what is the billing trend?"] = (
        time.time() + 300,
        "Cached response text",
    )

    # 2. Creating a mock callback context with a semantically similar query in event history
    mock_event = MagicMock(spec=Event)
    mock_event.role = "user"
    mock_event.content = Content(
        role="user", parts=[Part(text="tell me the billing trend")]
    )

    mock_session = MagicMock()
    mock_session.events = [mock_event]

    ctx = MagicMock(spec=CallbackContext)
    ctx.session = mock_session
    ctx.state = {}

    # 3. Mocking GenAI Client's response to return "what is the billing trend?" as semantic match
    mock_response = MagicMock()
    mock_response.text = "what is the billing trend?"

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("app.agent.genai_client", mock_client):
        await before_agent_cache_lookup(ctx)

        mock_client.models.generate_content.assert_called_once()

        # Verify that state holds the cached response text
        assert ctx.state.get("cached_agent_response") == "Cached response text"


@pytest.mark.asyncio
async def test_semantic_cache_miss():
    """Verify that a cache miss does not populate bypassed state."""
    _AGENT_QUERY_CACHE["what is the billing trend?"] = (
        time.time() + 300,
        "Cached response text",
    )

    mock_event = MagicMock(spec=Event)
    mock_event.role = "user"
    mock_event.content = Content(role="user", parts=[Part(text="show me zombie disks")])

    mock_session = MagicMock()
    mock_session.events = [mock_event]

    ctx = MagicMock(spec=CallbackContext)
    ctx.session = mock_session
    ctx.state = {}

    # Mocking GenAI Client's response to return "NONE" (no semantic match)
    mock_response = MagicMock()
    mock_response.text = "NONE"

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("app.agent.genai_client", mock_client):
        await before_agent_cache_lookup(ctx)

        assert "cached_agent_response" not in ctx.state


@pytest.mark.asyncio
async def test_after_agent_save_cache():
    """Verify that a successful turn saves its user query and model text to cache."""
    # Mock user query event
    mock_user_event = MagicMock(spec=Event)
    mock_user_event.role = "user"
    mock_user_event.content = Content(role="user", parts=[Part(text="test query")])

    # Mock model response event
    mock_model_event = MagicMock(spec=Event)
    mock_model_event.role = "model"
    mock_model_event.content = Content(role="model", parts=[Part(text="test response")])

    mock_session = MagicMock()
    mock_session.events = [mock_user_event, mock_model_event]

    ctx = MagicMock(spec=CallbackContext)
    ctx.session = mock_session
    ctx.state = {}

    await after_agent_save_cache(ctx)

    # Check that "test query" was correctly cached
    assert "test query" in _AGENT_QUERY_CACHE
    expiry, response_text = _AGENT_QUERY_CACHE["test query"]
    assert response_text == "test response"
    assert expiry > time.time()


@pytest.mark.asyncio
async def test_fast_local_cache_hit():
    """Verify that an exact case-insensitive query bypasses the fast LLM call and hits cache directly."""
    # 1. Populating the cache
    _AGENT_QUERY_CACHE["What is the billing trend?"] = (
        time.time() + 300,
        "Cached response text",
    )

    # 2. Creating a mock context with the exact query but different casing
    mock_event = MagicMock(spec=Event)
    mock_event.role = "user"
    mock_event.content = Content(
        role="user", parts=[Part(text="  what is the billing trend?  ")]
    )

    mock_session = MagicMock()
    mock_session.events = [mock_event]

    ctx = MagicMock(spec=CallbackContext)
    ctx.session = mock_session
    ctx.state = {}

    mock_client = MagicMock()

    with patch("app.agent.genai_client", mock_client):
        await before_agent_cache_lookup(ctx)

        # Confirm the LLM models check was completely bypassed (not called)
        mock_client.models.generate_content.assert_not_called()

        # Confirm we successfully hit the local cache
        assert ctx.state.get("cached_agent_response") == "Cached response text"
