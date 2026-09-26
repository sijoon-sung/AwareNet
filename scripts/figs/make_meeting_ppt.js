// 지도교수 미팅 발표자료 — 설계 변경 경위·실험 결과·계획·논의 (27장)
const pptxgen = require("pptxgenjs");
const path = require("path");

const INK = "1D2D3D", TEAL = "0F766E", TEALL = "D7EAE8", TEALBG = "F2F7F6";
const ORG = "B45309", GRAY = "5A6B7A", LINE = "C9D2D9";
const F = "Malgun Gothic";
const FIG = p => path.join(__dirname, "..", "..", "out", "fig", p);

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5

let NO = 0;
function base(dark = false) {
  const s = pres.addSlide();
  s.background = { color: dark ? INK : "FFFFFF" };
  NO++;
  if (!dark) s.addText(String(NO), { x: 12.7, y: 7.05, w: 0.5, h: 0.35, fontFace: F,
    fontSize: 10, color: GRAY, align: "right", isTextBox: true, margin: 0 });
  return s;
}
function head(s, title, sub) {
  s.addText(title, { x: 0.6, y: 0.42, w: 12.1, h: 0.75, fontFace: F, fontSize: 26,
    bold: true, color: INK, isTextBox: true, margin: 0 });
  if (sub) s.addText(sub, { x: 0.6, y: 1.14, w: 12.1, h: 0.4, fontFace: F,
    fontSize: 13, color: GRAY, isTextBox: true, margin: 0 });
}
function chip(s, x, y, d, txt, fill, fs) {
  s.addShape("ellipse", { x, y, w: d, h: d, fill: { color: fill }, line: { type: "none" } });
  s.addText(txt, { x: x - 0.2, y, w: d + 0.4, h: d, fontFace: F, fontSize: fs || 14,
    bold: true, color: "FFFFFF", align: "center", valign: "middle", isTextBox: true, margin: 0 });
}
function card(s, x, y, w, h, fill, lineC) {
  s.addShape("roundRect", { x, y, w, h, rectRadius: 0.07, fill: { color: fill },
    line: lineC ? { color: lineC, width: 1.2 } : { type: "none" },
    shadow: { type: "outer", color: "9AA7B0", blur: 6, offset: 2, angle: 90, opacity: 0.25 } });
}
function rows(s, items, x, y, w, opt) {
  const o = Object.assign({ gap: 0.62, fs: 14, color: INK }, opt || {});
  s.addText(items.map((t, i) => ({ text: t, options: { bullet: { code: "2022", indent: 12 },
    breakLine: i < items.length - 1, paraSpaceAfter: 8 } })),
    { x, y, w, h: items.length * o.gap, fontFace: F, fontSize: o.fs, color: o.color,
      isTextBox: true, valign: "top" });
}

/* 1 ── 표지 */
{
  const s = base(true);
  s.addText("AwareNet", { x: 0.9, y: 2.0, w: 11.5, h: 0.9, fontFace: F, fontSize: 48,
    bold: true, color: "FFFFFF", isTextBox: true, margin: 0 });
  s.addText("설계 변경의 경위와 실험 계획 — 지도교수 미팅 자료",
    { x: 0.9, y: 3.05, w: 11.5, h: 0.6, fontFace: F, fontSize: 22, color: TEALL,
      isTextBox: true, margin: 0 });
  s.addText("학습은 더 빠르게, 참여는 빠짐없이 — 기기마다 알맞은 학습량과 접속 경로를 정하는 연합학습 네트워크",
    { x: 0.9, y: 3.75, w: 11.5, h: 0.5, fontFace: F, fontSize: 14, color: "9FB6C9",
      isTextBox: true, margin: 0 });
  s.addText("충남대학교 AwareNet 팀  ·  2026. 09  ·  넷챌린지 시즌13",
    { x: 0.9, y: 6.5, w: 11.5, h: 0.4, fontFace: F, fontSize: 13, color: "8DA3B5",
      isTextBox: true, margin: 0 });
}

/* 2 ── 발표 개요 */
{
  const s = base();
  head(s, "발표 개요");
  const items = [
    ["1", "설계 변경의 이유", "가치 기반 대역폭 할당의 한계점 4가지 —\n자기상관성, 자원 편중에 따른 과적합, 공정성-속도 트레이드오프, 물리적 한계 실측"],
    ["2", "현행 설계와 실험 결과, 향후 계획", "완료: 학습량 조절 −40% · 학습량×경로 공동 결정 −21% · 언어모델 실험 −29%\n계획: 젯슨 실기기 → KOREN 실WAN (V100 VM 확보 완료)"],
    ["3", "논의드리고 싶은 사항 4가지", "연구 방향 · 과제명 변경 · 외부 멘토 의견 반영 · 설계 변경 서술 방식"],
  ];
  items.forEach(([n, t, d], i) => {
    const y = 1.75 + i * 1.78;
    card(s, 0.6, y, 12.1, 1.55, i === 2 ? TEALBG : "FFFFFF", i === 2 ? TEAL : LINE);
    chip(s, 0.95, y + 0.42, 0.7, n, TEAL, 18);
    s.addText(t, { x: 2.0, y: y + 0.16, w: 10.4, h: 0.5, fontFace: F, fontSize: 17,
      bold: true, color: INK, isTextBox: true, margin: 0 });
    s.addText(d, { x: 2.0, y: y + 0.62, w: 10.4, h: 0.85, fontFace: F, fontSize: 12,
      color: GRAY, isTextBox: true, margin: 0 });
  });
}

/* 3 ── 문제 상황 (그림 4) */
{
  const s = base();
  head(s, "문제 상황 — 느린 기기가 학습에서 제외된다",
    "실제 배치 사례: 구글 Gboard(키보드 추천) · 병원 20곳 공동 진단 모델(EXAM) · 제약사 10곳 신약 개발(MELLODDY)");
  s.addImage({ path: FIG("final_04_문제상황.png"), x: 0.75, y: 1.75, w: 11.85, h: 4.31 });
  s.addText("데이터를 넘기지 않고 함께 학습하는 방식(연합학습)에서, 마감을 넘긴 기기는 그 라운드에서 버려진다 — "
    + "누가 버려질지는 회선 경합의 운이 정하고, 느린 기관의 데이터는 계속 반영되지 못한다",
    { x: 0.75, y: 6.2, w: 11.85, h: 0.7, fontFace: F, fontSize: 13, color: INK,
      isTextBox: true, margin: 0, align: "center" });
}

