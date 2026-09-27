"""Reaggregate saved rounds for the scheduler report; no experiment is run."""
from pathlib import Path
import hashlib
import json
import statistics as st

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'configs/measurements/report_metrics_revised.json'


def main():
    used = set()
    def read(path):
        used.add(path)
        return json.loads((ROOT/path).read_text(encoding='utf-8-sig'))
    def run(stem, expected):
        path = 'out/'+stem+'.jsonl'; used.add(path)
        rr = [json.loads(s) for s in (ROOT/path).read_text(encoding='utf-8-sig').splitlines() if s.strip()]
        rr = [r for r in rr if 'round' in r]
        assert [r['round'] for r in rr] == list(range(expected)), path
        args = read('out/'+stem+'.args.json')
        assert args['rounds'] == expected
        assert all(0 <= r['acc'] <= 1 for r in rr)
        body = rr[4:]
        d = dict(source=path, seed=args['seed'], rounds=len(rr), clients=args['clients'],
                 mean_round_s=st.mean(r['makespan'] for r in body),
                 mean_width=st.mean(st.mean(r['plan'].values()) for r in body),
                 mean_application_bytes=st.mean(sum(v[2] for v in r['per_client'].values()) for r in body),
                 final_accuracy_pct=100*rr[-1]['acc'],
                 tail50_accuracy_pct=100*st.mean(r['acc'] for r in rr[-50:]),
                 exits=2 if args['multipath'] else 1)
        return d, rr

    scenarios=[]; traces={}
    keys=['mean_round_s','mean_width','mean_application_bytes','final_accuracy_pct']
    for cond,label in [('normal','정상'),('traffic','트래픽 몰림'),('slow','연산 지연'),('vary','용량 변동')]:
        item=dict(condition=cond,label=label)
        for arm in ['uniform','widthpath']:
            samples=[];seq=[]
            for seed in (1,2,3):
                d,rr=run(f'wp_scen32_{cond}_s{seed}_bothmp_{arm}',24);samples.append(d);seq.append(rr)
            item[arm]={k:st.mean(d[k] for d in samples) for k in keys};item[arm]['seeds']=samples
            traces[f'{cond}_{arm}']=[dict(round=i,time_s=st.mean(r[i]['makespan'] for r in seq),
                mean_width=st.mean(st.mean(r[i]['plan'].values()) for r in seq),
                moved_clients=st.mean(sum(r[i]['paths'][k]!=r[i-1]['paths'][k] for k in r[i]['paths']) if i else 0 for r in seq)) for i in range(24)]
        a,b=item['uniform'],item['widthpath']
        item.update(time_reduction_pct=100*(1-b['mean_round_s']/a['mean_round_s']),
                    application_bytes_reduction_pct=100*(1-b['mean_application_bytes']/a['mean_application_bytes']),
                    final_accuracy_difference_pp=b['final_accuracy_pct']-a['final_accuracy_pct'])
        scenarios.append(item)

    accuracy=[]
    for label,stem,lam in [('기준선','wp_r8mix_acc',None),('λ=18','wp_r8mix_acc_l18',18),('λ=70','wp_r8mix_acc',70),('λ=280','wp_r8mix_acc_l280',280)]:
        arm='uniform' if lam is None else 'widthpath'
        samples=[run(f'{stem}_s{seed}_bothmp_{arm}',200)[0] for seed in (1,2)]
        accuracy.append(dict(label=label,lam=lam,seeds=samples,
            **{k:st.mean(r[k] for r in samples) for k in ['mean_round_s','mean_width','tail50_accuracy_pct','mean_application_bytes']}))
    for d in accuracy:
        d['time_reduction_pct']=100*(1-d['mean_round_s']/accuracy[0]['mean_round_s'])
        d['accuracy_difference_pp']=d['tail50_accuracy_pct']-accuracy[0]['tail50_accuracy_pct']

    old=read('configs/measurements/final_report_evidence_2026-09-26.json')
    for a,b in zip(scenarios,old['koren_system']):
        for arm in ('uniform','widthpath'):assert abs(a[arm]['mean_round_s']-b[arm]['mean_s'])<1e-9
    used.update(['sfl/fed_server.py','sfl/fed_client.py','sfl/plan.py','sfl/policies.py','scripts/analysis/acc_lambda_table.py'])
    manifest=dict(date='2026-09-27',purpose='Full report rewrite: timing, learning quality, and logged controller decisions',
        new_experiments=False,scenarios=scenarios,accuracy_200=accuracy,traces=traces,
        definitions={
            'timing':'Mean of seed means; omit round 0-3; 24-round runs use 3 seeds and 200-round runs use 2 seeds.',
            'accuracy_32':'Accuracy in final saved round 23, then mean of 3 seeds; short-run progress indicator.',
            'accuracy_200':'Mean accuracy over saved rounds 150-199 within each run, then mean of 2 seeds. Not 100 independent repeats.',
            'evaluation':'fed_server evaluates the largest width trained so far, on CIFAR-10 test indices 0-1999.',
            'bytes':'Sum per_client[k][2] over clients per round: application accounting of activation/label/gradient exchange; excludes TCP/IP headers, retransmissions and model aggregation; framing differs slightly by transport.',
            'comparison':'Full-width single-exit baseline versus widthpath with two exits. λ=280 preserves width=1.0 throughout the analyzed body.',
            'scales':'The 32-process timing and 8-process accuracy studies use different network and compute configurations.',
            'mechanism':'Path selection uses measured capacity estimates; splitting weights use configured capacity and shared allocation, not instantaneous per-chunk throughput.'},
        sources=[dict(path=p,sha256=hashlib.sha256((ROOT/p).read_bytes()).hexdigest()) for p in sorted(used)])
    OUT.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'source_count':len(used),'accuracy_200':[{k:v for k,v in r.items() if k!='seeds'} for r in accuracy]},ensure_ascii=True))


if __name__=='__main__':main()
