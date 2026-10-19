"""Trusted, bounded certificate checkers; never execute model text here."""
from __future__ import annotations

from .common import Invalid


def validate_cipher(data):
    lines = data.get("ciphertext_lines")
    if not isinstance(lines, list) or not lines or any(not isinstance(x, list) for x in lines):
        raise Invalid("ciphertext_lines must contain nonempty lists")
    flat = sum(lines, [])
    if not flat or len(flat) > 10000 or any(type(x) is not int or x < 0 for x in flat):
        raise Invalid("invalid glyph sequence")
    if data.get("total_length") != len(flat):
        raise Invalid(f"declared length {data.get('total_length')} differs from actual length {len(flat)}")
    if data.get("line_lengths") is not None and data["line_lengths"] != list(map(len, lines)):
        raise Invalid("declared line lengths differ from input")
    if data.get("unique_glyphs") != len(set(flat)):
        raise Invalid("declared glyph count differs from input")
    if data.get("transcription_verified") is not True or not data.get("source_sha256"):
        raise Invalid("historical transcription has not been verified against a preserved source")
    return flat


def validate_plan(plan, packet):
    if not isinstance(plan, dict) or set(plan) != {"protocol_version", "target_id", "method_id", "hypothesis", "python"}:
        raise Invalid("proposal must contain exactly protocol_version, target_id, method_id, hypothesis, python")
    if type(plan["protocol_version"]) is not int or plan["protocol_version"] != 1:
        raise Invalid("unsupported protocol version")
    if plan["target_id"] != packet["target"]["id"] or plan["method_id"] != packet["method_id"]:
        raise Invalid("proposal changed the assigned target or method")
    for field, maximum in [("hypothesis", 4000), ("python", 24000)]:
        if not isinstance(plan[field], str) or not 1 <= len(plan[field]) <= maximum:
            raise Invalid(f"invalid {field}")
    try:
        compile(plan["python"], "experiment.py", "exec")
    except (SyntaxError, ValueError) as error:
        raise Invalid("experiment is not valid Python") from error


def graph_certificate(value, *, minimum_degree, forbidden_lengths, max_operations=250000):
    if not isinstance(value, dict) or set(value) != {"vertices", "edges"}:
        raise Invalid("graph certificate must have only vertices and edges")
    n, edges = value["vertices"], value["edges"]
    if type(n) is not int or not 3 <= n <= 16 or not isinstance(edges, list) or len(edges) > 120:
        raise Invalid("graph is outside the bounded verifier domain")
    adjacency = [set() for _ in range(n)]
    seen = set()
    for edge in edges:
        if not isinstance(edge, list) or len(edge) != 2 or any(type(x) is not int or not 0 <= x < n for x in edge):
            raise Invalid("invalid edge")
        a, b = sorted(edge)
        if a == b or (a, b) in seen:
            raise Invalid("self-loop or duplicate edge")
        seen.add((a, b))
        adjacency[a].add(b)
        adjacency[b].add(a)
    if min(map(len, adjacency)) < minimum_degree:
        return {"status": "rejected", "reason": "minimum degree condition fails"}
    operations = 0
    for length in forbidden_lengths:
        if length > n:
            continue
        for start in range(n):
            stack = [(start, 1 << start, 1)]
            while stack:
                operations += 1
                if operations > max_operations:
                    return {"status": "inconclusive", "reason": "verifier operation budget exhausted"}
                vertex, mask, depth = stack.pop()
                if depth == length:
                    if start in adjacency[vertex]:
                        return {"status": "rejected", "reason": f"forbidden cycle of length {length} exists"}
                    continue
                for neighbor in adjacency[vertex]:
                    if neighbor > start and not mask & (1 << neighbor):
                        stack.append((neighbor, mask | (1 << neighbor), depth + 1))
    return {"status": "certificate_verified", "reason": "bounded exhaustive certificate check passed",
            "operations": operations, "vertices": n, "edges": len(edges)}


def check_result(result, target):
    if not isinstance(result, dict) or set(result) != {"status", "certificate"}:
        raise Invalid("experiment output must contain exactly status and certificate")
    if result["status"] == "no_candidate" and result["certificate"] is None:
        return {"status": "no_finding", "reason": "bounded search found no candidate; no hypothesis is eliminated"}
    if result["status"] != "candidate":
        raise Invalid("unknown result status or malformed no_candidate result")
    outcome = graph_certificate(result["certificate"], minimum_degree=target["minimum_degree"],
                                forbidden_lengths=target["forbidden_lengths"])
    if outcome["status"] == "certificate_verified":
        outcome["status"] = "calibration_passed" if target["kind"] == "calibration" else "candidate_needs_review"
    return outcome
