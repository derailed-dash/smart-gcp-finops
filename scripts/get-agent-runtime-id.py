#!/usr/bin/env python3
"""
Description: Retrieves the deployed Vertex AI Reasoning Engine resource ID.
Usage: python scripts/get-agent-runtime-id.py <project_id> <region> <service_name>
"""
import sys

import vertexai
from vertexai.preview.reasoning_engines import ReasoningEngine


def main():
    if len(sys.argv) < 4:
        print("Usage: python get-agent-runtime-id.py <project_id> <region> <service_name>", file=sys.stderr)
        sys.exit(1)

    project = sys.argv[1]
    region = sys.argv[2]
    service_name = sys.argv[3]

    try:
        vertexai.init(project=project, location=region)
        engines = ReasoningEngine.list()
        for engine in engines:
            if engine.display_name == service_name:
                print(engine.resource_name)
                sys.exit(0)

        print(f"Error: Reasoning Engine with display name '{service_name}' not found.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: Failed to retrieve reasoning engine list: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
