"""Record inspected implementation provenance and analytic control time scales.

Reads cached Git refs and current sources. Does not access or configure any host.
The time-scale examples are arithmetic, not an AI or network benchmark.
"""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'configs/measurements/network_implementation_audit_2026-09-26.json'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def main():
    refs = ['origin/awarenet', 'origin/main', 'origin/deploy', 'origin/OVS_SDN', 'origin/PPT', 'origin/PPT_성시준']
    paths = ['sfl/net/real_rig.sh', 'sfl/net/hairpin_lo.sh', 'sfl/policies.py',
             'sfl/mpsend.py', 'sfl/chunker.py', 'sfl/sdn/osken_controller.py',
             'scripts/measurement/net_throughput.py', 'scripts/exp/run_scen32.sh',
             'out/rig_selftest_h5x.json']
    old = [('origin/main', 'scripts/deploy/pangyo_tc_agent.py'),
           ('origin/main', 'scripts/deploy/ovs_setup_mode_b.sh'),
           ('origin/OVS_SDN', 'edge/ovs_setup.sh'),
           ('origin/OVS_SDN', 'central/bandwidth_executor.py'),
           ('origin/OVS_SDN', 'central/sdn_controller.py')]
    inputs = [{'path': p, 'sha256': hashlib.sha256((ROOT/p).read_bytes()).hexdigest()} for p in paths]
    historical = []
    for ref, p in old:
        blob = git('show', f'{ref}:{p}')
        historical.append({'ref': ref, 'commit': git('rev-parse', ref).decode().strip(),
                           'path': p, 'sha256': hashlib.sha256(blob).hexdigest()})
    packets = [{'rate_mbps': rate, 'bytes_per_packet': 1500,
                'serialization_us': 1500*8/rate,
                'packets_per_s': rate*1e6/(1500*8)} for rate in [56, 1000]]
    waits = [{'rate_mbps': rate, 'hypothetical_decision_ms': delay,
              'bytes_arriving_if_output_stalls': rate*1e6/8*delay/1000}
             for rate in [56, 1000] for delay in [1, 10, 50, 100]]
    result = {
        'date': '2026-09-26', 'cached_refs_only': True,
        'refs': {r: git('rev-parse', r).decode().strip() for r in refs},
        'current_sources': inputs, 'historical_sources': historical,
        'findings': {
            'current_kernel_configuration': 'Linux tc/HTB/IFB/u32; experiment setup and perturbation',
            'loopback_path_action': 'replace IFB classification filters; not an underlay next-hop change',
            'koren_path_action': 'TCP relay endpoint selection; tc imposes experiment access/edge limits',
            'tensor_split_layer': 'application layer over multiple standard TCP sockets',
            'tcp_changes': 'connection reuse, blocking socket after connect, TCP_NODELAY, SO_SNDBUF request 262144 bytes',
            'reliability': 'range and duplicate validation, whole-tensor ACK, async ACK check and flush; no per-chunk received ACK',
            'historical_ack_priority': 'main: optional AWARENET_ACK_PROTECT=0 by default; IPv4 packet-length <128 priority classifier, not pure ACK identification',
            'historical_ovs_caveat': 'main moves shaping from virtual VXLAN port to actual container netdev due to possible no-op',
            'custom_tcp_kernel_patch_found': False,
            'negative_search_scope': 'six cached branch tips, tracked .py/.sh/.c/.h/.conf/.patch/.diff files; not all historical/deleted/untracked files',
            'standard_cc_selection': 'net_throughput.py measurement socket can request TCP_CONGESTION; not a custom congestion algorithm',
            'ai_controller_inference_measured': False,
            'institution_delegation_verified': False,
        },
        'analytic_examples': {'packet_serialization': packets, 'hypothetical_stalled_output': waits,
                              'assumptions': 'fixed 1500-byte packet, full stated bit rate, no L2 overhead; hypothetical stalled output; not measured latency, deadline, or observed queue growth'},
        'reference_urls': ['https://www.rfc-editor.org/rfc/rfc7426.html',
                           'https://www.rfc-editor.org/rfc/rfc5681.html',
                           'https://docs.kernel.org/networking/ip-sysctl.html',
                           'https://man7.org/linux/man-pages/man7/socket.7.html'],
        'new_kernel_deployment': False,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'refs': len(refs), 'current_sources': len(inputs), 'historical_sources': len(historical),
                      'output': str(OUT)}, ensure_ascii=True))


if __name__ == '__main__':
    main()