/* 4 ── 원래 목표와 과제명의 오해 */
{
  const s = base();
  head(s, "원래 목표 — 학습 트래픽을 위한 네트워크",
    "과제명이 오해를 샀습니다: 일반 트래픽 제어 과제로 읽히지만, 처음부터 학습 트래픽이 대상이었습니다");
  card(s, 0.6, 1.8, 5.9, 4.6, "FFFFFF", LINE);
  s.addText("등록된 과제명", { x: 0.95, y: 2.05, w: 5.2, h: 0.4, fontFace: F, fontSize: 13,
    bold: true, color: GRAY, isTextBox: true, margin: 0 });
  s.addText("“KOREN SDN 기반 AI 인지형 네트워크”",
    { x: 0.95, y: 2.5, w: 5.2, h: 0.8, fontFace: F, fontSize: 17, bold: true, color: INK,
      isTextBox: true, margin: 0 });
  s.addText("읽히는 방식: 일반 트래픽을 SDN 으로 배분하는 과제\n→ 외부 멘토도 이렇게 이해 (8/28 챌린저데이)\n→ “배분 장치가 좋으면 왜 연합학습에만 쓰는가,\n     전체 네트워크에 적용하라”는 의견의 출발점",
    { x: 0.95, y: 3.4, w: 5.2, h: 1.8, fontFace: F, fontSize: 12.5, color: GRAY,
      isTextBox: true, margin: 0 });
  card(s, 6.85, 1.8, 5.9, 4.6, TEALBG, TEAL);
  s.addText("처음부터의 의도", { x: 7.2, y: 2.05, w: 5.2, h: 0.4, fontFace: F, fontSize: 13,
    bold: true, color: TEAL, isTextBox: true, margin: 0 });
  s.addText("학습이라는 특수한 트래픽을 아는 네트워크",
    { x: 7.2, y: 2.5, w: 5.2, h: 0.8, fontFace: F, fontSize: 17, bold: true, color: INK,
      isTextBox: true, margin: 0 });
  rows(s, [
    "일반 트래픽: 내용이 1비트도 깨지면 안 됨 → 조절 수단은 전송 시점과 경로뿐",
    "학습 트래픽: 양을 줄여도 결과 품질이 점진적으로만 하락 → “얼마나 보낼지”라는 조절 수단이 추가로 생김",
    "이 조절 수단을 실측 근거로 제어하는 것이 과제의 본질",
  ], 7.2, 3.45, 5.3, { fs: 13 });
}

/* 5 ── 초기 설계 */
{
  const s = base();
  head(s, "초기 설계 — 가치 기반 대역폭 할당",
    "“가치 있는 데이터를 가진 참여자에게 대역폭을 더 준다” — 집행 계층은 실제 장비에서 검증을 완료했습니다");
  const steps = ["① 각 참여자의 데이터 가치를\n     loss 로 평가", "② 가치 순으로\n     대역폭을 배정",
    "③ 게이트웨이 큐(HTB)가\n     비율을 집행"];
  steps.forEach((t, i) => {
    const x = 0.6 + i * 4.25;
    card(s, x, 1.95, 3.7, 1.5, "FFFFFF", LINE);
    s.addText(t, { x: x + 0.25, y: 2.1, w: 3.3, h: 1.2, fontFace: F, fontSize: 13.5,
      color: INK, isTextBox: true, margin: 0, valign: "middle" });
    if (i < 2) s.addShape("rightArrow", { x: x + 3.75, y: 2.5, w: 0.45, h: 0.4,
      fill: { color: TEAL }, line: { type: "none" } });
  });
  card(s, 0.6, 4.0, 12.1, 2.4, TEALBG, TEAL);
  s.addText("집행 계층 검증 완료 — 중간보고서의 성과 (유효 자산)",
    { x: 0.95, y: 4.25, w: 11.4, h: 0.45, fontFace: F, fontSize: 15, bold: true,
      color: TEAL, isTextBox: true, margin: 0 });
  s.addText([
    { text: "한 회선(45Mbps)에 흐름 3개를 경합시키고 큐 비율을 8 : 1 : 1 로 지정  →  실측 처리량 ", options: {} },
    { text: "7.93 : 1.01 : 1.00", options: { bold: true, color: TEAL } },
    { text: "  (집행 정확도 96~100%)\n“큐 정책으로 대역폭을 원하는 비율로 나눌 수 있다”는 검증 완료 — 문제는 장치가 아니라 ", options: {} },
    { text: "적용할 수 있는 환경", options: { bold: true, color: ORG } },
    { text: "이었습니다 (다음 4장)", options: {} },
  ], { x: 0.95, y: 4.8, w: 11.4, h: 1.4, fontFace: F, fontSize: 13.5, color: INK,
    isTextBox: true, margin: 0 });
}

/* 6 ── 한계점 ① 자기상관성 */
{
  const s = base();
  head(s, "한계점 ①  자기상관성 — 가치 평가의 피드백 루프",
    "loss 로 가치를 재면, 판정의 근거가 판정의 결과에 의해 움직입니다 — 가장 근본적인 문제였습니다");
  const boxes = [
    ["loss 가 높다\n= “가치가 높다” 판정", "FFFFFF", INK],
    ["대역폭을 더 받아\n더 많이·더 먼저 학습", "FFFFFF", INK],
    ["그 데이터에 익숙해져 loss 하락,\n다른 참여자의 loss 는 상대적 상승", "FDF3E7", ORG],
  ];
  boxes.forEach(([t, bg, tc], i) => {
    const x = 0.8 + i * 4.25;
    card(s, x, 2.3, 3.6, 1.6, bg, i === 2 ? ORG : LINE);
    s.addText(t, { x: x + 0.2, y: 2.42, w: 3.2, h: 1.35, fontFace: F, fontSize: 13,
      color: tc, isTextBox: true, margin: 0, valign: "middle", align: "center" });
    if (i < 2) s.addShape("rightArrow", { x: x + 3.65, y: 2.9, w: 0.45, h: 0.4,
      fill: { color: ORG }, line: { type: "none" } });
  });
  s.addShape("line", { x: 2.6, y: 4.25, w: 9.7, h: 0, line: { color: ORG, width: 2,
    dashType: "dash", endArrowType: "triangle" } });
  s.addShape("line", { x: 12.3, y: 3.9, w: 0, h: 0.35, line: { color: ORG, width: 2, dashType: "dash" } });
  s.addShape("line", { x: 2.6, y: 3.95, w: 0, h: 0.3, line: { color: ORG, width: 2, dashType: "dash" } });
  s.addText("판정 기준(loss)이 다시 처음으로 — 판정이 스스로 만든 결과를 근거로 삼는 피드백 루프",
    { x: 2.8, y: 4.35, w: 9.0, h: 0.4, fontFace: F, fontSize: 12.5, color: ORG, bold: true,
      isTextBox: true, margin: 0, align: "center" });
  card(s, 0.6, 5.15, 12.1, 1.45, "FFFFFF", LINE);
  s.addText([
    { text: "왜 치명적인가 — ", options: { bold: true } },
    { text: "가치 순위가 안정되지 않아 배정이 진동하고, “누구에게 더 줄까”의 정답이 존재하지 않게 됩니다. ", options: {} },
    { text: "loss 편향 선택이 수렴점을 틀어지게 한다는 이론 결과도 있습니다 (Power-of-Choice 2020 — 24장 참고 문헌).", options: { color: GRAY } },
  ], { x: 0.95, y: 5.38, w: 11.4, h: 1.05, fontFace: F, fontSize: 13.5, color: INK,
    isTextBox: true, margin: 0 });
}

