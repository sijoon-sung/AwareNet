"""Verify archived timing and collect actual training records for the silent cut."""
from pathlib import Path
import hashlib
import json
import statistics

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'output/healthcare_enterprise_demo'
OUT=ROOT/'output/demo_short'

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    published=read(ROOT/'configs/measurements/report_metrics_revised.json')
    files=[]; scenarios=[]; runs={}
    for condition in ['normal','traffic','slow','vary']:
        item={'condition':condition,'label':{'normal':'정상','traffic':'트래픽 몰림','slow':'연산 지연','vary':'용량 변동'}[condition]}
        for policy in ['uniform','widthpath']:
            seeds=[]
            for seed in [1,2,3]:
                path=ROOT/f'out/wp_scen32_{condition}_s{seed}_bothmp_{policy}.jsonl'
                records=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
                records=[row for row in records if 'round' in row]
                assert [r['round'] for r in records]==list(range(24))
                files.append(path)
                args_path=path.with_suffix('.args.json')
                args=read(args_path)
                assert args['clients']==32 and args['rounds']==24 and args['seed']==seed
                assert args['multipath']==(policy=='widthpath')
                files.append(args_path)
                seeds.append(statistics.mean(r['makespan'] for r in records[4:]))
                if seed==1 and condition=='traffic':
                    runs[policy]=[{k:row[k] for k in ['round','makespan','acc','plan','paths','elapsed']} for row in records]
            item[policy]=statistics.mean(seeds)
        item['reduction_pct']=100*(1-item['widthpath']/item['uniform'])
        reference=next(r for r in published['scenarios'] if r['condition']==condition)
        assert abs(item['reduction_pct']-reference['time_reduction_pct'])<1e-9
        item['accuracy_delta_pp']=reference['final_accuracy_difference_pp']
        scenarios.append(item)
    for policy in runs:
        for i,row in enumerate(runs[policy]):
            row['changes']=[]
            if i:
                before=runs[policy][i-1]
                for cid in sorted(row['plan'],key=lambda x:int(x[1:])):
                    if row['paths'][cid]!=before['paths'][cid] or row['plan'][cid]!=before['plan'][cid]:
                        row['changes'].append(dict(client=cid,path_before=before['paths'][cid],path_after=row['paths'][cid],
                                                  width_before=before['plan'][cid],width_after=row['plan'][cid]))
    data={'cnn':read(SRC/'cnn_history.json'),'cnn_metrics':read(SRC/'cnn_verified_metrics.json'),
          'lora':read(SRC/'enterprise_history.json'),'lora_inference':read(SRC/'enterprise_inference.json'),
          'network_runs':runs,'network_summary':scenarios,
          'comparison':{'metric':'round completion time, not time to target accuracy','baseline':'full width, fixed assignment, one connection',
                        'awarenet':'width/path adaptation, two connections','clients':32,'rounds':24,'seeds':3,'omit_rounds':[0,1,2,3],
                        'data':'archived CIFAR-10/KOREN experiment; distinct from local X-ray/LoRA demonstrations'},
          'chapters':[{'start':0,'title':'CNN 학습','source':'local recorded training'},
                      {'start':24,'title':'X-ray 추론','source':'local recorded inference'},
                      {'start':34,'title':'LoRA 학습','source':'local recorded training'},
                      {'start':54,'title':'업무 질문','source':'local recorded inference'},
                      {'start':66,'title':'KOREN 시스템 작동·시간 비교','source':'archived real network logs'},
                      {'start':98,'title':'조건별 시간 단축','source':'means recomputed from 24 raw logs'}]}
    (OUT/'data.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    files += [SRC/n for n in ['cnn_history.json','cnn_verified_metrics.json','enterprise_history.json','enterprise_inference.json','cnn_predictions.npz']]
    manifest={'inputs':[{'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files],
              'raw_timing_logs':24,'all_published_means_verified':True,'new_training':False,'duration_seconds':112,'audio':False}
    (OUT/'sources.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(scenarios,ensure_ascii=False))

if __name__=='__main__':main()
