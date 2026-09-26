"""Actual PyTorch gradients over paced loopback TCP; synthetic device delays.

This is a primed ready-gradient queue microbenchmark, NOT full SFL training,
tc emulation, or a KOREN measurement. All front forwards and server backwards
finish before timing. Independent client backwards execute after receipt.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import random
import socket
import statistics
import sys
import threading
import time

import numpy as np
import torch
from torch import nn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sfl"))
from barrier_schedule import GradientJob, chunk_schedule, plan_window


def prepare(seed, clients, case):
    torch.manual_seed(seed)
    front = nn.Sequential(nn.Conv2d(3, 16, 3, padding=1), nn.Tanh())
    back = nn.Sequential(nn.AdaptiveAvgPool2d(1), nn.Flatten(), nn.Linear(16, 3))
    tasks = {}
    for i in range(clients):
        net = copy.deepcopy(front)
        x, y = torch.randn(4, 3, 32, 32), torch.randint(0, 3, (4,))
        out = net(x)
        remote = out.detach().requires_grad_(True)
        loss = nn.functional.cross_entropy(back(remote), y)
        grad, = torch.autograd.grad(loss, remote)
        reference = copy.deepcopy(front)
        ref_opt = torch.optim.SGD(reference.parameters(), lr=.05)
        ref_loss = nn.functional.cross_entropy(back(reference(x)), y)
        ref_loss.backward(); ref_opt.step()
        blob = grad.numpy().tobytes()
        delay = (.35 if i == clients-2 else .55 if i == clients-1 else .025) if case == "heterogeneous" else .05
        tasks[f"c{i}"] = {"net": net, "out": out, "reference": reference,
                           "blob": blob, "delay": delay, "grad_shape": grad.shape}
    return tasks


def trial(seed, case, policy, clients=8, capacity_bps=16e6):
    tasks = prepare(seed, clients, case)
    ids = list(tasks)
    random.Random(seed).shuffle(ids)
    jobs = [GradientJob(k, len(tasks[k]["blob"]), tasks[k]["delay"]+.005,
                        tasks[k]["delay"], tasks[k]["delay"]+.03) for k in ids]
    decision = plan_window(jobs, capacity_bps, completion_error_s=.005)
    schedule = decision["schedule"] if policy == "guarded" else chunk_schedule(jobs, policy)
    listener = socket.create_server(("127.0.0.1", 0))
    writers, readers = {}, {}
    threads, errors, received, done, hashes, diffs = [], [], {}, {}, {}, {}
    try:
        for k in ids:
            reader = socket.create_connection(listener.getsockname(), timeout=10)
            writer, _ = listener.accept()
            writer.settimeout(10)
            for sock in (reader, writer):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            readers[k], writers[k] = reader, writer
        start = time.perf_counter()
        def consume(k):
            try:
                task, stream = tasks[k], readers[k]
                blob = bytearray()
                while len(blob) < len(task["blob"]):
                    part = stream.recv(min(65536, len(task["blob"])-len(blob)))
                    if not part:
                        raise OSError("unexpected EOF")
                    blob.extend(part)
                received[k] = time.perf_counter()-start
                hashes[k] = hashlib.sha256(blob).hexdigest()
                grad = torch.from_numpy(np.frombuffer(blob, dtype=np.float32).copy()).reshape(task["grad_shape"])
                opt = torch.optim.SGD(task["net"].parameters(), lr=.05)
                opt.zero_grad(); task["out"].backward(grad); opt.step()
                time.sleep(task["delay"])  # Explicit device-delay emulation, not measured compute.
                done[k] = time.perf_counter()-start
                diffs[k] = max((a-b).abs().max().item() for a, b in zip(task["net"].parameters(), task["reference"].parameters()))
            except Exception as exc:
                errors.append(repr(exc))
        for k in ids:
            th = threading.Thread(target=consume, args=(k,), daemon=True)
            threads.append(th); th.start()
        # One shared user-space serializer; every arm sends the exact same bytes.
        deadline = time.perf_counter()
        for cid, offset, size in schedule:
            deadline = max(deadline, time.perf_counter()) + size*8/capacity_bps
            time.sleep(max(0., deadline-time.perf_counter()))
            writers[cid].sendall(tasks[cid]["blob"][offset:offset+size])
        for th in threads:
            th.join(10)
        if errors or any(th.is_alive() for th in threads):
            raise RuntimeError(errors or "client did not finish")
        if any(hashes[k] != hashlib.sha256(t["blob"]).hexdigest() for k, t in tasks.items()):
            raise AssertionError("gradient payload changed")
        if max(diffs.values()) > 1e-6:
            raise AssertionError("transport changed the monolithic client update")
        return {"seed": seed, "case": case, "policy": policy, "barrier_s": max(done.values()),
                "mean_gradient_completion_s": statistics.mean(received.values()),
                "gradient_completion_s": received, "client_done_s": done,
                "payload_bytes": sum(len(t["blob"]) for t in tasks.values()),
                "max_parameter_error": max(diffs.values()), "all_payload_hashes_match": True,
                "used_tail": decision["used_tail"] if policy == "guarded" else policy == "tail",
                "emulated_delay_s": {k: t["delay"] for k, t in tasks.items()}}
    finally:
        for sock in list(writers.values())+list(readers.values()):
            sock.close()
        listener.close()


def main():
    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--out", type=Path, default=ROOT / "out/barrier_study")
    args = ap.parse_args()
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    args.out.mkdir(parents=True, exist_ok=True)
    # Warm optimizer/thread initialization outside the measured arms.
    trial(777, "homogeneous", "rr", clients=2)
    rows = []
    with (args.out / "socket_raw.jsonl").open("w", encoding="utf-8") as f:
        for case in ("heterogeneous", "homogeneous"):
            for seed in range(args.repeats):
                order = ["rr", "fifo", "sjf", "tail", "guarded"]
                random.Random(900+seed).shuffle(order)
                for p in order:
                    row = trial(seed, case, p)
                    rows.append(row); f.write(json.dumps(row)+"\n"); f.flush()
                print(f"{case} seed={seed} done", flush=True)
    summary = {}
    for case in ("heterogeneous", "homogeneous"):
        selected = [r for r in rows if r["case"] == case]
        baseline = {r["seed"]: r["barrier_s"] for r in selected if r["policy"] == "rr"}
        summary[case] = {}
        for policy in ("rr", "fifo", "sjf", "tail", "guarded"):
            arm = [r for r in selected if r["policy"] == policy]
            gains = [100*(1-r["barrier_s"]/baseline[r["seed"]]) for r in arm]
            summary[case][policy] = {"mean_barrier_s": statistics.mean(r["barrier_s"] for r in arm),
                                    "mean_paired_gain_pct": statistics.mean(gains),
                                    "min_gain_pct": min(gains), "max_gain_pct": max(gains)}
    result = {"scope": "primed queue, paced loopback TCP, real PyTorch gradients, injected device delays",
              "repeats": args.repeats, "clients": 8, "capacity_bps": 16e6,
              "torch": torch.__version__, "summary": summary,
              "max_parameter_error": max(r["max_parameter_error"] for r in rows),
              "all_payload_hashes_match": all(r["all_payload_hashes_match"] for r in rows),
              "payload_bytes_per_arm": sorted({r["payload_bytes"] for r in rows})}
    (args.out / "socket_summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
