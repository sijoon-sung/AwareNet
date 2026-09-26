"""KOREN and Jetson measurement-conditioned replay with explicit assumptions.

build: recover and verify source measurements; study: deterministic timing
model; socket: inject the same timing/payload into actual local TCP sockets.
None of these produces a new KOREN or Jetson hardware measurement.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import socket
import statistics
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sfl"))
from barrier_schedule import GradientJob
from trace_replay import replay

CONFIG = ROOT / "configs/measured_replay.json"
INPUT = ROOT / "configs/measurements/koren_jetson_2026-09-23.json"
OUT = ROOT / "out/measured_replay"
POLICIES = ("rr", "fifo", "sjf", "tail", "guarded")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


def network_windows(data):
    """Count bytes in a common wall interval, never N * median(goodput)."""
    m, per = data["meta"], data["per"]
    if len(per) != m["n"] or m["proto"] != "tcp":
        raise ValueError("incomplete or non-TCP network measurement")
    windows = []
    for r in range(m["rounds"]):
        start_idx = r if m["pattern"] == "burst" else r*m["batches"]
        end_idx = r if m["pattern"] == "burst" else (r+1)*m["batches"]-1
        start = min(v["spans"][start_idx][0] for v in per.values())
        end = max(v["spans"][end_idx][1] for v in per.values())
        bits = len(per)*m["batches"]*(m["up_mb"]+m["dn_mb"])*1e6*8
        windows.append({"index": r, "start_s": start, "end_s": end,
                        "duration_s": end-start, "counted_payload_bits": bits,
                        "effective_service_bps": bits/(end-start),
                        "scope": "synchronized_echo_round" if m["pattern"] == "burst" else "overlapping_index_slice_not_a_capacity_measurement"})
    return windows


def build_inputs():
    cfg = read_json(CONFIG)
    jp = ROOT / cfg["jetson_source"]
    jetson = read_json(jp)
    historical = subprocess.run(["git", "show", f"{cfg['jetson_commit']}:{cfg['jetson_original_path']}"],
                                cwd=ROOT, capture_output=True, check=True).stdout
    if json.loads(historical) != jetson:
        raise ValueError("archived Jetson data differs from the original commit")
    source_manifest = [{"path": cfg["jetson_source"], "sha256": hashlib.sha256(jp.read_bytes()).hexdigest(),
                        "commit": cfg["jetson_commit"], "original_path": cfg["jetson_original_path"],
                        "git_blob_semantically_verified": True}]
    for name, entry in jetson["power_modes"].items():
        times = entry["step_times_ms"]
        if len(times) != entry["n_steps"] or not all(x > 0 for x in times):
            raise ValueError(f"invalid raw Jetson samples: {name}")
    networks = {}
    for name, path in cfg["network_sources"].items():
        p = ROOT/path
        data = read_json(p)
        networks[name] = {"raw": data, "windows": network_windows(data)}
        source_manifest.append({"path": path, "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                                "kind": "recorded_echo_timing_not_physical_link_capacity"})
    result = {"schema": 1, "label": cfg["label"], "source_manifest": source_manifest,
              "jetson": jetson, "networks": networks, "assumptions": cfg}
    write_json(INPUT, result)
    print(f"Verified original Jetson commit; recovered {sum(len(v['step_times_ms']) for v in jetson['power_modes'].values())} step samples", flush=True)
    return result


def load_inputs():
    if not INPUT.exists():
        raise FileNotFoundError("run measured_replay.py build first")
    data = read_json(INPUT)
    cfg = read_json(CONFIG)
    if data["assumptions"] != cfg:
        raise ValueError("configuration changed; rebuild the normalized inputs")
    return data


def scenario(data, sample, fraction, release_model, scale, net_window):
    cfg, modes = data["assumptions"], data["jetson"]["power_modes"]
    begin, end = cfg["evaluation_steps"]
    if not begin <= sample < end or begin < cfg["calibration_steps"]:
        raise ValueError("evaluation sample must be outside calibration")
    if fraction not in cfg["tail_fractions_assumed"] or release_model not in cfg["release_models_assumed"]:
        raise ValueError("unregistered mapping assumption")
    # The synchronized burst windows are the network evidence for this model.
    net = data["networks"]["burst"]
    cap = net["windows"][net_window]["effective_service_bps"]*scale
    predicted = net["windows"][0]["effective_service_bps"]*scale
    size = int(net["raw"]["meta"]["dn_mb"]*1e6)
    jobs, tails, releases, measured, bindings = [], {}, {}, {}, {}
    for i, name in enumerate(cfg["modes"]):
        cid, samples = f"c{i}", modes[name]["step_times_ms"]
        calibration = [x*.001*fraction for x in samples[:cfg["calibration_steps"]]]
        pad = cfg["tail_padding_fraction_assumed"]
        jobs.append(GradientJob(cid, size, statistics.median(calibration), min(calibration)*(1-pad), max(calibration)*(1+pad)))
        full_step = samples[sample]*.001
        measured[cid] = full_step
        tails[cid] = fraction*full_step
        releases[cid] = 0. if release_model == "all_ready" else (1-fraction)*full_step
        bindings[cid] = {"power_mode": name, "source_step_index": sample}
    # Virtual queue order is an explicit scenario variable, shared by every arm.
    random.Random(sample).shuffle(jobs)
    return {"jobs": jobs, "tails_s": tails, "release_s": releases, "capacity_bps": cap,
            "predicted_capacity_bps": predicted, "full_step_s": measured, "bindings": bindings,
            "spec": {"sample": sample, "tail_fraction_assumed": fraction, "release_model_assumed": release_model,
                     "capacity_scale": scale, "network_window": net_window}}


def simulate(s, cfg, policy, record_chunks=False):
    return replay(s["jobs"], s["release_s"], s["tails_s"], s["capacity_bps"], policy,
                  predicted_capacity_bps=s["predicted_capacity_bps"], quantum_bytes=cfg["quantum_bytes"],
                  completion_error_s=cfg["completion_error_s_assumed"], record_chunks=record_chunks)


def run_study(data):
    cfg = data["assumptions"]
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    with (OUT/"model_raw.jsonl").open("w", encoding="utf-8") as f:
        for scale in cfg["capacity_scales"]:
            for fraction in cfg["tail_fractions_assumed"]:
                for release in cfg["release_models_assumed"]:
                    for window in (1, 2):
                        for step in range(*cfg["evaluation_steps"]):
                            s = scenario(data, step, fraction, release, scale, window)
                            scores = {p: simulate(s, cfg, p) for p in POLICIES}
                            for value in scores.values():
                                value.pop("chunks")
                            row = {"result_kind": "measurement_conditioned_model", **s["spec"],
                                   "source_bindings": s["bindings"], "measured_full_step_s": s["full_step_s"],
                                   "derived_release_s": s["release_s"], "derived_tail_s": s["tails_s"],
                                   "effective_capacity_bps": s["capacity_bps"],
                                   "predicted_capacity_bps": s["predicted_capacity_bps"], "scores": scores}
                            rows.append(row); f.write(json.dumps(row)+"\n")
    groups = []
    for scale in cfg["capacity_scales"]:
        for fraction in cfg["tail_fractions_assumed"]:
            for release in cfg["release_models_assumed"]:
                group = [r for r in rows if r["capacity_scale"] == scale and r["tail_fraction_assumed"] == fraction and r["release_model_assumed"] == release]
                result = {"capacity_scale": scale, "tail_fraction_assumed": fraction,
                          "release_model_assumed": release, "paired_cases": len(group), "policies": {}}
                for p in POLICIES:
                    gains = [100*(1-r["scores"][p]["barrier_s"]/r["scores"]["rr"]["barrier_s"]) for r in group]
                    result["policies"][p] = {"mean_barrier_s": statistics.mean(r["scores"][p]["barrier_s"] for r in group),
                                             "mean_paired_gain_pct": statistics.mean(gains),
                                             "min_gain_pct": min(gains), "max_gain_pct": max(gains),
                                             "regressions": sum(x < -1e-8 for x in gains),
                                             "interventions": sum(r["scores"][p]["used_tail"] for r in group)}
                groups.append(result)
    validation = {}
    for name, net in data["networks"].items():
        c0 = net["windows"][0]["effective_service_bps"]
        validation[name] = [{"window": w["index"], "observed_s": w["duration_s"],
                             "predicted_s_using_window0": w["counted_payload_bits"]/c0,
                             "relative_error_pct": 100*((w["counted_payload_bits"]/c0)/w["duration_s"]-1),
                             "scope": w["scope"]} for w in net["windows"][1:]]
    result = {"result_kind": "measurement_conditioned_model", "not_new_field_measurement": True,
              "paired_scenarios": len(rows), "groups": groups, "baseline_holdout_check": validation,
              "scope": "single-egress transfer plus mapped local compute; not full SFL round, accuracy or deployment",
              "assumptions": cfg}
    write_json(OUT/"model_summary.json", result)
    print(json.dumps({"paired_scenarios": len(rows), "primary": [g for g in groups if g["tail_fraction_assumed"] == .5]}, indent=2), flush=True)


def socket_trial(data, sample, policy):
    s = scenario(data, sample, .5, "compute_ready", 1., 1)
    plan = simulate(s, data["assumptions"], policy, record_chunks=True)
    payloads = {j.cid: bytes([int(j.cid[1:])+1])*j.size_bytes for j in s["jobs"]}
    listener = socket.create_server(("127.0.0.1", 0))
    readers, writers, threads, errors, received, done, matches = {}, {}, [], [], {}, {}, {}
    try:
        for cid in payloads:
            readers[cid] = socket.create_connection(listener.getsockname(), timeout=10)
            writers[cid], _ = listener.accept()
            writers[cid].settimeout(10)
            for sock in (readers[cid], writers[cid]):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        start = time.perf_counter()
        def consume(cid):
            try:
                buf = bytearray()
                while len(buf) < len(payloads[cid]):
                    part = readers[cid].recv(min(65536, len(payloads[cid])-len(buf)))
                    if not part:
                        raise OSError("early EOF")
                    buf.extend(part)
                received[cid] = time.perf_counter()-start
                time.sleep(s["tails_s"][cid])
                done[cid] = time.perf_counter()-start
                matches[cid] = hashlib.sha256(buf).digest() == hashlib.sha256(payloads[cid]).digest()
            except Exception as exc:
                errors.append(repr(exc))
        for cid in payloads:
            th = threading.Thread(target=consume, args=(cid,), daemon=True)
            threads.append(th); th.start()
        for chunk in plan["chunks"]:
            time.sleep(max(0., start+chunk["send_at_s"]-time.perf_counter()))
            off = chunk["offset"]
            writers[chunk["cid"]].sendall(payloads[chunk["cid"]][off:off+chunk["bytes"]])
        for th in threads:
            th.join(12)
        if errors or any(t.is_alive() for t in threads) or not all(matches.values()) or len(matches) != len(payloads):
            raise RuntimeError(errors or "transfer incomplete/corrupted")
        return {"result_kind": "local_tcp_timing_injection_no_training", **s["spec"], "policy": policy,
                "barrier_s": max(done.values()), "predicted_barrier_s": plan["barrier_s"],
                "gradient_placeholder_receipt_s": received, "completion_s": done,
                "all_payload_hashes_match": True, "payload_bytes": sum(map(len, payloads.values())),
                "used_tail": plan["used_tail"], "injected_tail_s": s["tails_s"], "source_bindings": s["bindings"]}
    finally:
        for sock in [*readers.values(), *writers.values(), listener]:
            sock.close()


def run_sockets(data, repeats):
    if not 1 <= repeats <= 20:
        raise ValueError("repeats must use 1..20 held-out Jetson sample indices")
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    with (OUT/"socket_raw.jsonl").open("w", encoding="utf-8") as f:
        for sample in range(10, 10+repeats):
            order = ["rr", "fifo", "guarded"]
            random.Random(sample).shuffle(order)
            for p in order:
                row = socket_trial(data, sample, p)
                rows.append(row); f.write(json.dumps(row)+"\n"); f.flush()
            print(f"local TCP injection: held-out Jetson sample {sample} done", flush=True)
    baseline = {r["sample"]: r["barrier_s"] for r in rows if r["policy"] == "rr"}
    result = {"result_kind": "local_tcp_timing_injection_no_training", "not_new_field_measurement": True,
              "repeats": repeats, "payload_bytes_per_trial": sorted({r["payload_bytes"] for r in rows}),
              "all_payload_hashes_match": all(r["all_payload_hashes_match"] for r in rows), "policies": {}}
    for policy in ("rr", "fifo", "guarded"):
        arm = [r for r in rows if r["policy"] == policy]
        gains = [100*(1-r["barrier_s"]/baseline[r["sample"]]) for r in arm]
        result["policies"][policy] = {"mean_barrier_s": statistics.mean(r["barrier_s"] for r in arm),
                                      "mean_paired_gain_pct": statistics.mean(gains),
                                      "min_gain_pct": min(gains), "max_gain_pct": max(gains)}
    write_json(OUT/"socket_summary.json", result)
    print(json.dumps(result, indent=2), flush=True)


def main():
    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument("action", choices=("build", "study", "socket", "all"))
    ap.add_argument("--repeats", type=int, default=5)
    a = ap.parse_args()
    data = build_inputs() if a.action in ("build", "all") else load_inputs()
    if a.action in ("study", "all"):
        run_study(data)
    if a.action in ("socket", "all"):
        run_sockets(data, a.repeats)


if __name__ == "__main__":
    main()
