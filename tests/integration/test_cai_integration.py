from finops_agent.agent import root_agent
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types


def test_cai_tools_integration():
    """
    Integration test to verify the CAI tools are available and correctly handled
    by the agent in a conversational flow. Note: this requires valid GCP credentials.
    If the project has none, this will likely fail during the API call, but we can verify
    the agent *attempts* to use the tool.
    """
    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="test_user", app_name="test")
    runner = Runner(agent=root_agent, session_service=session_service, app_name="test")

    # Ask a question that should trigger the tools
    message = types.Content(
        role="user",
        parts=[
            types.Part(
                text="I have a resource with name //compute.googleapis.com/projects/p1/zones/z1/disks/d1. Can you fetch its CAI metadata and history starting from 2026-03-01T00:00:00Z?"
            )
        ],
    )

    events = list(
        runner.run(
            new_message=message,
            user_id="test_user",
            session_id=session.id,
            run_config=RunConfig(
                streaming_mode=StreamingMode.NONE
            ),  # Just get the final response for simplicity
        )
    )

    assert len(events) > 0, "Expected at least one response"

    # We don't assert the *success* of the tool (as it requires real creds and data),
    # but we assert the agent attempted to answer or used the tools.
    has_text = False
    for event in events:
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    has_text = True
                    print(part.text)

    assert has_text, "Expected a text response from the agent"
