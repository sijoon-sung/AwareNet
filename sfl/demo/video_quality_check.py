"""Validate final media streams and consistency of the disclosed evaluation data."""
import json
from pathlib import Path
import subprocess
import wave
import imageio_ffmpeg
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/healthcare_enterprise_demo'
video=OUT/'AwareNet_병원_기업_시연.mp4'
ff=imageio_ffmpeg.get_ffmpeg_exe()
decoded=subprocess.run([ff,'-v','error','-i',str(video),'-f','null','-'],capture_output=True,text=True)
assert decoded.returncode==0,decoded.stderr
frames,seconds=imageio_ffmpeg.count_frames_and_secs(str(video))
reader=imageio_ffmpeg.read_frames(str(video));metadata=next(reader);reader.close()
assert metadata['size']==(1920,1080)
assert abs(metadata['fps']-24)<.01
assert 250<seconds<260
with wave.open(str(OUT/'narration.wav'),'rb') as w:
    sr=w.getframerate();audio_seconds=w.getnframes()/sr
    pcm=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(float)/32768
    rms=float(np.sqrt(np.mean(pcm**2)))
assert rms>.005
assert abs(frames/metadata['fps']-audio_seconds)<.05
corp=json.loads((OUT/'enterprise_corpus.json').read_text(encoding='utf-8'))
training={i['q'] for client in corp['train'] for i in client}
heldout={i['q'] for i in corp['evaluation']}
assert training.isdisjoint(heldout)
infer=json.loads((OUT/'enterprise_inference.json').read_text(encoding='utf-8'))
assert [(x['correct'],x['n']) for x in infer['models']]==[(0,18),(6,18),(18,18)]
met=json.loads((OUT/'cnn_verified_metrics.json').read_text(encoding='utf-8'))
assert met['checkpoint_reloaded'] and met['correct']==543 and met['errors']==81
for i,t in enumerate([88,203,247]):
    subprocess.run([ff,'-y','-ss',str(t),'-i',str(video),'-frames:v','1',str(OUT/'frames'/f'encoded_check_{i}.png')],
                   check=True,capture_output=True)
result=dict(video_decode='pass',frames=frames,seconds=seconds,size=metadata['size'],fps=metadata['fps'],
            audio_seconds=audio_seconds,audio_rms=rms,train_test_questions_disjoint=True,
            cnn_checkpoint_prediction_match=True,lora_scores=[(x['correct'],x['n']) for x in infer['models']])
(OUT/'quality_check.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result),flush=True)
