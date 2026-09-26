# VM 클라 판(vmcli) vs HPC 안 기기 판(hpccli) 비교 — 같은 조건(v8mix), 차이는 기기 위치뿐 (2026-09-12)
#   ~/env/bin/python scripts/analysis/vmcli_compare.py [--a vmcli] [--b hpccli] [--skip 10] [--png out/reports/vmcli_compare.png]
# 표: 장면 × (균등, 계획, 차이) 를 두 판 나란히. 라운드 평균은 앞 --skip 라운드 제외(조건 원장 rounds 메모).
import argparse, json, os, statistics as st
ap = argparse.ArgumentParser()
ap.add_argument("--a", default="vmcli"); ap.add_argument("--b", default="hpccli")
ap.add_argument("--scenes", default="normal,traffic"); ap.add_argument("--skip", type=int, default=10)
ap.add_argument("--png", default="out/reports/vmcli_compare.png")
a = ap.parse_args()

def load(tag, pol):
    f = f"out/wp_{tag}_s1_bothmp_{pol}.jsonl"
    if not os.path.exists(f): return None
    rows = [json.loads(l) for l in open(f, encoding="utf-8") if l.strip()]
    return [r for r in rows if "round" in r]

def summ(rows, skip):
    ms = [r["makespan"] for r in rows]
    body = ms[skip:] or ms
    return dict(n=len(ms), mean=st.mean(body), peak=max(ms), total=sum(ms), ms=ms,
                moves=sum(1 for i in range(1, len(rows)) if rows[i].get("paths") != rows[i-1].get("paths")),
                wmean=st.mean([st.mean(list((r.get("plan") or {}).values()) or [1.0]) for r in rows[skip:] or rows]))

names = {"normal": "정상", "traffic": "몰림(R8~19 엣지 1 을 1/4)"}
print(f"{'장면':<22} {'판':<7} {'균등 평균':>9} {'계획 평균':>9} {'차이':>7} {'계획 최고':>9} {'평균 폭':>7} {'경로 변경':>8}  (라운드 {a.skip}+ 평균)")
series = {}
for sc in a.scenes.split(","):
    for tag in (a.a, a.b):
        u, w = load(f"{tag}_{sc}", "uniform"), load(f"{tag}_{sc}", "widthpath")
        if not u or not w: print(f"{names.get(sc, sc):<22} {tag:<7} (없음)"); continue
        su, sw = summ(u, a.skip), summ(w, a.skip)
        series[(sc, tag)] = (su["ms"], sw["ms"])
        print(f"{names.get(sc, sc):<22} {tag:<7} {su['mean']:>8.1f}s {sw['mean']:>8.1f}s {100*(sw['mean']/su['mean']-1):>+6.0f}% {sw['peak']:>8.1f}s {sw['wmean']:>7.2f} {sw['moves']:>8d}")
try:
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    from matplotlib import font_manager
    for fp in ("/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "C:/Windows/Fonts/malgun.ttf"):
        if os.path.exists(fp): font_manager.fontManager.addfont(fp); plt.rcParams["font.family"] = font_manager.FontProperties(fname=fp).get_name(); break
    plt.rcParams["axes.unicode_minus"] = False
    scs = [s for s in a.scenes.split(",") if any(k[0] == s for k in series)]
    fig, axs = plt.subplots(1, len(scs), figsize=(6.5 * len(scs), 4), squeeze=False)
    for ax, sc in zip(axs[0], scs):
        for tag, ls in ((a.a, "-"), (a.b, "--")):
            if (sc, tag) not in series: continue
            u, w = series[(sc, tag)]
            ax.plot(range(len(u)), u, ls, color="#888", label=f"{tag} 균등")
            ax.plot(range(len(w)), w, ls, color="#1f6feb", label=f"{tag} 계획")
        ax.set_title(names.get(sc, sc)); ax.set_xlabel("라운드"); ax.set_ylabel("라운드 시간 (s)"); ax.grid(alpha=.3); ax.legend(fontsize=8)
    os.makedirs(os.path.dirname(a.png), exist_ok=True); fig.tight_layout(); fig.savefig(a.png, dpi=120); print("그림", a.png)
except Exception as e:
    print("그림 생략:", e)
