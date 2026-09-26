# scripts/exp — 실험 드라이버 (조건은 conditions.json 에서만)

모든 드라이버는 `COND=<이름>` 으로 조건 원장을 읽는다(`cond.py --env`). 숫자를 스크립트에 직접 쓰지 않는다. 결과는 `out/wp_<COND>_s<시드>_<팔>_{uniform,widthpath}.jsonl` + `.args.json`(실행 인자) + `.profile.json`(인지 결과).

| 드라이버 | 무엇 | 결과 문서 |
|---|---|---|
| `run_real.sh` | 실회선 리그(역터널 4개 = 엣지 4개) 위에서 균등 vs 계획 한 조건 (`REUSE_UNIFORM`, `ONLY`, `UNIFORM_MP`) | 데이터_기록_2026-09-07.md |
| `run_scen32.sh` + `scenario_perturb.sh` | **32대 시나리오** — 정상·몰림·연산 느림·변동·λ 18/280 (교란은 감시자가 tc 로) | 실험_시나리오_32대_사전등록.md, 보고_실험종합_2026-09-10.md |
| `after_batch_rerun.sh` | 리그가 빌 때까지 기다렸다 지정 장면의 계획 팔만 재실행 (`SCEN`, `ARCHIVE`) | — |
| `verify_scen32.sh` | 32대 실행 전 검증(리그 자가검사·스모크·드라이런) | — |
| `verify_demo.sh` | 실증 플랫폼 자동 검증(라운드·교란 tc·복구·정리) | 보고_실험종합_2026-09-10.md §7 |
| `run_combo.sh` | 결합 실험(8대 혼합, 고정 목표 D=10 s, 팔 6개, ρ 0.5/1/2) | 실험_결합_3번_사전등록.md |
| `run_real_sweep.sh` | 망 손잡이 스윕(엣지 바꾸기·분할, ρ 0.5/1/2) | 데이터_기록_2026-09-07.md (9/8) |
| `run_micro_acc.sh` | 즉시 내보내기 정확도 절제(m=1/2/4, BN/GN) | 데이터_기록_2026-09-07.md (9/8~9) |
| `measure_r32.sh` | 32대 조건의 사전 측정 | — |
| `run_widthpath.sh` | 루프백(hairpin) 리그 폭×경로 실험 (9/6~7 절제·망 효과) | 실험_절제_조건표_복원.md, 데이터_기록_2026-09-06.md |
| `run_net_effect.sh` | 망 효과(엣지/분할/즉시 내보내기) 루프백 | 데이터_기록_2026-09-07.md (9/7) |
| `ablate_5.sh`, `ablate_rerun_width.sh` | 절제 5판·폭만 재실행 | 실험_절제_5판_사전등록.md |
| `rw_long.sh`, `run_tracks.sh` | 폭별 정확도 400R, 연산/망 효과 두 갈래 | 데이터_기록_2026-09-06.md |
| `run_l3net.sh`, `run_mp.sh` | 언어모델(LoRA) 실소켓 경로, 분할 전송 검증 | 실험_L시리즈.md, 설계_멀티패스_분할전송.md |
| `hpc_launch.sh`, `hpc_fetch.sh`, `vm_deploy.sh`, `vm_exp.sh` | HPC/VM 배포·실행·회수 | 실험환경_VM_HPC.md |

회선 측정은 `scripts/measurement/`(line_scale*, real_selftest, rig_selftest), 표·시각화·재생은 `scripts/analysis/`(scen32_report/viz, combo_table, replay_plan, trace_sense, report_html_0910).
