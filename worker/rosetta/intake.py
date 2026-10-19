"""Bounded status check against a fixed public primary registry; no model URLs."""
from __future__ import annotations

import hashlib
import re
import urllib.request

from .common import Invalid, now

REGISTRY = "https://raw.githubusercontent.com/teorth/erdosproblems/main/data/problems.yaml"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Invalid("registry redirect requires operator review")


def parse_status(data, number):
    text = data.decode("utf-8")
    blocks = re.split(r'(?m)^- number: ', text)
    block = next((x for x in blocks if x.startswith(f'"{number}"\n')), None)
    if block is None:
        raise Invalid("problem missing from maintained registry")
    status = re.search(r'(?m)^  informal_status:\n    state: "([^"]+)"', block)
    prize = re.search(r'(?m)^  prize: "\$(\d+)"', block)
    if not status or not prize:
        raise Invalid("registry status/reward format changed; review required")
    if status[1] not in {"open", "falsifiable", "verifiable"}:
        raise Invalid("problem is no longer listed as open")
    return {"problem": number, "status": status[1], "listed_usd": int(prize[1]),
            "excerpt": '- number: ' + block}


def live_status(target):
    if not re.fullmatch(r"erdos-\d+", target["id"]):
        raise Invalid("target has no reviewed live-status adapter")
    request = urllib.request.Request(REGISTRY, headers={"User-Agent": "Rosetta-Research/0.2"})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=15) as response:
            data = response.read(2_000_001)
    except OSError as error:
        raise Invalid("live problem-status check unavailable; no research run started") from error
    if len(data) > 2_000_000:
        raise Invalid("registry exceeds its bounded size")
    status = parse_status(data, int(target["id"].split('-')[1]))
    if status["listed_usd"] != target["reward"]["listed_usd"]:
        raise Invalid("listed reward changed; operator review required")
    return {"uri": REGISTRY, "retrieved_at": now(), "sha256": hashlib.sha256(data).hexdigest(),
            "content": status, "payment_guaranteed": False}