/* 7 ── 한계점 ② DiffServ 과적합 */
{
  const s = base();
  head(s, "한계점 ②  DiffServ 방식 우선순위 — 자원 편중과 과적합",
    "대역폭 총량이 고정이므로, 인터넷 QoS 의 DiffServ 처럼 등급 태그를 붙여 상위부터 채우는 방식을 시도했습니다");
  card(s, 0.6, 1.85, 5.9, 4.5, "FFFFFF", LINE);
  s.addText("시도한 것", { x: 0.95, y: 2.1, w: 5.2, h: 0.4, fontFace: F, fontSize: 14,
    bold: true, color: TEAL, isTextBox: true, margin: 0 });
  rows(s, [
    "트래픽에 등급 태그를 붙여 가치가 높은 순서대로 대역폭을 채움 (DiffServ 의 차등 서비스 개념)",
    "태그의 근거는 loss 기반 가치 (앞 장의 평가)",
    "구현 자체는 큐 우선순위로 가능 — 집행 계층은 이미 검증됨",
  ], 0.95, 2.6, 5.3, { fs: 13 });
  card(s, 6.85, 1.85, 5.9, 4.5, "FDF3E7", ORG);
  s.addText("부딪힌 것 — 과적합", { x: 7.2, y: 2.1, w: 5.2, h: 0.4, fontFace: F,
    fontSize: 14, bold: true, color: ORG, isTextBox: true, margin: 0 });
  rows(s, [
    "상위 등급 참여자에게 학습 기회가 편중 → 모델이 그 참여자의 데이터에 과잉 적응 (overfitting)",
    "연합학습의 목적은 “모두의 데이터를 고루 반영” — 특정 참여자로의 편중은 목적 자체와 충돌",
    "네트워크 QoS 에서는 옳은 원리가, 학습에서는 편향 장치가 됨 — 학습은 “고른 반영”이 품질 조건",
  ], 7.2, 2.6, 5.3, { fs: 13 });
}

/* 8 ── 한계점 ③ 워터필링 */
{
  const s = base();
  head(s, "한계점 ③  워터필링 도입 — 공정성과 속도의 트레이드오프",
    "과적합을 막기 위해 모든 참여자에게 최소 몫을 보장하는 워터필링(max-min 공정성)을 일부 도입했습니다");
  const items = [
    ["보장을 늘리면", "느린·낮은 가치 참여자에게도 대역폭이 가야 하므로 빠른 쪽이 대기 → 라운드 시간 증가"],
    ["보장을 줄이면", "다시 자원 편중으로 돌아가 과적합 재발"],
    ["중간을 찾으면", "환경마다 최적점이 달라 튜닝 상수가 됨 — “상수 없는 설계” 원칙과 충돌"],
  ];
  items.forEach(([t, d], i) => {
    const y = 1.95 + i * 1.05;
    card(s, 0.6, y, 8.2, 0.88, "FFFFFF", LINE);
    s.addText(t, { x: 0.9, y: y + 0.12, w: 2.1, h: 0.6, fontFace: F, fontSize: 13.5,
      bold: true, color: INK, isTextBox: true, margin: 0, valign: "middle" });
    s.addText(d, { x: 3.1, y: y + 0.1, w: 5.55, h: 0.7, fontFace: F, fontSize: 12,
      color: GRAY, isTextBox: true, margin: 0, valign: "middle" });
  });
  card(s, 9.1, 1.95, 3.6, 3.08, TEALBG, TEAL);
  s.addText("결론", { x: 9.4, y: 2.2, w: 3.0, h: 0.4, fontFace: F, fontSize: 14, bold: true,
    color: TEAL, isTextBox: true, margin: 0 });
  s.addText("속도와 공정성이 같은 자원(대역폭)을 두고 경합하는 트레이드오프 —\n한 자원 안의 재분배로는 둘 다 얻을 수 없음",
    { x: 9.4, y: 2.65, w: 3.0, h: 2.2, fontFace: F, fontSize: 12.5, color: INK,
      isTextBox: true, margin: 0 });
  s.addText("→ 그래서 조절 대상을 바꿨습니다: 대역폭(총량 고정)이 아니라 학습량(줄여도 품질이 점진 하락)을 조절하면, 이 트레이드오프가 사라집니다",
    { x: 0.6, y: 5.4, w: 12.1, h: 0.9, fontFace: F, fontSize: 15, bold: true, color: TEAL,
      isTextBox: true, margin: 0 });
}

/* 9 ── 한계점 ④ 물리적 한계 */
{
  const s = base();
  head(s, "한계점 ④  물리적 한계 — 실측과 조사로 확인",
    "설계 문제(①~③)와 별개로, 적용 환경 자체가 없다는 것이 실측·조사로 확인됐습니다");
  const cards3 = [
    ["재분배 무효 (실측)", "같은 회선 안에서 몫을 재분배해도 완료 시각 불변 — 32.0초 대 34.7초 (오차 범위).\n현대 TCP 는 남는 대역폭을 놀리지 않아, 개입 전에 이미 물리 하한", TEAL],
    ["전송 시점 조절 무효 (실측)", "느린 쪽을 당기지 못하고 빠른 쪽만 52% 지연 — 완료 시각은 그대로", TEAL],
    ["공용 회선의 부재 (조사)", "Gboard·EXAM(병원 20곳)·MELLODDY(제약 10곳) 전부, 참여자가 함께 쓰는 공용 회선이 없음 — 배분할 대상 자체가 없었음", ORG],
  ];
  cards3.forEach(([t, d, c], i) => {
    const x = 0.6 + i * 4.25;
    card(s, x, 1.95, 3.85, 3.6, "FFFFFF", c);
    s.addText(t, { x: x + 0.28, y: 2.2, w: 3.3, h: 0.7, fontFace: F, fontSize: 14.5,
      bold: true, color: c, isTextBox: true, margin: 0 });
    s.addText(d, { x: x + 0.28, y: 2.95, w: 3.3, h: 2.4, fontFace: F, fontSize: 12,
      color: INK, isTextBox: true, margin: 0 });
  });
  s.addText("가설을 세우고 → 실측하고 → 기각을 기록했습니다. 이 이력 자체가 과제의 산출물이라고 생각합니다.",
    { x: 0.6, y: 5.85, w: 12.1, h: 0.5, fontFace: F, fontSize: 13.5, color: GRAY,
      isTextBox: true, margin: 0 });
}

