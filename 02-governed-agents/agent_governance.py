from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID


def verify_monitoring(
    connections: Sequence[Mapping[str, Any]], expected_name: str
) -> dict[str, str]:
    if not expected_name.strip() or any(
        marker in expected_name for marker in ("<", ">", "$(", "/")
    ):
        raise ValueError(
            "APPLICATION_INSIGHTS_RESOURCE_NAME must be an approved component name."
        )
    suffix = f"/providers/microsoft.insights/components/{expected_name.strip()}".lower()
    matches = [
        connection
        for connection in connections
        if connection.get("type") == "AppInsights"
        and str(connection.get("target", "")).rstrip("/").lower().endswith(suffix)
    ]
    if not matches:
        raise ValueError(
            "The project has no AppInsights connection targeting the approved component "
            f"'{expected_name}'. Ask the platform team to configure project tracing."
        )
    return {
        "application_insights": expected_name,
        "check": "connection_configuration_only",
    }


def verify_identity(agent: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    verified: dict[str, dict[str, str]] = {}
    for field in ("blueprint", "instance_identity"):
        identity = agent.get(field)
        if identity is None:
            raise ValueError(
                f"Agent is missing {field}. Creation may have succeeded, but the agent "
                "cannot be released without a verified new-model Agent Identity. "
                "Inspect tenant support and legacy-agent status; no resource was deleted."
            )
        if not isinstance(identity, Mapping):
            raise TypeError(f"Agent {field} must be an identity object.")
        verified[field] = {}
        for key in ("client_id", "principal_id"):
            value = identity.get(key)
            try:
                valid = isinstance(value, str) and UUID(value).int != 0
            except ValueError:
                valid = False
            if not valid:
                raise ValueError(f"Agent {field}.{key} must be a non-empty UUID.")
            verified[field][key] = value
    return verified


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Foundry configuration metadata; does not provision resources."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    monitoring = commands.add_parser("monitoring")
    monitoring.add_argument("--expected-name", required=True)
    commands.add_parser("identity")
    arguments = parser.parse_args()
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise TypeError("Expected a JSON object.")
        if arguments.command == "monitoring":
            connections = payload.get("value")
            if not isinstance(connections, list) or not all(
                isinstance(connection, dict) for connection in connections
            ):
                raise ValueError("Expected a connection list in 'value'.")
            result = verify_monitoring(connections, arguments.expected_name)
        else:
            result = verify_identity(payload)
    except (ValueError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
