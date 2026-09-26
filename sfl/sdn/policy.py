"""Validated OpenFlow policy export for the operator-owned edge OVS bridge."""

from __future__ import annotations

import ipaddress
import json
import os
import tempfile
from pathlib import Path
from typing import Mapping


def build_policy(decision: Mapping, source_ips: Mapping[str, tuple[str, ...]],
                 path_ports: Mapping[str, int], ingress_port: int,
                 service_ip: str, service_port: int, dpid: int) -> dict:
    """Turn split-depth/path decisions into narrowly scoped OpenFlow matches.

    source_ips contains one consenting, controlled veth/overlay IP per exit.
    Ingress/output ports refer only to ports of the bridge we own.
    """
    if min(ingress_port, service_port, dpid) <= 0:
        raise ValueError("ingress, service port and datapath id must be positive")
    service_ip = str(ipaddress.IPv4Address(service_ip))
    if ingress_port in path_ports.values() or any(p <= 0 for p in path_ports.values()):
        raise ValueError("path ports must be positive and distinct from ingress")
    if len(set(path_ports.values())) != len(path_ports):
        raise ValueError("each path needs its own OVS port")
    rules, used = [], set()
    for cid, assignment in decision["clients"].items():
        route = assignment["route"]
        ips = source_ips.get(cid)
        if not ips or len(ips) != len(route):
            raise ValueError(f"missing consenting ingress IP for every exit of {cid}")
        for src, path in zip(ips, route):
            src = str(ipaddress.IPv4Address(src))
            if src in used or path not in path_ports:
                raise ValueError(f"duplicate source IP or unknown path for {cid}")
            used.add(src)
            rules.append({"client_id": cid, "src_ip": src, "dst_ip": service_ip,
                          "tcp_dst": service_port, "in_port": ingress_port,
                          "out_port": path_ports[path], "path": path})
    return {"schema": 1, "dpid": dpid, "rules": rules}


def validate_policy(policy: dict, allowed_ports: set[int], expected_dpid: int,
                    ingress_port: int, service_ip: str, service_port: int) -> None:
    """Reject policy beyond the operator's switch/ports before issuing flow mods."""
    if policy.get("schema") != 1 or policy.get("dpid") != expected_dpid:
        raise ValueError("policy schema or datapath mismatch")
    if not isinstance(policy.get("rules"), list) or not policy["rules"]:
        raise ValueError("at least one authorized flow is required")
    seen = set()
    for rule in policy.get("rules", []):
        src = str(ipaddress.IPv4Address(rule["src_ip"]))
        ipaddress.IPv4Address(rule["dst_ip"])
        if (src in seen or rule["out_port"] not in allowed_ports
                or rule["in_port"] != ingress_port
                or rule["dst_ip"] != service_ip or rule["tcp_dst"] != service_port):
            raise ValueError("duplicate client or unauthorized switch port")
        if not 1 <= rule["tcp_dst"] <= 65535:
            raise ValueError("invalid TCP service port")
        seen.add(src)


def write_policy(path: str | Path, policy: dict) -> None:
    """Publish a complete new policy through atomic replace on the same volume."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".sdn-", dir=target.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(policy, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
