#!/usr/bin/env python3
"""Trusted optional Hermes adapter. Secrets stay in memory, never stdout."""
from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
import sys
import datetime as dt


def reasoning_options(config):
    """Keep the operator's bounded effort explicit, including on older Hermes catalogs."""
    effort = config.get("reasoning_effort", "low")
    if effort not in {"low", "medium", "high", "xhigh"}:
        raise ValueError("unsupported reasoning effort")
    if config["provider"] == "xai":
        return {"reasoning_config": {"enabled": True, "effort": effort},
                "request_overrides": {"reasoning_effort": effort}}
    if "reasoning_effort" in config:
        raise ValueError("explicit effort is currently supported only for xAI")
    return {}


def guard_request(create, config, on_start, counts=None):
    """One SDK request, exact configured model, no tools, bounded output."""
    counts = counts if counts is not None else {"started": 0, "blocked": 0}
    def checked(*args, **kwargs):
        limit = kwargs.get("max_tokens", kwargs.get("max_completion_tokens"))
        extra = kwargs.get("extra_body") or {}
        protected = {"model", "tools", "tool_choice", "functions", "function_call",
                     "max_tokens", "max_completion_tokens", "max_output_tokens", "reasoning_effort"}
        valid = (not args and kwargs.get("model") == config["model"] and not kwargs.get("tools")
                 and not kwargs.get("functions") and isinstance(extra, dict)
                 and not protected.intersection(extra)
                 and type(limit) is int and 1 <= limit <= 4096)
        if config["provider"] == "xai":
            valid = valid and kwargs.get("reasoning_effort") == config.get("reasoning_effort", "low")
        if counts["started"] or not valid:
            counts["blocked"] += 1
            raise RuntimeError("provider request violates the bounded adapter policy")
        counts["started"] += 1
        on_start(dict(counts))
        return create(**kwargs)
    return checked, counts


def main():
    config = json.loads(Path(sys.argv[1]).read_text())
    packet = json.load(sys.stdin)
    providers = {"nvidia": ("https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY"),
                 "xai": ("https://api.x.ai/v1", "XAI_API_KEY")}
    if config["provider"] not in providers or config["base_url"] != providers[config["provider"]][0]:
        raise ValueError("requires an explicitly supported provider endpoint")
    reasoning = reasoning_options(config)
    sys.path.insert(0, config["hermes_source"])
    with contextlib.redirect_stdout(sys.stderr):
        import hermes_bootstrap  # noqa: F401 -- activates existing dependencies
        from dotenv import dotenv_values
    credential = dotenv_values(config["credential_env_file"]).get(providers[config["provider"]][1])
    if not credential:
        raise ValueError("existing provider credential unavailable")
    home = Path(config["agent_home"])
    home.mkdir(parents=True, exist_ok=True)
    home.chmod(0o700)
    settings = {"model": {"provider": config["provider"], "base_url": config["base_url"],
                 "default": config["model"]}, "fallback_models": [], "max_tokens": 4096,
                "agent": {"api_max_retries": 1, "auto_recovery_cycles": 0, "environment_probe": False},
                "memory": {"enabled": False}, "display": {"show_cost": False}}
    path = home / "config.yaml"
    path.write_text(json.dumps(settings))
    path.chmod(0o600)
    os.environ["HERMES_HOME"] = str(home)
    os.environ.pop("HERMES_YOLO_MODE", None)
    with contextlib.redirect_stdout(sys.stderr):
        from run_agent import AIAgent
        agent = AIAgent(model=config["model"], provider=config["provider"], base_url=config["base_url"],
            api_key=credential, api_mode="chat_completions", enabled_toolsets=[], disabled_toolsets=["all"],
            max_iterations=1, max_tokens=4096, quiet_mode=True, skip_context_files=True,
            skip_memory=True, skip_background_review=True, load_soul_identity=False,
            fallback_model={}, save_trajectories=False, run_budget_seconds=150,
            cwd=str(home), session_id="rosetta-" + packet["run_id"], **reasoning)
        if agent.tools or agent.valid_tool_names:
            raise RuntimeError("nonempty tool surface; refusing model call")
        if getattr(agent, "_fallback_chain", None):
            raise RuntimeError("fallback provider configured; refusing model call")
        if (agent._api_max_retries != 1 or agent._auto_recovery_cycles != 0
                or agent.client.max_retries != 0):
            raise RuntimeError("automatic retry/recovery policy is not disabled")
        receipt_path = os.environ.get("ROSETTA_AGENT_RECEIPT")
        def receipt(value):
            if receipt_path:
                fd = os.open(receipt_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "w") as stream:
                    json.dump(value, stream)
        identity = {"provider": config["provider"], "model": config["model"], "tool_count": 0,
                    "reasoning_effort": reasoning.get("request_overrides", {}).get("reasoning_effort"),
                    "maximum_output_tokens": 4096, "at": dt.datetime.now(dt.timezone.utc).isoformat()}
        receipt({**identity, "status": "adapter_ready", "api_calls_started": 0})
        from openai.resources.chat.completions import Completions
        original_create = Completions.create
        counts = {"started": 0, "blocked": 0}
        def on_start(counts):
            receipt({**identity, "status": "request_started_outcome_unknown", "api_calls_started": counts["started"]})
        def guarded_sdk(resource, *args, **kwargs):
            # Hermes can clone its SDK client with with_options(); an instance-only
            # wrapper does not cover that request. This process hosts one adapter.
            if (str(resource._client.base_url).rstrip("/") != config["base_url"]
                    or resource._client.max_retries != 0):
                raise RuntimeError("SDK endpoint or retry policy changed")
            guarded, _ = guard_request(lambda **kw: original_create(resource, **kw), config, on_start, counts)
            return guarded(*args, **kwargs)
        Completions.create = guarded_sdk
        try:
            result = agent.run_conversation(user_message=json.dumps(packet),
                system_message="Follow Rosetta's instructions field. Return only proposal JSON. You have no tools.")
        except Exception as error:
            receipt({**identity, "status": "adapter_error", "error_type": type(error).__name__,
                     "api_calls_started": counts["started"], "requests_blocked": counts["blocked"]})
            raise
        finally:
            Completions.create = original_create
        if counts["started"] != 1:
            raise RuntimeError("expected exactly one guarded SDK request")
        if isinstance(result, dict):
            receipt({**identity, "status": "response_received",
                     "api_calls_started": counts["started"], "requests_blocked": counts["blocked"],
                     **{k: result.get(k) for k in ["input_tokens", "output_tokens", "api_calls", "failed"]}})
    if not isinstance(result, dict) or result.get("failed") or not result.get("final_response"):
        raise RuntimeError("Hermes returned no successful final response")
    print(json.dumps(json.loads(result["final_response"])))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("Hermes adapter failed: " + type(error).__name__, file=sys.stderr)
        raise SystemExit(1)