/* 10 ── 설계 변경 전후 비교 */
{
  const s = base();
  head(s, "설계 변경 — 대역폭 할당에서 학습량·경로 조절로");
  const rows2 = [
    ["", "전 (중간보고서까지)", "현 (변경 후)"],
    ["조절 대상", "대역폭 할당량 (총량 고정 → 트레이드오프)", "학습량(폭)과 접속 경로"],
    ["판정 근거", "loss 기반 가치 (자기상관성)", "시간 실측만 — 계산·전송의 이동평균"],
    ["네트워크 역할", "제어 대상 (VXLAN·큐 배분)", "측정 대상 + 접속 지점 선택"],
    ["공정성", "보장을 섞을수록 느려짐", "최소 폭 25% — 아무도 배제하지 않음"],
    ["상수", "등급·보장 수위 등 튜닝 필요", "문턱 상수 0 — 중앙값×1.2, 계측 오차 10%만"],
  ];
  const colW = [2.1, 4.9, 4.9], x0 = 0.65;
  rows2.forEach((r, i) => {
    const y = 1.7 + i * 0.82, h = 0.74;
    r.forEach((t, j) => {
      const x = x0 + colW.slice(0, j).reduce((a, b) => a + b, 0) + j * 0.12;
      if (i === 0) {
        if (j > 0) card(s, x, y, colW[j], h, j === 2 ? TEAL : GRAY);
        if (j > 0) s.addText(t, { x: x + 0.2, y, w: colW[j] - 0.4, h, fontFace: F,
          fontSize: 14, bold: true, color: "FFFFFF", isTextBox: true, margin: 0, valign: "middle" });
      } else {
        card(s, x, y, colW[j], h, j === 0 ? "EEF1F4" : j === 2 ? TEALBG : "FFFFFF",
          j === 2 ? TEAL : LINE);
        s.addText(t, { x: x + 0.2, y, w: colW[j] - 0.4, h, fontFace: F,
          fontSize: j === 0 ? 12.5 : 12, bold: j === 0, color: INK, isTextBox: true,
          margin: 0, valign: "middle" });
      }
    });
  });
}

/* 11 ── SDN 재적용 */
{
  const s = base();
  head(s, "SDN 개념의 재적용 — 중앙 제어부의 전역 관측",
    "가상 망을 구성하는 SDN 이 아니라, SDN 의 본질인 전역 관측과 중앙 결정을 학습 트래픽에 적용합니다");
  card(s, 0.6, 1.85, 5.9, 4.5, "FFFFFF", LINE);
  s.addText("SDN 의 본질 (교과서 정의)", { x: 0.95, y: 2.1, w: 5.2, h: 0.4, fontFace: F,
    fontSize: 14, bold: true, color: GRAY, isTextBox: true, margin: 0 });
  rows(s, [
    "제어 평면과 데이터 평면의 분리",
    "제어부(controller)가 망 전체의 상태를 한눈에 관측 (전역 관측)",
    "관측을 근거로 규칙을 내려보냄 (프로그래머블 제어)",
  ], 0.95, 2.6, 5.3, { fs: 13 });
  card(s, 6.85, 1.85, 5.9, 4.5, TEALBG, TEAL);
  s.addText("AwareNet 의 대응 — 같은 원리, 다른 대상", { x: 7.2, y: 2.1, w: 5.3, h: 0.4,
    fontFace: F, fontSize: 14, bold: true, color: TEAL, isTextBox: true, margin: 0 });
  rows(s, [
    "결정(컨트롤러)과 학습(기기)의 분리",
    "컨트롤러가 모든 기기의 계산·전송 속도를 실측으로 한눈에 관측",
    "관측을 근거로 역할을 내려보냄 — 전체 폭 / 축소 폭 / 다른 경로",
    "결과: 속도(라운드 시간)와 학습 상황(배제 0)이 함께 개선",
  ], 7.2, 2.6, 5.3, { fs: 13 });
  s.addText("가상 망을 구성하는 SDN 이 아니라, 망 전체를 관측해 제어하는 SDN — 과제명의 SDN 은 이 의미로 유지됩니다",
    { x: 0.6, y: 6.55, w: 12.1, h: 0.5, fontFace: F, fontSize: 14, bold: true, color: TEAL,
      isTextBox: true, margin: 0 });
}

/* 12 ── 시스템 구성 (그림 1) */
{
  const s = base();
  head(s, "시스템 구성 — 측정 · 결정 · 집행의 폐루프");
  s.addImage({ path: FIG("final_01_아키텍처.png"), x: 1.7, y: 1.55, w: 9.95, h: 5.32 });
}

/* 13 ── 분할 학습과 학습량(폭) (그림 2) */
{
  const s = base();
  head(s, "핵심 개념 ① — 모델 분할과 학습량(폭)",
    "기기는 모델 앞부분만 계산해 중간 결과를 올리고(분할 학습), 느린 기기는 층의 일부 폭만 학습합니다 (Ordered Dropout)");
  s.addImage({ path: FIG("final_02_분할과폭.png"), x: 1.25, y: 1.8, w: 10.8, h: 5.29 });
}

/* 14 ── 결정 순서 (그림 3) */
{
  const s = base();
  head(s, "핵심 개념 ② — 컨트롤러의 결정 순서",
    "모든 판단은 실측에서 출발합니다 — 문턱 상수 없이, 기준선은 참가자 중앙값의 1.2배");
  s.addImage({ path: FIG("final_03_결정순서.png"), x: 0.65, y: 1.95, w: 12.0, h: 3.68 });
  rows(s, [
    "1단 — 여유 있는 접속 경로가 있으면 이동 (정확도 손실 없음, 이득이 계측 오차 10%를 넘고 2라운드 연속일 때만)",
    "2단 — 경로로 부족하면 그 기기의 학습량(폭)만 한 단계 축소 · 최소 폭 25% 보장 (배제 없음)",
  ], 0.7, 5.85, 12.0, { fs: 13 });
}

