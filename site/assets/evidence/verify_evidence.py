"""Run beside manifest.json; verify original bytes and recompute reported numbers."""
import hashlib
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parent


def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))


def main():
    manifest = read(ROOT/'manifest.json')
    sources = {}
    checked = 0
    for group in manifest['groups']:
        assert hashlib.sha256((ROOT/group['archive']).read_bytes()).hexdigest() == group['archive_sha256']
        for f in group['files']:
            p = ROOT/f['public_path']
            assert hashlib.sha256(p.read_bytes()).hexdigest() == f['sha256'], f['source_path']
            assert p.stat().st_size == f['bytes']
            sources[f['source_path']] = p
            checked += 1
    computed = {'files_checked': checked, 'koren': {}, 'jetson_median_ms': {}, 'lora_correct': {}}
    for cond in ('normal', 'traffic', 'slow', 'vary'):
        computed['koren'][cond] = {}
        for policy in ('uniform', 'widthpath'):
            means = []
            for seed in (1,2,3):
                p = sources[f'out/wp_scen32_{cond}_s{seed}_bothmp_{policy}.jsonl']
                rows = [json.loads(s) for s in p.read_text(encoding='utf-8-sig').splitlines() if s.strip()]
                rows = [r for r in rows if 'round' in r]
                assert [r['round'] for r in rows] == list(range(24))
                key = 'makespan' if 'makespan' in rows[0] else 'makespan_s'
                means.append(statistics.mean(r[key] for r in rows[4:]))
            value = statistics.mean(means)
            expected = next(r for r in manifest['groups'][0]['statistics'] if r['condition']==cond)[policy]['mean_s']
            assert abs(value-expected) < 1e-9
            computed['koren'][cond][policy] = value
    a = read(sources['_archive/v2/jetson/results/jetson_compute_anchor.json'])
    for mode,d in a['power_modes'].items():
        assert len(d['step_times_ms']) == 30
        median = statistics.median(d['step_times_ms'])
        assert round(median,1) == d['step_median_ms']
        computed['jetson_median_ms'][mode] = median
    evaluation = read(sources['out/fed_split/eval_0913v1.json'])
    strict = read(sources['out/fed_split/strict_0913v1.json'])
    for name, domains in evaluation['grid'].items():
        count = sum(bool(strict.get(name,{}).get(r['q'],r['ok'])) for domain in domains.values() for r in domain['detail'])
        computed['lora_correct'][name] = count
    assert sorted(computed['lora_correct'].values()) == [0,6,12,12]
    revised = read(sources['configs/measurements/report_metrics_revised.json'])
    for entry in revised['sources']:
        assert hashlib.sha256(sources[entry['path']].read_bytes()).hexdigest() == entry['sha256']
    def verify_run(run):
        rr = [json.loads(s) for s in sources[run['source']].read_text(encoding='utf-8-sig').splitlines() if s.strip()]
        rr = [r for r in rr if 'round' in r]
        assert [r['round'] for r in rr] == list(range(run['rounds']))
        args = read(sources[run['source'].replace('.jsonl', '.args.json')])
        assert args['clients'] == run['clients'] and args['seed'] == run['seed']
        assert (2 if args['multipath'] else 1) == run['exits']
        values = {
            'mean_round_s': statistics.mean(r['makespan'] for r in rr[4:]),
            'mean_width': statistics.mean(statistics.mean(r['plan'].values()) for r in rr[4:]),
            'mean_application_bytes': statistics.mean(sum(v[2] for v in r['per_client'].values()) for r in rr[4:]),
            'final_accuracy_pct': 100*rr[-1]['acc'],
            'tail50_accuracy_pct': 100*statistics.mean(r['acc'] for r in rr[-50:]),
        }
        for key,value in values.items():
            assert abs(value-run[key]) < 1e-8, (run['source'],key)
        return values
    for scenario in revised['scenarios']:
        for arm in ('uniform','widthpath'):
            runs = [verify_run(r) for r in scenario[arm]['seeds']]
            for key in ('mean_round_s','mean_width','mean_application_bytes','final_accuracy_pct'):
                assert abs(statistics.mean(r[key] for r in runs)-scenario[arm][key]) < 1e-8
    computed['accuracy_200'] = []
    for arm in revised['accuracy_200']:
        runs = [verify_run(r) for r in arm['seeds']]
        for key in ('mean_round_s','mean_width','mean_application_bytes','tail50_accuracy_pct'):
            assert abs(statistics.mean(r[key] for r in runs)-arm[key]) < 1e-8
        computed['accuracy_200'].append({k:arm[k] for k in ('lam','mean_round_s','tail50_accuracy_pct','time_reduction_pct','accuracy_difference_pp')})
    computed['report_source_hashes_checked'] = len(revised['sources'])
    print(json.dumps(computed, indent=2))


if __name__ == '__main__':
    main()
