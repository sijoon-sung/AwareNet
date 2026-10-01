"""Recompute the 8-client fixed-deadline ablation from preserved round logs.

Run from the repository root, or the root of the extracted evidence ZIP.
This performs no training and changes no original log.
"""
import json
from pathlib import Path
from statistics import mean

for name, arm, policy in [
    ('baseline', 'bothmp', 'uniform'),
    ('width', 'width3', 'widthpath'),
    ('path+split', 'mp', 'widthpath'),
    ('width+path', 'both3', 'widthpath'),
    ('width+path+split', 'bothmp', 'widthpath'),
]:
    results = []
    for seed in (1, 2, 3):
        stem = Path(f'out/wp_r8mix_rho1_s{seed}_{arm}_{policy}')
        rows = [json.loads(line) for line in Path(str(stem)+'.jsonl').read_text(encoding='utf-8').splitlines()]
        rows = [row for row in rows if 'makespan' in row]
        assert len(rows) == 24
        if arm == 'width3':
            assert len({json.dumps(row['paths'], sort_keys=True) for row in rows}) == 1
        results.append({
            'seed': seed,
            'time_s': mean(row['makespan'] for row in rows[10:]),
            'mean_width': mean(mean(row['plan'].values()) for row in rows[10:]),
            'accuracy_pct': 100*mean(row['acc'] for row in rows[-20:]),
        })
    print(json.dumps({'policy': name,
                      **{key: mean(row[key] for row in results) for key in ('time_s', 'mean_width', 'accuracy_pct')},
                      'seeds': results}, ensure_ascii=False))