/* 15 ── 공동 결정 개념도 (그림 7) */
{
  const s = base();
  head(s, "현행 설계 — 학습량(폭)과 접속 경로의 공동 결정");
  s.addImage({ path: FIG("final_07_두손잡이.png"), x: 1.55, y: 1.55, w: 10.25, h: 5.6 });
}

/* 16 ── 실험 결과 요약 */
{
  const s = base();
  head(s, "실험 결과 요약 — 완료 항목 (재현 스크립트 포함)");
  const stats = [
    ["−40%", "학습량 조절\n이질 환경 라운드 시간", "기기 4대, 회선 20~80Mbps"],
    ["−21%", "학습량×경로 공동 결정\n병목이 심한 환경", "학습량 손실 0 — 경로 이동만으로"],
    ["−29%", "언어모델 실험\n어댑터 업로드 구간", "실제 0.5B 모델 3기관, 실소켓"],
    ["2~3%p", "예측 오차\n(계획 대비 실측)", "CNN 실험 3% · 언어모델 실험 2%p"],
  ];
  stats.forEach(([n, t, d], i) => {
    const x = 0.6 + i * 3.18;
    card(s, x, 1.9, 2.85, 3.3, i === 3 ? TEALBG : "FFFFFF", i === 3 ? TEAL : LINE);
    s.addText(n, { x: x + 0.15, y: 2.15, w: 2.55, h: 1.0, fontFace: F, fontSize: 40,
      bold: true, color: TEAL, align: "center", isTextBox: true, margin: 0 });
    s.addText(t, { x: x + 0.15, y: 3.25, w: 2.55, h: 0.9, fontFace: F, fontSize: 13,
      bold: true, color: INK, align: "center", isTextBox: true, margin: 0 });
    s.addText(d, { x: x + 0.15, y: 4.25, w: 2.55, h: 0.8, fontFace: F, fontSize: 10.5,
      color: GRAY, align: "center", isTextBox: true, margin: 0 });
  });
  rows(s, [
    "안정성: 성능 차이가 없는 환경에서는 개입 0회 (2회 실측으로 확인)",
    "목표 정확도 도달 시간(time-to-accuracy): 병목 환경에서 20% 도달 304초 → 179초 (−41%)",
  ], 0.7, 5.6, 11.9, { fs: 13.5 });
}

/* 17 ── 온라인 공동 결정 실측 (그림 6) */
{
  const s = base();
  head(s, "온라인 공동 결정 — 동작 실측 결과");
  s.addImage({ path: FIG("final_06_온라인판단.png"), x: 0.75, y: 1.6, w: 11.8, h: 4.45 });
  s.addText("전체 기기를 빠른 경로에 배치하고 시작 → 첫 측정 후 1대만 이동, 이후 안정 (진동 없음) — 병목이 심할수록 개선 폭이 커짐",
    { x: 0.75, y: 6.25, w: 11.8, h: 0.5, fontFace: F, fontSize: 13, color: GRAY,
      isTextBox: true, margin: 0, align: "center" });
}

/* 18 ── 언어모델 실험 상세 */
{
  const s = base();
  head(s, "언어모델 실험 — 3개 기관 연합과 경로 조절",
    "실제 0.5B 언어모델을 3개 기관이 나눠 학습 — 데이터는 안 움직이고 어댑터(35MB)만 실제 소켓으로 왕복");
  card(s, 0.6, 1.85, 5.9, 4.4, "FFFFFF", LINE);
  s.addText("지식 공유 검증 (동일 채점 기준)", { x: 0.95, y: 2.1, w: 5.2, h: 0.4,
    fontFace: F, fontSize: 14, bold: true, color: TEAL, isTextBox: true, margin: 0 });
  const tbl = [["기본 모델", "0%", "학습 전 — 알 수 없는 사실"],
    ["한 기관 단독", "36%", "자기 데이터만 학습"],
    ["3개 기관 연합", "71%", "서로의 지식이 전달됨"]];
  tbl.forEach(([a, b, c], i) => {
    const y = 2.65 + i * 1.1;
    card(s, 0.95, y, 5.2, 0.92, i === 2 ? TEALBG : "F7F9F8", i === 2 ? TEAL : LINE);
    s.addText(a, { x: 1.2, y: y + 0.08, w: 2.0, h: 0.76, fontFace: F, fontSize: 12.5,
      bold: true, color: INK, isTextBox: true, margin: 0, valign: "middle" });
    s.addText(b, { x: 3.2, y: y + 0.08, w: 0.9, h: 0.76, fontFace: F, fontSize: 17,
      bold: true, color: TEAL, isTextBox: true, margin: 0, valign: "middle" });
    s.addText(c, { x: 4.15, y: y + 0.08, w: 1.95, h: 0.76, fontFace: F, fontSize: 10.5,
      color: GRAY, isTextBox: true, margin: 0, valign: "middle" });
  });
  card(s, 6.85, 1.85, 5.9, 4.4, "FFFFFF", LINE);
  s.addText("경로 조절 실측 (어댑터 트래픽)", { x: 7.2, y: 2.1, w: 5.2, h: 0.4,
    fontFace: F, fontSize: 14, bold: true, color: TEAL, isTextBox: true, margin: 0 });
  rows(s, [
    "기준(전원 40Mbps 경로) 업로드 구간 20.5초 → 공동 결정(1대를 20Mbps 로 분산) 14.7초 (−29%)",
    "예측 33% 대 실측 31% — 오차 2%p",
    "추가 확인: 이득이 정확히 0인 환경에서는 6라운드 내내 개입하지 않음 (안정성) / 예측-실측 불일치가 테스트베드 결함(수신 직렬화)을 발견해 수정",
    "의미: CNN(활성값)과 언어모델(어댑터) — 성질이 다른 두 트래픽에서 같은 규칙이 동작",
  ], 7.2, 2.6, 5.3, { fs: 12.5 });
}

