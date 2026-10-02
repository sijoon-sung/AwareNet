'use strict';
const C={ink:'#223642',muted:'#5f737c',blue:'#356b8c',teal:'#388980',rose:'#af6878',line:'#b8c9d1',pale:'#f3f7f9',gray:'#8798a2'};
const colors=[C.blue,C.teal,C.rose],q=s=>document.querySelector(s),esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const f=x=>x.toFixed(1),sec=x=>`${String(Math.floor(x/60)).padStart(2,'0')}:${String(Math.floor(x%60)).padStart(2,'0')}`,image=n=>`assets/demo/viewer-images/${n}.png`;
let data,t=0,playing=false,last=performance.now(),drawn=-1;
const txt=(x,y,s,size=22,c=C.ink,weight=400,anchor='start')=>`<text x="${x}" y="${y}" font-size="${size}" fill="${c}" font-weight="${weight}" text-anchor="${anchor}">${esc(s)}</text>`;
const rect=(x,y,w,h,fill='white',stroke=C.line,r=5)=>`<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${r}" fill="${fill}" stroke="${stroke}" stroke-width="1.6"/>`;
const line=(d,c=C.blue,arrow=false,dash=false)=>`<path d="${d}" fill="none" stroke="${c}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" ${arrow?`marker-end="url(#a${c.slice(1)})"`:''} ${dash?'stroke-dasharray="6 6"':''}/>`;
const svg=(w,h,body,label)=>`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(label)}"><defs>${Object.values(C).map(c=>`<marker id="a${c.slice(1)}" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto-start-reverse"><path d="M1 1 L7 4 L1 7" fill="none" stroke="${c}" stroke-width="1.5"/></marker>`).join('')}</defs>${body}</svg>`;
const group=(x,y,s,body)=>`<g transform="translate(${x} ${y}) scale(${s})">${body}</g>`;
function rack(x,y,s=1,c=C.blue){return group(x,y,s,line('M0 10 L14 0 H83 V105 L69 116 H0 Z',c)+line('M0 10 H69 L83 0 M69 10 V116',c)+[22,49,76].map(yy=>rect(8,yy,52,19,'white',c,2)+`<circle cx="16" cy="${yy+9}" r="2.3" fill="${c}"/>`+line(`M25 ${yy+7} H50 M25 ${yy+12} H43`,c)).join(''));}
function hospital(x,y,s=1){return group(x,y,s,rect(0,20,84,70,C.pale,C.blue,1)+rect(25,0,34,90,'white',C.blue,1)+line('M42 8 V25 M34 16 H50',C.rose)+[39,57].map(yy=>[9,67].map(xx=>rect(xx,yy,9,10,'white',C.blue,0)).join('')).join('')+rect(35,68,14,22,C.pale,C.blue,0));}
function documentIcon(x,y,s=1,c=C.blue){return group(x,y,s,line('M0 0 H48 L66 18 V85 H0 Z',c)+line('M48 0 V18 H66 M13 34 H52 M13 46 H52 M13 58 H45 M13 70 H39',c));}
function network(x,y,s=1){let b='';for(const a of [15,45,75])for(const v of [25,65])b+=line(`M8 ${a} L48 ${v}`,C.line);for(const a of [25,65])for(const v of [15,45,75])b+=line(`M48 ${a} L88 ${v}`,C.line);for(const [xx,ys] of [[8,[15,45,75]],[48,[25,65]],[88,[15,45,75]]])for(const yy of ys)b+=`<circle cx="${xx}" cy="${yy}" r="6" fill="white" stroke="${C.blue}" stroke-width="1.8"/>`;return group(x,y,s,b);}
function router(x,y,c=C.blue){return `<circle cx="${x}" cy="${y}" r="22" fill="${C.pale}" stroke="${c}" stroke-width="1.8"/>`+line(`M${x-13} ${y-7} H${x+11} L${x+6} ${y-12} M${x+11} ${y+7} H${x-13} L${x-8} ${y+12}`,c);}
const channels=(x,y,w,c=C.blue)=>Array.from({length:8},(_,i)=>rect(x+i*14,y,10,20,i<Math.round(w*8)?c:'#e5ecef','none',1)).join('');
const panel=(title,body,cl='')=>`<section class="panel ${cl}"><h2>${title}</h2><div class="inside">${body}</div></section>`;
const heading=(title,subtitle,right='')=>`<h1>${title}</h1><p class="subtitle">${subtitle}<span class="right">${right}</span></p>`;
const trace=(title,hint,rows)=>`<div class="trace"><div><h3>${title}</h3><div class="hint">${hint}</div></div><pre>${rows.join('\n')}</pre></div>`;
function chart(series,{xmin=0,xmax=20,ymin=0,ymax=100,ticks=[0,50,100],log=false,w=690,h=330}={}){
 const L=75,R=20,T=30,B=53,X=x=>L+(x-xmin)/(xmax-xmin)*(w-L-R),Y=v=>h-B-(Math.max(ymin,Math.min(ymax,log?Math.log10(Math.max(v,1e-7)):v))-ymin)/(ymax-ymin)*(h-T-B);
 let b='';for(const v of ticks){const py=Y(log?10**v:v);b+=`<line x1="${L}" y1="${py}" x2="${w-R}" y2="${py}" stroke="#e4ecef"/>`+txt(8,py+7,log?'1e'+v:v,19,C.muted);}
 for(const [points,c] of series){const pts=points.filter(([x])=>x>=xmin).map(([x,y])=>[X(x),Y(y)]);if(pts.length>1)b+=`<polyline fill="none" stroke="${c}" stroke-width="3" points="${pts.map(p=>p.join(',')).join(' ')}"/>`;if(pts.length){const [x,y]=pts.at(-1);b+=`<circle cx="${x}" cy="${y}" r="4" fill="${c}"/>`;}}
 for(const x of [xmin,Math.floor((xmin+xmax)/2),xmax])b+=txt(X(x),h-24,x,19,C.muted,400,'middle');b+=txt(w-5,h-1,'라운드',18,C.muted,400,'end');return svg(w,h,b,'기존 실행 기록의 라운드별 측정값');
}
function learningFlow(row,kind){
 let b='',cnn=kind==='cnn';
 for(let i=0;i<3;i++){
  const y=16+i*137,c=row.clients[i];b+=rect(10,y,410,118,'white',C.line);
  b+=cnn?hospital(25,y+24,.65):documentIcon(34,y+20,.82,colors[i]);
  if(cnn)b+=`<image x="97" y="${y+19}" width="77" height="77" preserveAspectRatio="xMidYMid meet" href="${image('client_'+i+'_0')}"/>`;
  const xx=cnn?190:118;b+=txt(xx,y+33,cnn?'병원 '+ 'ABC'[i]:['운영','고객지원','보안'][i],23,C.ink,700);
  b+=cnn?channels(xx,y+51,c.width,colors[i])+txt(xx+127,y+68,c.width.toFixed(2),20,C.muted):txt(xx,y+66,['장애 대응 지침','고객 응답 기준','로그 공유 규정'][i],20,C.muted);
  b+=txt(xx,y+100,'loss '+c.loss.toFixed(4),20,colors[i])+line(`M420 ${y+59} H454`,colors[i]);
 }
 b+=line('M454 75 V349 M454 212 H558',C.blue,true)+txt(515,188,'활성값',20,C.blue,400,'middle')+rack(589,115,1.02)+network(719,125,1.1);
 b+=txt(705,272,'서버 뒷부분 학습',24,C.ink,700,'middle')+line('M746 303 V364 H454 V249',C.rose,true)+txt(655,396,'기울기 반환',21,C.rose,400,'middle');
 b+=line('M827 178 H878',C.teal,true)+rect(895,132,103,109,C.pale,C.line)+txt(946,174,'연합',22,C.ink,700,'middle')+txt(946,208,'집계',22,C.ink,700,'middle')+txt(925,288,'라운드 '+row.round,20,C.muted,400,'middle');
 return svg(1010,430,b,'클라이언트 학습, 서버 연산, 기울기 반환 및 라운드별 연합 집계');
}
function intro(){return heading('모델 크기와 전송 경로를 함께 조절하는 AwareNet','클라이언트의 연산 부담과 네트워크 경합을 함께 고려합니다.')+`<div class="overview-grid"><img class="architecture" src="assets/submission/architecture.svg?v=20261002r1" alt="클라이언트, KOREN 중계, 학습 서버와 AwareNet 스케줄러"><div class="steps"><div class="step" style="opacity:${t>0.5?1:0.45}"><h2><span class="number">1</span>연산·전송 상태 관측</h2><p>완료 시간과 전송량을<br>다음 계획에 반영</p></div><div class="step"><h2><span class="number">2</span>경로와 모델 크기 결정</h2><p>경로 개선 후의 시간 이득으로<br>폭 축소 필요성을 판단</p></div><div class="step"><h2><span class="number">3</span>학습·전송·집계</h2><p>활성값과 기울기를 교환하고<br>라운드 종료 후 모델 갱신</p></div></div></div>`;}
function cnnTrain(){
 const hist=data.cnn,wall=hist.at(-1).elapsed*Math.min(1,(t-9)/16),row=hist.slice(1).filter(r=>r.elapsed<=wall).at(-1)||hist[1],r=row.round;
 const logs=row.clients.map(c=>`client ${c.client}   width ${c.width.toFixed(2)}   loss ${c.loss.toFixed(6)}   activation [${c.activation_shape.join(', ')}]`);logs.push(`<b>round ${String(r).padStart(2,'0')}   집계 후 정확도 ${f(row.accuracy*100)}%   기록 시간 ${f(row.elapsed)}s</b>`);
 return heading(`CNN 학습 · ${r} / 20 라운드`,'공개 X-ray를 세 가상 병원 클라이언트로 나누어 학습','ResNet-18 · cut 2 · batch 16')+`<div class="grid">${panel('클라이언트 학습 → 서버 연산 → 연합 집계',learningFlow(row,'cnn'),'train-panel')}${panel('집계 후 시험 정확도',`<p class="metric">${f(row.accuracy*100)}%<small>시험 영상 624장</small></p>${chart([[hist.slice(0,r+1).map(v=>[v.round,v.accuracy*100]),C.blue]])}<p class="muted" style="font-size:20px;margin:8px 0">채널 비율 0.50 / 0.75 / 1.00</p>`,'train-panel')}</div>`+trace('학습 실행 기록','cnn_history.json',logs);
}
function cnnInfer(){
 const c=data.cnn_metrics.cases[t<31?0:1];
 const preds=[['학습 전',c.initial_probs],['연합학습 후',c.final_probs]].map(([label,pr],i)=>`<div class="pred ${i?'result':'base'}"><h3>${label}</h3>${pr.map((p,k)=>`<div class="prob"><span>${['정상','폐렴'][k]}</span><div class="track"><i style="width:${100*p}%;background:${i?C.blue:C.gray}"></i></div><span class="mono">${f(p*100)}%</span></div>`).join('')}<div class="diagnosis">예측: <span style="color:${i?C.blue:C.muted}">${pr[1]>pr[0]?'폐렴':'정상'}</span></div></div>`).join('');
 return heading('같은 영상에 대한 학습 전·후 예측','저장된 전역 모델을 다시 불러와 시험 영상에 적용','CNN · 실제 추론 결과')+`<div class="inference-grid">${panel('시험 영상',`<img class="xray" src="${image('test_'+c.index)}" alt="공개 시험 X-ray"><p style="margin:17px 0 0;font-size:23px">데이터 라벨: ${['정상','폐렴'][c.label]}</p>`)}${panel('모델 예측 확률',`<div class="two">${preds}</div><div class="model-flow">${svg(200,65,hospital(4,7,.5)+hospital(64,7,.5)+hospital(124,7,.5),'세 병원의 공동 학습').replace('<svg ','<svg style="width:200px" ')}<span>세 클라이언트의 갱신 → 전역 모델 → 같은 입력으로 확인</span></div>`)}</div><div class="strip"><span>전체 시험 세트</span><strong>543 / 624 일치</strong><strong>87.0%</strong><span class="muted">오분류 81장</span></div>`;
}
function loraTrain(){
 const hist=data.lora.federated,wall=hist.at(-1).elapsed*Math.min(1,(t-35)/14),row=hist.filter(r=>r.elapsed<=wall).at(-1)||hist[0],r=row.round;
 const logs=row.clients.map((c,i)=>`${['운영    ','고객지원','보안    '][i]}   loss ${c.loss.toFixed(6)}   LoRA rank 16`);logs.push(`<b>round ${String(r).padStart(2,'0')}   앞단 어댑터 평균 · ${row.adapter_bytes.toLocaleString('en-US')} bytes   기록 시간 ${f(row.elapsed)}s</b>`);
 return heading(`LoRA 학습 · ${r} / 16 라운드`,'서로 다른 부서의 지침을 학습하고 앞단 어댑터를 집계','Qwen2.5-0.5B · 고정 rank 16')+`<div class="grid">${panel('부서별 어댑터 학습 → 서버 연산 → 연합 집계',learningFlow(row,'lora'),'train-panel')}${panel('클라이언트별 학습 손실',`<div class="legend">${['운영','고객지원','보안'].map((s,i)=>`<span><i style="background:${colors[i]}"></i>${s}</span>`).join('')}</div>${chart([0,1,2].map(i=>[hist.slice(0,r).map(rr=>[rr.round,rr.clients[i].loss]),colors[i]]),{xmin:1,xmax:16,ymin:-6,ymax:1,ticks:[1,-1,-3,-6],log:true})}<p class="muted" style="font-size:19px;margin:8px 0">손실은 로그 축으로 표시</p>`,'train-panel')}</div>`+trace('학습 실행 기록','enterprise_history.json',logs);
}
function loraInfer(){
 const ix=t<56?6:12,local=data.lora_inference.models[1].questions[ix],fed=data.lora_inference.models[2].questions[ix];
 return heading('부서 간 공동 학습 후, 업무 질문에 답하기','학습한 규정을 다른 표현으로 질문한 실제 생성 결과','저장된 실제 생성 결과 · 텍스트 표시만 압축 재생')+`<div class="question"><small>평가 질문 · ${fed.fact}</small>${esc(fed.q)}</div><div class="two">${[local,fed].map((r,i)=>panel(i?'운영 + 고객지원 + 보안 연합학습':'운영 부서만 학습',`<div class="answer-icon">${svg(90,100,documentIcon(10,0,1,i?C.teal:C.gray),'부서별 업무 지침')}</div><p class="answer">${esc(r.answer.slice(0,Math.ceil(r.answer.length*Math.min(1,Math.max(0,(t-(ix===6?51:56))/1.2)))))}</p><div class="status ${i?'good':''}">규정과 ${r.correct?'일치':'불일치'}</div><p class="muted" style="font-size:19px">생성 시간 ${r.seconds.toFixed(2)}초</p>`,'answer-panel')).join('')}</div><div class="strip"><span>18개 질문 전체 비교</span><strong>기본 0/18</strong><strong>단독 6/18</strong><strong style="color:${C.teal}">연합 18/18</strong></div>`;
}
function korenPurpose(){
 return heading('KOREN에서 확인한 것과 확장할 수 있는 것','관리 가능한 연구 환경에서 실제 학습 트래픽을 반복 측정')+`<div class="koren-purpose"><section class="panel purpose"><div class="icon">${svg(150,140,router(40,60)+line('M65 60 H103',C.blue,true)+rack(111,29,.52),'연구망과 관리 노드')}</div><h2>통제 가능한 실험 조건</h2><p>동일한 연구망에서 용량과 교란 시점을 설정하고 정책을 반복 비교</p></section><section class="panel purpose"><div class="icon">${svg(150,140,rack(8,19,.72)+line('M75 58 H104',C.teal,true)+rack(114,33,.47,C.teal),'원격 VM과 HPC 연계')}</div><h2>원격 VM·HPC 연동</h2><p>실제 전송·큐·재조립과 서버 연산을 포함한 완료 시간 측정</p></section><section class="panel purpose"><div class="icon">${svg(150,140,network(12,26,1.3),'동시 전송의 경합')}</div><h2>동시 전송의 병목 관측</h2><p>8 → 32 클라이언트<br>배치 왕복 중앙값<br>0.41초 → 2.18초</p></section></div><div class="next-network"><div><h2>후속 확장</h2><p style="font-size:20px;margin-top:14px">이번 실험에는 미적용</p></div><div><h3>T-SDN 전용회선</h3><p>회선 자원 확보 → 경합 완화<br>완료 시간 예측의 안정화 기대</p></div><div><h3>L2VPN</h3><p>다기관 논리망 구성<br>클라이언트·중계 배치 확장</p></div></div>`;
}
function topology(row){
 let b=txt(185,28,'32개 논리 클라이언트',22,C.ink,700,'middle'),counts=[0,0,0,0];
 for(let i=0;i<32;i++){
  const x=12+(i%4)*92,y=51+Math.floor(i/4)*43,key='c'+i,w=row.plan[key]??1,path=String(row.paths[key]||'');
  for(const n of path.split('+'))if(+n>=1&&+n<=4)counts[+n-1]++;
  b+=rect(x,y,82,34,'white',C.line,3)+txt(x+7,y+23,key,17)+rect(x+37,y+12,36,9,'#e5ecef','none',1)+rect(x+37,y+12,36*w,9,C.blue,'none',1);
 }
 b+=line('M380 217 H422 V106 H483',C.blue,true)+line('M422 217 V318 H483',C.teal,true);
 for(let i=0;i<2;i++){
  const y=i?250:38,c=i?C.teal:C.blue,congested=i===0&&row.round>=8&&row.round<20;b+=rect(495,y,245,154,congested?'#fff2ed':C.pale,congested?'#b66b32':C.line,8)+rack(512,y+32,.69,c)+txt(611,y+30,'VM '+(i+1),22,C.ink,700);if(congested)b+=txt(515,y+177,'중계 용량 축소 구간',17,'#b66b32',700);
  for(let j=0;j<2;j++){let yy=y+68+j*51;b+=router(617,yy,c)+txt(648,yy+7,'E'+(i*2+j+1)+' · '+counts[i*2+j]+'개',18,C.muted);}
 }
 b+=line('M740 112 H784 V217 H831',C.blue,true)+line('M740 325 H784 V217',C.teal)+rack(850,143,.90)+txt(895,278,'학습 서버',22,C.ink,700,'middle');
 b+=txt(185,425,'막대: 채널 비율',18,C.muted,400,'middle')+txt(616,442,'연결 배정은 해당 라운드 로그 기준',18,C.muted,400,'middle');
 return svg(980,453,b,'32개 클라이언트의 실제 폭과 네 중계에 대한 연결 배정 수');
}
function koren(){
 const rr=Math.min(23,4+Math.floor((t-73)/1.3)),runs=data.network_runs,row=runs.widthpath[rr];
 const mean=p=>runs[p].slice(4,rr+1).reduce((s,r)=>s+r.makespan,0)/(rr-3),u=mean('uniform'),v=mean('widthpath');
 const changes=[];for(const r of runs.widthpath.slice(Math.max(0,rr-2),rr+1))for(const c of r.changes)changes.push(`r${r.round}  ${c.client.padEnd(4)}  중계 ${c.path_before} → ${c.path_after}   폭 ${c.width_before.toFixed(2)} → ${c.width_after.toFixed(2)}`);
 const cap=rr<8?'교란 전':rr<20?'8R 용량 축소 → 실제 중계 배정 변화':'20R 용량 복구 → 상태 재관측';
 return heading(`KOREN 동작 기록 · ${rr} 라운드`,'트래픽 몰림 조건: '+cap,'CIFAR-10 · 32 clients · seed 1')+`<div class="grid network-grid">${panel('채널 비율과 중계 연결 배정',topology(row),'network-panel')}${panel('라운드 완료 시간 · 초',`<div class="legend"><span><i class="gray"></i>기준 방식</span><span><i></i>AwareNet</span></div>${chart(['uniform','widthpath'].map((p,i)=>[runs[p].slice(0,rr+1).map(r=>[r.round,r.makespan]),i?C.blue:C.gray]),{xmin:4,xmax:23,ymin:0,ymax:200,ticks:[0,100,200],w:720,h:323})}<p class="muted" style="font-size:19px;margin:8px 0">서로 다른 실행을 라운드 번호로 정렬</p>`,'network-panel')}</div><div class="strip" style="padding:14px 24px;margin-top:18px"><span>현재까지 평균 · r4–r${rr}</span><strong>${f(u)}초 → ${f(v)}초</strong><strong>${f(100*(1-v/u))}% 단축</strong></div>`+trace('설정 변경 기록','최근 라운드의 실제 결정',changes.length?changes.slice(-2):['현재 모델 폭과 경로 배정 유지']);
}
function summary(){
 let b='';for(let i=0;i<4;i++){
  const r=data.network_summary[i],y=22+i*125,scale=9.15*Math.min(1,Math.max(0,(t-101-i*.1)/1.2));b+=txt(5,y+50,r.label,27,C.ink,500);
  b+=rect(265,y+8,r.uniform*scale,24,C.gray,'none',2)+txt(285+r.uniform*scale,y+30,f(r.uniform)+'초',24,C.ink,700);
  b+=rect(265,y+53,r.widthpath*scale,24,C.blue,'none',2)+txt(285+r.widthpath*scale,y+76,f(r.widthpath)+'초',24,C.blue,700)+txt(1700,y+64,f(r.reduction_pct)+'%',36,C.blue,500,'end');
  if(i<3)b+=`<line x1="0" y1="${y+108}" x2="1720" y2="${y+108}" stroke="#e5ecef"/>`;
 }
 return heading('기준 방식 대비 라운드 완료 시간','KOREN · 24라운드 × 3시드 · 초기 4라운드 제외','단축률 = 1 − AwareNet / 기준 방식')+`<div class="result-legend"><span><i style="background:${C.gray}"></i>기준: 전체 채널 · 고정 배정 · 연결 1개</span><span><i style="background:${C.blue}"></i>AwareNet: 폭·경로 조정 · 연결 2개</span></div><section class="panel results-panel">${svg(1750,525,b,'네 조건의 기준 방식과 AwareNet 라운드 시간 및 단축률')}</section><div class="summary-note"><span>실제 실행 로그 24개 · 연결 수 차이를 포함한 전체 구성 비교</span></div><div class="strip"><span>관측 → 경로·분할 배분 → 필요한 클라이언트의 폭 조절</span><span class="muted">시간과 학습 품질을 함께 평가</span></div>`;
}