/* 19 ── 결정 알고리즘 3단계 검증 */
{
  const s = base();
  head(s, "결정 알고리즘의 신뢰성 — 3단계 검증",
    "실장비 실험 전에, 결정 알고리즘 자체를 검증했습니다");
  const cols = [
    ["단위 테스트 10종", "성능이 같으면 이동 없음 · 명확한 이득이면 1대만 이동 · 차이가 작으면 유지 ·\n느린 경로 배정 기기는 학습량 축소 — 규칙별 테스트 등록, 전부 통과", TEAL],
    ["난수 시뮬레이션 1000회", "기기 수·경로·속도를 난수로 생성한 시나리오 1000개 + 측정 잡음 ±10%\n→ 규칙 위반 0건 (진동·과잉 이동·성능 악화 없음), 예측 개선 중앙값 +30%", TEAL],
    ["검증 과정에서 발견·수정한 결함 2건", "측정 잡음 1회에 반응하는 문제 → 같은 결정이 2라운드 연속일 때만 적용\n왕복 진동 1건 발견 → 원래 경로로 복귀하는 이동은 3라운드 연속 요구 (상수 추가 없음)", ORG],
  ];
  cols.forEach(([t, d, c], i) => {
    const y = 1.95 + i * 1.5;
    card(s, 0.6, y, 12.1, 1.3, i === 2 ? "FDF3E7" : "FFFFFF", i === 2 ? ORG : LINE);
    s.addText(t, { x: 0.95, y: y + 0.14, w: 3.1, h: 1.0, fontFace: F, fontSize: 14.5,
      bold: true, color: c, isTextBox: true, margin: 0, valign: "middle" });
    s.addText(d, { x: 4.2, y: y + 0.12, w: 8.2, h: 1.06, fontFace: F, fontSize: 12,
      color: INK, isTextBox: true, margin: 0, valign: "middle" });
  });
  s.addText("난수 시뮬레이션이 실장비 실험보다 먼저 결함을 발견했습니다 — 실제 WAN 에서 발생했다면 원인 규명이 어려웠을 문제들입니다",
    { x: 0.6, y: 6.5, w: 12.1, h: 0.45, fontFace: F, fontSize: 13, color: GRAY,
      isTextBox: true, margin: 0 });
}

/* 20 ── 실험 계획 4단계 */
{
  const s = base();
  head(s, "실험 계획 — 관련 연구의 표준 검증 절차 4단계",
    "FjORD 는 ①만, PiPar·FedAdapt 는 ②③, FEDn 은 ④ — 한 논문이 모두 수행하지는 않는 절차를 순서대로 수행");
  const steps = [
    ["①", "난수 시뮬레이션", "1000회 실행, 규칙 위반 0건", "완료", TEAL, 1.0],
    ["②", "트래픽 제어(tc) 테스트베드", "학습량 −40% · 경로 −21% · 언어모델 −29%", "완료", TEAL, 1.0],
    ["③", "실기기 (젯슨)", "연산이 실제로 느린 기기에서 학습량 축소 경향 재현 — PC 2대 + 젯슨 1대", "계획", ORG, 1.0],
    ["④", "실WAN (KOREN)", "K-W1 사전 진단의 실WAN 검증 (판교 VM — 즉시 가능)  ·  K-W2 학습량 조절 재현 (실제 회선이 다른 기기들)\nK-W3 접속 지점 배정 — 집계 서버 2곳(판교 VM + HPC V100) 중 선택을 학습량과 함께 결정", "V100 VM 확보", ORG, 1.45],
  ];
  let y = 1.95;
  steps.forEach(([n, t, d, tag, c, h]) => {
    card(s, 0.6, y, 12.1, h, c === TEAL ? TEALBG : "FFFFFF", c);
    chip(s, 0.9, y + h / 2 - 0.31, 0.62, n, c, 15);
    s.addText(t, { x: 1.85, y: y + 0.08, w: 2.9, h: h - 0.16, fontFace: F, fontSize: 14,
      bold: true, color: INK, isTextBox: true, margin: 0, valign: "middle" });
    s.addText(d, { x: 4.85, y: y + 0.06, w: 6.1, h: h - 0.12, fontFace: F, fontSize: 11,
      color: INK, isTextBox: true, margin: 0, valign: "middle" });
    s.addText(tag, { x: 11.0, y: y + h / 2 - 0.2, w: 1.55, h: 0.4, fontFace: F, fontSize: 12,
      bold: true, color: c, align: "right", isTextBox: true, margin: 0 });
    y += h + 0.18;
  });
  s.addText("평가 기준(사전 등록): 실제 WAN 에서는 수치 일치가 아니라 경향 재현을 확인 — 느린 기기만 학습량이 줄고 라운드 시간이 단축",
    { x: 0.6, y: 6.95, w: 12.1, h: 0.4, fontFace: F, fontSize: 12, color: GRAY,
      isTextBox: true, margin: 0 });
}

/* 21 ── 연합학습의 역할 */
{
  const s = base();
  head(s, "연합학습의 역할 — 현재는 검증 플랫폼, 기법은 범용",
    "지난 미팅에서 설명이 부족했던 부분을 정리했습니다");
  card(s, 0.6, 1.85, 5.9, 4.4, TEALBG, TEAL);
  s.addText("현재: 검증 플랫폼", { x: 0.95, y: 2.1, w: 5.2, h: 0.45, fontFace: F,
    fontSize: 15, bold: true, color: TEAL, isTextBox: true, margin: 0 });
  rows(s, [
    "연합학습은 “기기마다 속도가 다르고, 트래픽이 라운드 경계마다 집중되는” 조건을 실제로 만들어 주는 환경",
    "이 환경에서 측정 → 결정 → 집행 절차를 실측으로 검증 완료",
  ], 0.95, 2.65, 5.3, { fs: 13 });
  card(s, 6.85, 1.85, 5.9, 4.4, "FFFFFF", LINE);
  s.addText("다음: 같은 기법이 닿는 곳", { x: 7.2, y: 2.1, w: 5.2, h: 0.45, fontFace: F,
    fontSize: 15, bold: true, color: INK, isTextBox: true, margin: 0 });
  rows(s, [
    "분할 학습 — 활성값 트래픽 (CNN 실험에서 동작 확인)",
    "언어모델 — 어댑터 트래픽 (−29% 실측)",
    "서버에 데이터를 모으면 더 빠를 수 있으나, 데이터가 나갈 수 없는 전제(병원·제약)에서는 이 방식뿐 — 증명 목표는 범용성 (다음 장)",
  ], 7.2, 2.65, 5.3, { fs: 13 });
}

/* 22 ── 범용성 */
{
  const s = base();
  head(s, "범용성 — 어떤 트래픽까지 적용 가능한가",
    "“모든 트래픽”이 아니라, “양을 줄여도 품질이 점진적으로 떨어지는 트래픽”이라는 분류 전체에 적용됩니다");
  card(s, 0.6, 1.85, 7.9, 4.5, "FFFFFF", LINE);
  s.addText("적용 가능 — 품질이 점진 하락하는 트래픽", { x: 0.95, y: 2.1, w: 7.2, h: 0.4,
    fontFace: F, fontSize: 14, bold: true, color: TEAL, isTextBox: true, margin: 0 });
  rows(s, [
    "분산 학습 전반 — 성질이 다른 두 트래픽(활성값·어댑터)에서 이미 같은 규칙이 동작함을 실측",
    "영상 스트리밍 — 화질을 낮춰도 시청은 됨. 유튜브·넷플릭스의 적응형 화질(ABR)이 같은 원리의 상용 선례 → “양 조절 수단이 실재한다”의 가장 강한 증거",
    "센서·관측 데이터 — 샘플링 주기를 낮춰도 관측은 유지됨",
  ], 0.95, 2.6, 7.2, { fs: 12.5 });
  card(s, 8.85, 1.85, 3.85, 4.5, "FDF3E7", ORG);
  s.addText("적용 불가", { x: 9.15, y: 2.1, w: 3.2, h: 0.4, fontFace: F, fontSize: 14,
    bold: true, color: ORG, isTextBox: true, margin: 0 });
  s.addText("파일 전송·금융 거래 등 내용이 1비트도 깨지면 안 되는 트래픽 —\n원리적으로 불가하며,\n이는 한계가 아니라 분류 기준",
    { x: 9.15, y: 2.6, w: 3.25, h: 2.5, fontFace: F, fontSize: 12, color: INK,
      isTextBox: true, margin: 0 });
  s.addText("정리: 일반 네트워크 전체로의 확장은 표준 기술(QoS)의 재확인이 되므로 하지 않되, “양을 줄일 수 있는 트래픽” 분류에 대한 범용성은 실측으로 증명한다",
    { x: 0.6, y: 6.5, w: 12.1, h: 0.55, fontFace: F, fontSize: 13.5, bold: true,
      color: TEAL, isTextBox: true, margin: 0 });
}

/* 23 ── 예상 질문과 답변 */
{
  const s = base();
  head(s, "예상 질문과 준비된 답변");
  const qa = [
    ["Q. 모델을 주고받는 것인가?", "데이터는 절대 안 움직입니다. CNN 실험: 기기는 모델 앞부분만 계산해 중간 결과(활성값)를 올림. 언어모델 실험: 어댑터(전체 파라미터의 1% 미만, 35MB)만 오가고, 라운드마다 서버가 평균해 돌려줌"],
    ["Q. loss 로 가치를 나눈다면, loss 는 누가 계산하나?", "그 설계는 기각했습니다 (자기상관성 — 6장). 현재는 가치 판단 자체가 없고, 시간 실측(계산·전송)만으로 결정합니다. 굳이 한다면 각 기기가 로컬로 계산해 보고하는 방식(Oort 계열)이 표준이나, 피드백 루프 문제로 채택하지 않았습니다"],
    ["Q. 그럼 컨트롤러는 무엇을 아는가?", "기기별 계산 시간·전송 시간·업로드 크기(전부 실측 이동평균) — 데이터 내용은 전혀 모릅니다. 시작 전 0.8초의 사전 진단으로 첫 라운드부터 배정이 이루어집니다"],
  ];
  qa.forEach(([q, a], i) => {
    const y = 1.7 + i * 1.62;
    card(s, 0.6, y, 12.1, 1.45, "FFFFFF", LINE);
    s.addText(q, { x: 0.95, y: y + 0.12, w: 11.4, h: 0.4, fontFace: F, fontSize: 13.5,
      bold: true, color: TEAL, isTextBox: true, margin: 0 });
    s.addText(a, { x: 0.95, y: y + 0.52, w: 11.4, h: 0.85, fontFace: F, fontSize: 12,
      color: INK, isTextBox: true, margin: 0 });
  });
}

/* 24 ── 참고 문헌 */
{
  const s = base();
  head(s, "참고 문헌 — 설계 변경과 현행 설계의 근거",
    "왼쪽 4편은 기각한 설계의 근거, 오른쪽 4편은 현행 설계의 근거입니다");
  const left = [
    ["DiffServ (RFC 2475, 1998)", "등급 태그 기반 차등 서비스 — 우선순위 시도의 원형"],
    ["Kelly, Rate control (1998)", "대역폭 배분 공정성(비례 공정)의 고전 — 워터필링의 이론 배경"],
    ["Oort (OSDI 2021)", "loss×시간 효용으로 참여자 선택 — loss 기반 가치 평가의 대표 연구"],
    ["Power-of-Choice (2020)", "loss 편향 선택은 빨라지지만 수렴점이 틀어짐을 증명 — 과적합 우려의 이론 근거"],
  ];
  const right = [
    ["FjORD (NeurIPS 2021)", "학습 폭(Ordered Dropout)의 원조 — 본 과제는 실측 기반 배정으로 확장"],
    ["PiPar (JPDC 2024)", "분할학습 파이프라이닝 — 실험 방법론의 참조"],
    ["FedAdapt (IoT FL)", "라즈베리파이·젯슨 실기기 실험 — 3단계(젯슨) 계획의 관행 근거"],
    ["FEDn (2021)", "클라우드 4개 지역 실WAN 연합학습 — 4단계(KOREN) 계획의 관행 근거"],
  ];
  [[left, 0.6, "기각한 설계의 근거"], [right, 6.85, "현행 설계의 근거"]].forEach(([list, x, t]) => {
    s.addText(t, { x: x + 0.05, y: 1.72, w: 5.8, h: 0.35, fontFace: F, fontSize: 13,
      bold: true, color: GRAY, isTextBox: true, margin: 0 });
    list.forEach(([n, d], i) => {
      const y = 2.15 + i * 1.18;
      card(s, x, y, 5.9, 1.02, "FFFFFF", LINE);
      s.addText(n, { x: x + 0.25, y: y + 0.1, w: 5.4, h: 0.38, fontFace: F, fontSize: 12.5,
        bold: true, color: INK, isTextBox: true, margin: 0 });
      s.addText(d, { x: x + 0.25, y: y + 0.47, w: 5.4, h: 0.5, fontFace: F, fontSize: 10.5,
        color: GRAY, isTextBox: true, margin: 0 });
    });
  });
}