function ending(){return heading('AwareNet','분할 연합학습을 위한 모델과 네트워크의 적응형 스케줄링')+`<div style="padding:110px 70px"><h2 style="font-size:40px;font-weight:500">코드와 실행 기록 공개</h2><p style="font-size:34px;margin-top:34px">github.com/sijoon-sung/AwareNet</p><p style="font-size:25px;color:${C.muted};margin-top:50px">모델·전송 코드 · 시드별 원로그 · 실험 조건 · 재집계 코드</p><p style="font-size:25px;color:${C.muted};margin-top:25px">충남대학교 · 성시준 · 석태경</p></div>`;}

function render(){
 const active=t<9?0:t<35?1:t<61?2:t<101?3:4;let key,body,source;
 if(t<9){key='intro';body=intro();source='시스템 구조 · 다음 화면부터 기존 CNN·LoRA 학습과 KOREN 측정 기록을 재생';}
 else if(t<27){key='cnn';body=cnnTrain();source='2026-09-29 로컬 학습 · RTX 3080 · PneumoniaMNIST+ 공개 영상 4,708장 학습 / 624장 시험';}
 else if(t<35){key='cnn-result';body=cnnInfer();source='MedMNIST+ / Yang et al. · CC BY 4.0 · 64×64 확대 표시 · 공개 연구용 데이터 · 임상 검증 제외';}
 else if(t<51){key='lora';body=loraTrain();source='2026-09-29 로컬 학습 · RTX 3080 · 가상 기업 지침 · 고정 LoRA 랭크 · 앞단 어댑터 평균 / 서버 뒷단 공동 갱신';}
 else if(t<61){key='lora-result';body=loraInfer();source='저장 모델의 실제 생성 결과 · 학습한 규정 9개를 다른 문장으로 질문한 평가';}
 else if(t<73){key='koren-purpose';body=korenPurpose();source='기존 KOREN 측정 기록과 NIA KOREN 이용안내서 · T-SDN·L2VPN의 효과는 후속 비교 대상';}
 else if(t<101){key='koren';body=koren();source='기존 KOREN 실측 · 앞의 로컬 학습과 별도 실행 · 기준 연결 1개 / AwareNet 연결 2개의 전체 구성 비교';}
 else if(t<109){key='summary';body=summary();source='원로그 24개 재집계 · 연결 수 차이를 포함한 전체 구성 비교 · 측정 지표는 라운드 완료 시간';}
 else{key='ending';body=ending();source='Open source & evidence · 공개 코드와 원자료는 홈페이지에서 확인';}
 const rate=key==='cnn'?`실행 로그 약 ${Math.round(data.cnn.at(-1).elapsed/16)}배속`:key==='lora'?`실행 로그 약 ${Math.round(data.lora.federated.at(-1).elapsed/14)}배속`:key==='koren'?'실행 로그 · 라운드당 1.3초 압축':key==='lora-result'?'실제 생성 결과 · 표시 재생':'저장된 실행 기록';
 q('.replay-label').textContent=rate;
 q('#content').innerHTML=body;q('#source').textContent=source;q('#clock').textContent=sec(t)+' / 01:52';q('#seek').value=t;q('#progress').style.width=(t/112*100)+'%';document.querySelectorAll('nav button').forEach((b,i)=>b.classList.toggle('active',i===active));window.viewerScene=key;
}
function setTime(v){t=Math.max(0,Math.min(112,v));render();drawn=t;window.replayDone=t>=112;}
q('#play').onclick=()=>{if(t>=112)setTime(0);playing=!playing;last=performance.now();q('#play').textContent=playing?'일시정지':'재생';};
q('#reset').onclick=()=>setTime(0);q('#seek').oninput=e=>setTime(+e.target.value);document.querySelectorAll('[data-seek]').forEach(b=>b.onclick=()=>setTime(+b.dataset.seek));
function resize(){const s=Math.min(innerWidth/1920,innerHeight/1080);q('#stage').style.transform=`scale(${s})`;q('#stage').style.left=Math.max(0,(innerWidth-1920*s)/2)+'px';}addEventListener('resize',resize);resize();
function tick(now){if(playing){t=Math.min(112,t+(now-last)/1000);if(t-drawn>=.18){render();drawn=t;}if(t>=112){playing=false;render();q('#play').textContent='재생';window.replayDone=true;}}last=now;requestAnimationFrame(tick);}
fetch('assets/demo/viewer-data.json').then(r=>{if(!r.ok)throw Error('기록을 불러오지 못했습니다.');return r.json();}).then(d=>{data=d;render();window.viewerReady=true;window.viewerSeek=setTime;requestAnimationFrame(tick);}).catch(e=>q('#content').textContent=e.message);