/* 25 ── 논의 사항 4가지 */
{
  const s = base();
  head(s, "논의드리고 싶은 사항 — 4가지");
  const qs = [
    ["연구 방향", "학습량 조절(폭·언어모델)을 본체로 유지할지, 축소할지 — 팀 의견은 본체 유지 (새로움이 학습 쪽에 있음)"],
    ["과제명", "“KOREN SDN 기반”과 현 방향의 거리 — 변경 신청(다음 장 문안)할지, SDN 접점을 강화해 유지할지"],
    ["외부 멘토 의견 반영", "“일반 네트워크로 넓혀라” 의견에 대한 반영 기록 — 준비한 문안(22장 범용성 논리)이 심사에서 충분한지"],
    ["설계 변경 서술 방식", "가설 → 실측 → 기각의 이력을 보고서에 정면으로 쓰는 방식에 대한 의견"],
  ];
  qs.forEach(([t, d], i) => {
    const y = 1.75 + i * 1.28;
    card(s, 0.6, y, 12.1, 1.1, i === 0 ? TEALBG : "FFFFFF", i === 0 ? TEAL : LINE);
    chip(s, 0.92, y + 0.24, 0.62, String(i + 1), TEAL, 15);
    s.addText(t, { x: 1.85, y: y + 0.1, w: 3.0, h: 0.9, fontFace: F, fontSize: 14.5,
      bold: true, color: INK, isTextBox: true, margin: 0, valign: "middle" });
    s.addText(d, { x: 4.95, y: y + 0.08, w: 7.5, h: 0.95, fontFace: F, fontSize: 12,
      color: GRAY, isTextBox: true, margin: 0, valign: "middle" });
  });
}

/* 26 ── 과제명 변경안 */
{
  const s = base();
  head(s, "과제명 변경안과 사유 문안 (준비된 초안)");
  card(s, 0.6, 1.8, 12.1, 1.5, TEALBG, TEAL);
  s.addText("변경안", { x: 0.95, y: 2.0, w: 11.4, h: 0.35, fontFace: F, fontSize: 12,
    bold: true, color: TEAL, isTextBox: true, margin: 0 });
  s.addText("AwareNet — 학습은 더 빠르게, 참여는 빠짐없이: 기기마다 알맞은 학습량과 접속 경로를 정하는 연합학습 네트워크 (KOREN 실측 기반)",
    { x: 0.95, y: 2.38, w: 11.4, h: 0.8, fontFace: F, fontSize: 15.5, bold: true,
      color: INK, isTextBox: true, margin: 0 });
  card(s, 0.6, 3.55, 12.1, 2.35, "FFFFFF", LINE);
  s.addText("변경 사유 문안 (신청서용)", { x: 0.95, y: 3.72, w: 11.4, h: 0.35, fontFace: F,
    fontSize: 12, bold: true, color: GRAY, isTextBox: true, margin: 0 });
  s.addText("“본 과제는 당초 KOREN 의 SDN 제어 기능을 활용해 회선을 측정·제어하는 것을 계획하였습니다. 그러나 수행 과정에서 현실적인 제약으로 해당 기능(L2VPN 개통, T-SDN OpenAPI 등)을 제공받기 어렵다는 것을 확인하였습니다. 이에 OVS(Open vSwitch)로 가상 경로를 직접 구성해 SDN 제어를 대신하는 방안도 검토하였으나, 이는 저희가 만든 가상 환경 안에서만 성립하고 실제 운영 환경으로 이어질 수 없다고 판단하여 채택하지 않았습니다. 이에 따라 과제의 초점을 연합학습의 학습 환경 — 학습 트래픽의 측정과 기기별 학습량·접속 경로의 조절 — 으로 옮겼습니다. SDN 의 개념이 사라진 것은 아니며, 중앙 제어부가 망 전체를 관측해 기기의 접속 지점을 바꾸는 재접속의 형태로 이어집니다. 이러한 변경 내용을 과제명에 반영하여 정정하고자 합니다.”",
    { x: 0.95, y: 4.1, w: 11.4, h: 1.75, fontFace: F, fontSize: 11.5, color: INK,
      isTextBox: true, margin: 0 });
  rows(s, [
    "절차: ① 사무국에 변경 가능 여부 확인 (선행) ② 가능 시 위 문안으로 신청 ③ 불가 시 등록명 유지 + 표지에 부제로 병기",
  ], 0.7, 6.1, 11.9, { fs: 12.5 });
}

/* 27 ── 요약 */
{
  const s = base(true);
  s.addText("요약", { x: 0.9, y: 0.85, w: 11.5, h: 0.6, fontFace: F, fontSize: 30,
    bold: true, color: "FFFFFF", isTextBox: true, margin: 0 });
  const rows3 = [
    ["전", "가치 기반 대역폭 할당 — 자기상관성·과적합·공정성 트레이드오프·물리적 한계로 중단 (전 과정 기록)"],
    ["현", "학습량(폭)과 접속 경로를 실측 기반으로 공동 결정 — 학습량 −40% · 경로 −21% · 언어모델 −29%, 예측 오차 2~3%p"],
    ["다음", "젯슨 실기기 → KOREN 실WAN (V100 확보) — 그리고 오늘, 연구 방향의 확정"],
  ];
  rows3.forEach(([t, d], i) => {
    const y = 1.9 + i * 1.35;
    s.addShape("roundRect", { x: 0.9, y, w: 11.5, h: 1.15, rectRadius: 0.07,
      fill: { color: i === 1 ? "27404F" : "24333F" }, line: i === 1 ? { color: TEAL, width: 1.2 } : { type: "none" } });
    s.addText(t, { x: 1.25, y: y + 0.1, w: 1.2, h: 0.95, fontFace: F, fontSize: 19,
      bold: true, color: i === 1 ? "7BD3C8" : "9FB6C9", isTextBox: true, margin: 0, valign: "middle" });
    s.addText(d, { x: 2.6, y: y + 0.08, w: 9.6, h: 1.0, fontFace: F, fontSize: 13,
      color: "E8EEF2", isTextBox: true, margin: 0, valign: "middle" });
  });
  s.addText("모든 수치는 저장소의 재현 명령으로 다시 얻을 수 있습니다 — 예상과 다르게 나오면 다르게 나온 대로 보고합니다",
    { x: 0.9, y: 6.35, w: 11.5, h: 0.5, fontFace: F, fontSize: 12.5, color: "8DA3B5",
      isTextBox: true, margin: 0 });
}

pres.writeFile({ fileName: path.join(__dirname, "..", "..", "docs", "01_제출발표", "미팅_방향과실측.pptx") })
  .then(f => console.log("saved", f));
