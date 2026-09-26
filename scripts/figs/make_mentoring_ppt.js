// 지도교수 멘토링 자료 — 1부 여기까지 온 과정(스토리) · 2부 결정 2 · 3부 질문 5
// 빌드: node scripts/figs/make_mentoring_ppt.js  →  docs/01_제출발표/미팅_멘토링자료.pptx
// 그림: out/fig/final_*.png (make_final_figs.py), out/fig/mt_*.png (make_mentoring_figs.py),
//       out/fig/final_08_분할전송.png (make_mp_fig.py)
const pptxgen = require("pptxgenjs");
const path = require("path");
const fs = require("fs");

const INK = "1D2D3D", TEAL = "0F766E", TEALL = "D7EAE8", TEALBG = "F2F7F6";
const ORG = "B45309", ORGBG = "FDF3E7", GRAY = "5A6B7A", LINE = "C9D2D9";
const F = "Malgun Gothic";
const FIG = p => path.join(__dirname, "..", "..", "out", "fig", p);

// PNG 실제 크기로 비율을 맞춰 (x,y) 기준 상자 (maxW × maxH) 안에 넣는다 — 가로 중앙 정렬
function pngSize(file) {
  const b = fs.readFileSync(file);
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) };
}
function img(s, name, x, y, maxW, maxH, align = "center") {
  const f = FIG(name), { w, h } = pngSize(f);
  let W = maxW, H = maxW * h / w;
  if (H > maxH) { H = maxH; W = maxH * w / h; }
  const X = align === "center" ? x + (maxW - W) / 2 : x;
  s.addImage({ path: f, x: X, y: y + (maxH - H) / 2, w: W, h: H });
  return { x: X, y: y + (maxH - H) / 2, w: W, h: H };
}

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";            // 13.33 × 7.5

let NO = 0;
function base(dark = false) {
  const s = pres.addSlide();
  s.background = { color: dark ? INK : "FFFFFF" };
  NO++;
  if (!dark) s.addText(String(NO), { x: 12.7, y: 7.05, w: 0.5, h: 0.35, fontFace: F,
    fontSize: 10, color: GRAY, align: "right", isTextBox: true, margin: 0 });
  return s;
}
function part(s, label) {
  s.addText(label, { x: 0.6, y: 0.12, w: 9, h: 0.3, fontFace: F, fontSize: 10.5,
    bold: true, color: TEAL, isTextBox: true, margin: 0 });
}
function head(s, title, sub) {
  s.addText(title, { x: 0.6, y: 0.44, w: 12.1, h: 0.72, fontFace: F, fontSize: 25,
    bold: true, color: INK, isTextBox: true, margin: 0 });
  if (sub) s.addText(sub, { x: 0.6, y: 1.16, w: 12.1, h: 0.4, fontFace: F,
    fontSize: 12.5, color: GRAY, isTextBox: true, margin: 0 });
}
function card(s, x, y, w, h, fill, lineC) {
  s.addShape("roundRect", { x, y, w, h, rectRadius: 0.07, fill: { color: fill },
    line: lineC ? { color: lineC, width: 1.2 } : { type: "none" },
    shadow: { type: "outer", color: "9AA7B0", blur: 6, offset: 2, angle: 90, opacity: 0.25 } });
}
function chip(s, x, y, d, txt, fill, fs) {
  s.addShape("ellipse", { x, y, w: d, h: d, fill: { color: fill }, line: { type: "none" } });
  s.addText(txt, { x: x - 0.25, y, w: d + 0.5, h: d, fontFace: F, fontSize: fs || 13,
    bold: true, color: "FFFFFF", align: "center", valign: "middle", isTextBox: true, margin: 0 });
}
function label(s, x, y, w, txt, color) {
  s.addText(txt, { x, y, w, h: 0.38, fontFace: F, fontSize: 12.5, bold: true,
    color: color || GRAY, isTextBox: true, margin: 0 });
}
function text(s, x, y, w, h, txt, opt) {
  const o = Object.assign({ fs: 12.5, color: INK, bold: false, valign: "top", align: "left" }, opt || {});
  s.addText(txt, { x, y, w, h, fontFace: F, fontSize: o.fs, color: o.color, bold: o.bold,
    isTextBox: true, margin: 0, valign: o.valign, align: o.align });
}
function rows(s, items, x, y, w, h, opt) {
  const o = Object.assign({ fs: 12.5, color: INK, bold: false }, opt || {});
  s.addText(items.map((t, i) => ({ text: t, options: { bullet: { code: "2022", indent: 12 },
    breakLine: i < items.length - 1, paraSpaceAfter: 6 } })),
    { x, y, w, h, fontFace: F, fontSize: o.fs, color: o.color, bold: o.bold,
      isTextBox: true, valign: "top" });
}
function arrowBox(s, x, y, w, h, txt, fill, lineC, opt) {
  card(s, x, y, w, h, fill, lineC);
  text(s, x + 0.15, y, w - 0.3, h, txt, Object.assign({ valign: "middle", align: "center" }, opt || {}));
}
function situation(s, txt, y = 1.4, h = 0.85) {
  card(s, 0.6, y, 12.1, h, "FFFFFF", LINE);
  label(s, 0.95, y + 0.15, 1.3, "상황");
  text(s, 2.2, y, 10.2, h, txt, { fs: 12, valign: "middle" });
}
// 질문 장 (그림형): 상황 → [그림 | 우리 생각] → 여쭙는 것
function qSlideFig(qno, title, sit, fig, ours, asks, oursLabel = "우리 생각") {
  const s = base();
  part(s, "3부 · 질문");
  head(s, `질문 ${qno}.  ${title}`);
  situation(s, sit);
  const fy = 2.4, fh = 2.95;
  img(s, fig, 0.6, fy, 6.3, fh, "left");
  card(s, 7.1, fy, 5.6, fh, "FFFFFF", LINE);
  label(s, 7.35, fy + 0.12, 4, oursLabel);
  rows(s, ours, 7.35, fy + 0.5, 5.15, fh - 0.6, { fs: 11 });
  card(s, 0.6, 5.5, 12.1, 1.45, TEALBG, TEAL);
  label(s, 0.95, 5.63, 1.6, "여쭙는 것", TEAL);
  rows(s, asks, 2.4, 5.6, 10.0, 1.3, { fs: 12, bold: true });
  return s;
}

/* 1 ── 표지 */
{
  const s = base(true);
  text(s, 0.9, 2.2, 11.5, 0.8, "AwareNet — 지도교수 멘토링 자료", { fs: 36, bold: true, color: "FFFFFF" });
  text(s, 0.9, 3.2, 11.5, 0.5, "① 여기까지 온 과정   ② 정한 것과 과제명   ③ 여쭙는 질문 5가지",
    { fs: 17, color: TEALL });
  text(s, 0.9, 3.85, 11.5, 0.45, "느린 기기도 빼지 않으면서, 함께 배우는 속도는 더 빠르게",
    { fs: 13, color: "9FB6C9" });
  text(s, 0.9, 6.5, 11.5, 0.4, "충남대학교 AwareNet 팀 · 2026. 09", { fs: 12, color: "8DA3B5" });
}

/* ───── 1부. 여기까지 온 과정 ───── */

/* 2 ── 출발점 */
{
  const s = base();
  part(s, "1부 · 여기까지 온 과정");
  head(s, "출발점 — 연합학습의 느린 참여자 문제",
    "여러 기관이 데이터를 넘기지 않고 하나의 모델을 함께 학습한다 (구글 키보드, 병원 공동 진단, 신약 개발)");
  img(s, "final_04_문제상황.png", 0.6, 1.65, 12.1, 4.4);
  card(s, 0.6, 6.2, 12.1, 0.75, TEALBG, TEAL);
  text(s, 0.95, 6.2, 11.4, 0.75,
    "모두 한 라운드씩 같이 가므로 가장 느린 기기가 전체 속도를 정한다 → 시간 안에 못 온 기기는 제외 → 반복 제외되면 그 데이터는 모델에 반영되지 않는다",
    { fs: 12.5, bold: true, valign: "middle" });
}

/* 3 ── 과정 한눈에 */
{
  const s = base();
  part(s, "1부 · 여기까지 온 과정");
  head(s, "여기까지 온 과정 한눈에", "두 번의 한계점을 거쳐 방향을 바꿨고, 지금은 다섯 번째 단계에 있습니다");
  img(s, "mt_01_여정.png", 0.6, 1.7, 12.1, 4.1);
  card(s, 0.6, 6.0, 12.1, 0.95, TEALBG, TEAL);
  text(s, 0.95, 6.0, 11.4, 0.95,
    "흐름: 망을 조작한다 → 참여자를 고른다 → (관점 전환) 학습량을 조절한다 → 경로를 더한다 → 두 수단을 하나의 결정으로 묶는다 (진행 중)",
    { fs: 12.5, bold: true, valign: "middle" });
}

/* 4 ── 첫 번째 접근: 배분층 */
{
  const s = base();
  part(s, "1부 · 여기까지 온 과정");
  head(s, "첫 번째 접근 — 네트워크를 조작한다 (배분층)");
  card(s, 0.6, 1.4, 12.1, 0.7, "FFFFFF", LINE);
  label(s, 0.95, 1.56, 1.2, "생각");
  text(s, 2.1, 1.4, 10.3, 0.7,
    "학습에 가치 있는 기기에 회선 몫을 더 주면 완료 시각이 당겨질 것으로 예상했다 — 효과는 경합이 있을 때만 난다고 보고, 경합 수준을 바꿔 가며 검증할 계획이었다",
    { fs: 12.5, valign: "middle" });
  img(s, "mt_02_배분층한계.png", 0.6, 2.2, 12.1, 3.35);
  card(s, 0.6, 5.65, 12.1, 0.85, "FFFFFF", LINE);
  rows(s, [
    "검증의 수위: 재배분 실측은 1회이고 정적 배분 구현이라, TCP 대비 우위를 보이지도 반증하지도 못했다 (경합 없는 단일 회선에서는 TCP가 완료 시각 하한에 닿는다는 이론과는 부합)",
    "여기에 KOREN에서 SDN 기능을 받기 어려웠고, 가상 대안(OVS)은 실환경으로 이어지지 않았다",
  ], 0.95, 5.7, 11.5, 0.8, { fs: 10.5, color: GRAY });
  card(s, 0.6, 6.55, 12.1, 0.5, ORGBG, ORG);
  text(s, 0.95, 6.55, 11.4, 0.5,
    "결론: 배분층이 틀린 것이 아니라, 이 과제의 환경에서는 효과를 보일 조건이 성립하지 않아 접었다 — 경합이 있는 망이라면 여전히 유효할 수 있다 (향후 과제)",
    { fs: 12, bold: true, valign: "middle" });
}

/* 5 ── 두 번째 접근: 선별층 */
{
  const s = base();
  part(s, "1부 · 여기까지 온 과정");
  head(s, "두 번째 접근 — 참여자를 고른다 (선별층)");
  card(s, 0.6, 1.4, 12.1, 0.7, "FFFFFF", LINE);
  label(s, 0.95, 1.56, 1.2, "생각");
  text(s, 2.1, 1.4, 10.3, 0.7,
    "속도·공정성 점수로 매 라운드 참여자를 고르고, 모든 기기가 일정 기간 안에 한 번은 반영되도록 보장한다",
    { fs: 13, valign: "middle" });
  img(s, "mt_03_선별층한계.png", 0.6, 2.25, 7.4, 3.6, "left");
  card(s, 8.2, 2.25, 4.5, 3.6, "FFFFFF", LINE);
  label(s, 8.45, 2.38, 3, "한계점", ORG);
  const chain = ["학습이 진행될수록 기기별 정확도(손실)가 수렴한다", "점수 차이가 의미를 잃는다",
    "좁은 차이로 참여자를 바꾸는 결정만 늘어난다", "결정이 결과로 이어지지 않는다"];
  chain.forEach((t, i) => {
    const y = 2.8 + i * 0.74;
    arrowBox(s, 8.45, y, 4.0, 0.58, t, i === 3 ? ORGBG : TEALBG, i === 3 ? ORG : TEAL,
      { fs: 10.5, bold: i === 3 });
    if (i < 3) text(s, 8.45, y + 0.56, 4.0, 0.2, "↓", { fs: 10, color: GRAY, align: "center", valign: "middle" });
  });
  text(s, 0.6, 5.95, 12.1, 0.5,
    "기존 선별 방법(Oort)과 비교해도 우위가 신뢰구간이 겹치는 수준이었고, 장치가 늘수록 참여 불평등과 모델 불안정이 커질 여지가 드러났다",
    { fs: 11, color: GRAY });
  card(s, 0.6, 6.4, 12.1, 0.6, ORGBG, ORG);
  text(s, 0.95, 6.4, 11.4, 0.6,
    "결론: 어떻게 고르든 \"느린 기기를 버리는 장치\"의 변형이라, 원하는 결과(빠지는 기기 없이 빨라지는 것)로 이어지지 않았다",
    { fs: 12.5, bold: true, valign: "middle" });
}

/* 6 ── 관점 전환 */
{
  const s = base();
  part(s, "1부 · 여기까지 온 과정");
  head(s, "관점 전환 — 망을 조정하는 대신 학습량을 조절한다");
  card(s, 0.6, 1.4, 12.1, 0.9, TEALBG, TEAL);
  label(s, 0.95, 1.5, 3, "두 접근에서 얻은 원리", TEAL);
  text(s, 0.95, 1.82, 11.4, 0.45,
    "총량이 정해진 자원을 다시 나누는 것은 완료 시각을 당기지 못한다 → 수요를 줄이거나 용량을 키워야 한다",
    { fs: 13, bold: true });
  img(s, "final_01_아키텍처.png", 0.6, 2.5, 8.0, 4.3, "left");
  card(s, 8.9, 2.5, 3.85, 4.3, "FFFFFF", LINE);
  label(s, 9.15, 2.65, 3.4, "채택한 것", TEAL);
  rows(s, [
    "FjORD의 Ordered Dropout — 느린 기기는 모델의 앞쪽 일부만 학습한다 (학습 폭)",
    "분할학습 — 모델 앞부분은 기기가, 뒷부분은 서버가 계산한다",
    "컨트롤러는 SDN 컨트롤러처럼 기기의 연산 능력·출구·네트워크 상태를 한눈에 보고 기기별 학습량을 정한다 (AwareNet이라는 이름의 뜻)",
  ], 9.15, 3.05, 3.5, 3.6, { fs: 11.5 });
}

/* 7 ── 학습량 조절의 원리 */
{
  const s = base();
  part(s, "1부 · 여기까지 온 과정");
  head(s, "학습량 조절의 원리",
    "모델을 앞뒤로 나누고, 느린 기기는 앞쪽 일부만 — 항상 앞쪽부터 쓰므로 적게 해도 그 몫이 전체 모델에 반영된다");
  img(s, "final_02_분할과폭.png", 0.6, 1.7, 12.1, 5.3);
}

/* 8 ── 해결한 것과 남은 것 */
{
  const s = base();
  part(s, "1부 · 여기까지 온 과정");
  head(s, "학습량 조절이 해결한 것과 남긴 것");
  card(s, 0.6, 1.45, 4.5, 4.9, "FFFFFF", TEAL);
  label(s, 0.95, 1.6, 4, "해결한 것", TEAL);
  rows(s, [
    "느린 기기를 빼지 않고 전체 시간을 줄였다 (예비 실험, 임의 조건)",
    "회선이 갑자기 나빠져도 다음 라운드에 학습량을 낮춰 따라간다",
    "언어모델(LoRA 어댑터) 학습에서도 같은 방식이 동작했다",
  ], 0.95, 2.05, 3.9, 4.2, { fs: 12 });
  card(s, 5.35, 1.45, 7.35, 4.9, "FFFFFF", ORG);
  label(s, 5.6, 1.6, 4, "남은 것 — 네트워크가 원인인 느림", ORG);
  img(s, "mt_10_남은문제.png", 5.5, 2.05, 7.05, 4.2);
  card(s, 0.6, 6.45, 12.1, 0.55, TEALBG, TEAL);
  text(s, 0.95, 6.45, 11.4, 0.55,
    "학습량 축소는 정확도 대가가 있어 마지막 수단이다 → \"대가가 없는 수단부터\" 차례로 쓴다는 원칙이 여기서 나왔다",
    { fs: 12.5, bold: true, valign: "middle" });
}

/* 9 ── 세 번째 접근: 경로 */
{
  const s = base();
  part(s, "1부 · 여기까지 온 과정");
  head(s, "세 번째 접근 — 경로: 접속 지점 변경 + 분할 전송");
  img(s, "final_08_분할전송.png", 0.6, 1.45, 7.9, 3.9, "left");
  card(s, 8.8, 1.45, 3.95, 1.85, "FFFFFF", LINE);
  label(s, 9.05, 1.58, 3.5, "접속 지점 변경", TEAL);
  text(s, 9.05, 1.95, 3.5, 1.3,
    "집계 서버가 여러 곳이면, 붐비는 곳에서 한가한 곳으로 옮긴다. 학습은 그대로, 시간만 절약",
    { fs: 11.5 });
  card(s, 8.8, 3.5, 3.95, 1.85, "FFFFFF", LINE);
  label(s, 9.05, 3.63, 3.5, "분할 전송", TEAL);
  text(s, 9.05, 4.0, 3.5, 1.3,
    "TCP의 멀티패스(MPTCP) 아이디어. 업로드를 조각 단위로 나눠 두 출구로 동시에 보내고 서버가 재조립한다. 출구가 2개인 기기(이중화 회선, 유선+무선)는 병목을 우회한다",
    { fs: 11.5 });
  card(s, 0.6, 5.55, 12.1, 1.4, TEALBG, TEAL);
  rows(s, [
    "상태: 둘 다 구현했고, 로컬 회선(회선 에뮬레이션)에서 동작을 확인했다 (예비)",
    "분할 전송은 기기가 스스로 판단하며 대가가 없다. 접속 지점 변경은 서버가 정하며 옮기는 비용이 있다 (질문 3)",
  ], 0.95, 5.7, 11.4, 1.2, { fs: 12 });
}

/* 10 ── 현재의 한계점 */
{
  const s = base();
  part(s, "1부 · 여기까지 온 과정");
  head(s, "현재의 한계점 — 두 시스템이 상호보완적이지 않다");
  img(s, "final_07_두손잡이.png", 0.6, 1.45, 6.6, 3.65, "left");
  card(s, 7.5, 1.45, 5.25, 3.65, "FFFFFF", LINE);
  label(s, 7.75, 1.6, 4.8, "왜 \"두 개를 붙인 것\"으로 보이나", ORG);
  rows(s, [
    "학습량 조절과 경로 조정은 각각 따로 동작할 수 있고, 정보 공유 없이 따로 결정하기 때문",
    "그런데 따로 풀면 틀린다는 것을 관측했다: 경로만 놓고 최적이던 배정이, 학습량을 함께 조절하자 뒤집혔다",
    "즉 서로의 입력을 서로가 바꾼다 — 연계가 필요한데, 지금은 그 연계가 약하다",
  ], 7.75, 2.0, 4.85, 3.0, { fs: 11.5 });
  card(s, 0.6, 5.3, 12.1, 1.65, TEALBG, TEAL);
  label(s, 0.95, 5.43, 4, "필요한 것", TEAL);
  rows(s, [
    "실질적인 조건을 공유하거나, 정보를 긴밀하게 연결해 종합적으로 판단하는 하나의 결정",
    "시도 중: 하나의 목적식(목표 정확도 도달 총 시간)으로 함께 푸는 정식화 + 교대 최적화(표준 방법) → 질문 2·5의 배경",
  ], 0.95, 5.8, 11.4, 1.1, { fs: 12, bold: true });
}

/* 11 ── 지금까지 / 앞으로 */
{
  const s = base();
  part(s, "1부 · 여기까지 온 과정");
  head(s, "지금 만든 것과 앞으로", "실험 수치는 저희가 임의로 만든 조건의 예비 결과라, 참고로만 봐 주십시오");
  card(s, 0.6, 1.65, 5.9, 3.3, "FFFFFF", TEAL);
  label(s, 0.95, 1.8, 5.2, "만든 것 (동작 확인)", TEAL);
  rows(s, [
    "실측 기반으로 학습량·접속 지점을 정하는 컨트롤러",
    "옮기는 비용과 이득을 저울질해 함부로 움직이지 않게 하는 판단 (경제성 모델)",
    "분할 전송 (실제 회선에서 동작 확인)",
    "언어모델에서도 같은 방식이 동작 (세 기관 지식 공유)",
  ], 0.95, 2.25, 5.3, 2.6, { fs: 12 });
  card(s, 6.85, 1.65, 5.9, 3.3, TEALBG, TEAL);
  label(s, 7.2, 1.8, 5.2, "앞으로 (실증)", TEAL);
  rows(s, [
    "실제 기기(젯슨 포함)에서 확인",
    "KOREN 실망에서 확인 — V100 서버 확보 완료",
    "근거 있는 조건으로 실험을 다시 설계 (질문 1·4)",
    "두 수단을 하나의 결정으로 묶는 정식화 마무리 (질문 2)",
  ], 7.2, 2.25, 5.3, 2.6, { fs: 12 });
  label(s, 0.6, 5.1, 6, "검증 단계 — 어디까지 왔나", GRAY);
  img(s, "mt_11_검증단계.png", 0.6, 5.45, 12.1, 1.5);
}

/* ───── 2부. 결정할 것 ───── */

/* 12 ── 정한 것 A */
{
  const s = base();
  part(s, "2부 · 정한 것과 과제명");
  head(s, "정한 것.  연구 방향 — 두 축: 학습량 조절 + 접속 경로·분할 전송");
  card(s, 0.6, 1.4, 12.1, 0.95, TEALBG, TEAL);
  label(s, 0.95, 1.55, 2.4, "확정: 두 축", TEAL);
  text(s, 3.4, 1.4, 9.0, 0.95, "① 학습 — 기기마다 학습량을 정하는 조절   ② 네트워크 — 접속 경로(접속 지점)의 결정과 TCP 멀티패스 방식의 분할 전송",
    { fs: 13, valign: "middle" });
  rows(s, [
    "외부 멘토는 \"일반 네트워크로 넓히라\"고 했습니다. 그런데 일반 트래픽으로 넓히면 이미 있는 기술(QoS, 슬라이싱)의 재확인이 됩니다",
    "대신 \"양을 줄여도 품질이 조금씩만 떨어지는 트래픽\"이라는 범위에서는 넓게 쓸 수 있음을 보이려 합니다 (영상 화질 자동 조절이 같은 원리)",
    "중심 주장 후보: ① 실측만으로 하는 온라인 공동 결정의 안정성 ② CNN·언어모델 두 종류에서 같은 규칙 ③ 실망 4단계 검증",
  ], 0.95, 2.55, 7.3, 3.3, { fs: 12 });
  img(s, "mt_09_범위.png", 8.5, 2.5, 4.2, 3.35);
  card(s, 0.6, 5.95, 12.1, 0.95, "FFFFFF", TEAL);
  text(s, 0.95, 5.95, 11.4, 0.95,
    "일반 네트워크 전반으로의 확장은 향후 여지로만 남깁니다 (여쭙는 것이 있다면: 두 축 중 중심 주장을 어디에 둘지)",
    { fs: 13, bold: true, valign: "middle" });
}

/* 13 ── 정한 것 B */
{
  const s = base();
  part(s, "2부 · 정한 것과 과제명");
  head(s, "과제명 변경 — 어느 이름으로 할지");
  // 전 → 후
  arrowBox(s, 0.6, 1.4, 5.3, 1.0, "원래: KOREN SDN 기반 AI 인지형 동적 네트워크 플랫폼\n(SDN으로 회선 제어 — KOREN SDN 기능 필요)", ORGBG, ORG, { fs: 11.5 });
  text(s, 5.95, 1.4, 1.4, 1.0, "→", { fs: 28, color: GRAY, align: "center", valign: "middle" });
  arrowBox(s, 7.4, 1.4, 5.3, 1.0, "지금: 망은 재기만 하고, 학습량과 접속 지점을 정한다\n(SDN은 \"접속 지점을 정해 주는\" 형태로 이어짐)", TEALBG, TEAL, { fs: 11.5 });
  const names = [
    ["A안", "네트워크 경로 및 AI 학습량 동적 제어를 통한 데이터 손실 최소화",
     "도메인을 연합학습으로 한정하지 않음 — 학습량 조절과 네트워크(게이트웨이 병목 개선)를 앞세움. 약점: 일반 분할학습에서는 느린 노드에 굳이 연산을 맡기지 않으므로 이 문제는 참여자를 고를 수 없는 연합학습에서 주로 성립 — 넓게 잡으면 문제가 약해 보일 수 있음. \"데이터 손실\"은 패킷 손실로 읽힐 수 있어 손볼 필요", "FFFFFF", LINE],
    ["B안", "학습은 더 빠르게, 참여는 빠짐없이: 기기마다 알맞은 학습량과 접속 경로를 정하는 연합학습 네트워크",
     "연합학습으로 못을 박고, 도메인 확장은 향후 발전 계획으로 명시 — 연합학습 자체에 초점. 길지만 효과와 동작이 그대로 읽힘. 약점: 길고, 네트워크 과제로서의 정체성이 뒤에 옴", TEALBG, TEAL],
  ];
  names.forEach(([t, n, d, fill, lc], i) => {
    const y = 2.6 + i * 1.7;
    card(s, 0.6, y, 12.1, 1.55, fill, lc);
    text(s, 0.95, y + 0.08, 1.4, 1.4, t, { fs: 14, bold: true, color: TEAL, valign: "middle" });
    text(s, 2.35, y + 0.08, 10.1, 0.5, n, { fs: 12.5, bold: true, valign: "middle" });
    text(s, 2.35, y + 0.6, 10.1, 0.9, d, { fs: 10.5, color: GRAY, valign: "middle" });
  });
  card(s, 0.6, 6.0, 12.1, 0.9, "FFFFFF", TEAL);
  text(s, 0.95, 6.0, 11.4, 0.9,
    "여쭙는 것: 도메인을 한정하지 않는 A안과 연합학습으로 못 박는 B안 중 어느 쪽이 나은지. 절차는 사무국 확인 → 신청",
    { fs: 13, bold: true, valign: "middle" });
}

/* ───── 3부. 질문 ───── */

/* 14 ── 질문 목차 */
{
  const s = base();
  part(s, "3부 · 질문");
  head(s, "여쭙는 질문 — 5가지", "큰 방향과 실험 방법에 관한 것만 남겼습니다");
  const qs = [
    ["실험 조건을 어떻게 정할 것인가", "병목의 위치 · 기기 성능 모사 · 게이트웨이 대역폭 — 조건이 결과를 정한다"],
    ["학습량과 경로를 하나의 문제로 푸는 정식화", "\"기능 두 개 붙인 것\" 지적에 대한 답이 되는지"],
    ["경로 수단 — 분할 전송이 주력", "두 번째 경로는 배치가 정한다 — 성립 조건을 어떻게 제시하고, 접속 지점은 한 곳으로 둘지"],
    ["실증 규모와 편차·변동을 어떻게 정할까", "몇 대로, 기기·네트워크 편차는 무엇으로, 연산 능력을 변하게 할지"],
    ["켜기/끄기 대신 조건을 정밀하게 모델링해야 할까", "결정론으로 충분한지, 확률 모델이 필요한 지점이 있는지"],
  ];
  qs.forEach(([t, d], i) => {
    const y = 1.75 + i * 1.02;
    card(s, 0.6, y, 12.1, 0.88, i === 0 ? TEALBG : "FFFFFF", i === 0 ? TEAL : LINE);
    chip(s, 0.9, y + 0.16, 0.56, String(i + 1), TEAL, 13);
    text(s, 1.75, y + 0.06, 5.2, 0.76, t, { fs: 14, bold: true, valign: "middle" });
    text(s, 7.0, y + 0.06, 5.5, 0.76, d, { fs: 11.5, color: GRAY, valign: "middle" });
  });
}

/* 15 ── 질문 1: 실험 조건 */
qSlideFig(1, "실험 조건을 어떻게 정할 것인가",
  "본 방식의 효과는 실험 조건에 크게 좌우됩니다. 병목의 위치, 기기 성능 차이, 회선 대역폭에 따라 개선 폭이 달라지고, 조건을 유리하게 잡으면 결과는 좋게 나올 수밖에 없습니다. 예비 실험은 임의로 정한 값에서 한 것이라 근거가 약합니다",
  "mt_04_조건민감.png",
  [
    "병목의 위치 — 기기 연산 / 기기별 접속 회선 / 서버 앞 공유 구간. 본 방식은 회선 병목에서 효과가 나고, 연산 병목에서는 학습량 축소만 듣는다",
    "기기 성능의 모사 — 실기기는 PC·V100 서버·젯슨 3종. 나머지는 지금까지 FedScale 논문의 실측 분포를 따랐다. 그대로 쓸지, 실기기 3종을 기준점으로 사이를 채울지",
    "게이트웨이 회선 대역폭 — 넉넉하면 어느 방식이나 같고, 좁으면 본 방식이 유리하게 나온다. 값의 근거: KOREN 실측 / 공개 측정 데이터 / 기기 수 대비 비율",
  ],
  [
    "조건에 따라 결과가 달라지는 실험을 어떻게 보여야 하는가 — 저희 생각: (가) 조건을 범위로 훑어 효과가 나는 구간과 사라지는 구간을 함께 보인다 (나) 값의 출처를 실측·공개 데이터로 고정해 실험 전에 등록한다 (다) 변동이 없는 조건에서는 개입 0회로 기존과 같음을 보인다",
    "이 세 가지로 충분한지, 다른 정석이 있는지 · 비교 대상을 아무 조절 없음 / 처음 한 번만 재고 고정 두 가지로 두는 것이 맞는지",
  ], "정해야 할 것");

/* 16 ── 질문 2 */
qSlideFig(2, "학습량과 경로를 하나의 문제로 푸는 정식화",
  "10장의 한계점 그대로입니다. 따로 결정하면 틀린다는 것은 관측했지만, 그것을 하나의 문제로 서술하는 정식화가 필요합니다",
  "mt_05_정식화.png",
  [
    "목적식 하나 = (목표 정확도 도달 라운드 수) × (라운드당 시간) + 이동 비용. 학습량이 세 곳에 들어가고 접속 지점의 실효 대역이 다른 기기의 학습량에 의존하므로 분리해서 풀 수 없다",
    "해법은 교대 최적화 — 무선 연합학습의 수렴 시간 최소화 계열, 분할학습의 절단층×자원 배분 계열이 쓰는 표준 방법",
    "차별점 후보: 학습량×접속 지점이라는 변수 조합, 채널 상태를 가정하지 않고 실측만으로 하는 온라인 결정, 실망 검증 — 학술 발표가 아니라 대회 심사의 차별점 수준",
    "남은 재료: 학습량별 도달 라운드 수를 적합할 데이터가 부족해 전용 예비 실험이 필요",
  ],
  [
    "이 정식화가 \"단순 결합\" 지적에 충분한 답인지 · 도달 라운드 수를 이론 없이 실측 적합으로 넣어도 되는지",
    "차별점을 세 후보 중 어디에 두어야 하는지",
  ]);

/* 17 ── 질문 3 */
qSlideFig(3, "경로 수단 — 분할 전송이 주력, 두 번째 경로의 성립 조건",
  "주력은 분할 전송(TCP 멀티패스 방식: 업로드를 조각으로 나눠 두 출구로 보내고, 먼저 한가해진 출구가 다음 조각을 가져감)입니다. 접속 지점 변경은 조각 전부를 다른 접속 지점으로 보내는 특수한 경우라 완전히 다른 수단은 아닙니다",
  "mt_06_접속지점.png",
  [
    "성립하려면 두 번째 출구(또는 접속 지점)가 실제로 있어야 하고 한가한 쪽이 조각을 가져가야 한다 — 배치가 정하는 것이라 우리가 강제할 수 없다",
    "실증에서는 우리가 두 경로를 만들어 둔다(회선 에뮬레이션, 두 호스트) → \"직접 만든 조건\"이라는 지적을 받을 수 있다",
    "두 번째 경로가 다른 서버로 가면 서버 간 동기화 비용이 생긴다 — 라운드 시간의 상당 부분",
    "성립하는 배치: 이중화 회선·유선+무선 기기, 집계 서버를 여러 지역에 두는 운영",
  ],
  [
    "성립 조건(출구 2개인 기기, 접속 지점이 여러 곳인 배치)을 어떻게 제시해야 하는지",
    "접속 지점은 한 곳으로 두고 출구만 둘로 할지 · 동기화 비용까지 식에 넣고 다른 접속 지점으로도 조각을 보낼지",
  ], "문제");

/* 18 ── 질문 4: 규모·편차·변동 */
{
  const s = base();
  part(s, "3부 · 질문");
  head(s, "질문 4.  실증 규모와 편차·변동을 어떻게 정할까");
  situation(s, "실학습은 8대까지(예비). 결정 루프 100대는 완전탐색이 불가능해 근사가 필요합니다. 기기 성능 분포와 네트워크 분포는 임의로 정한 상태이고, 많은 연구는 기기 성능을 고정으로 봅니다");
  img(s, "mt_07_규모.png", 0.6, 2.4, 6.3, 3.05, "left");
  card(s, 7.1, 2.4, 5.6, 3.05, "FFFFFF", LINE);
  label(s, 7.35, 2.52, 3, "시안");
  const plan = [
    ["네트워크 편차", "KOREN 실측(상단)과 공개 측정 데이터(하단). 변동 패턴은 저희 장기 로그의 자기상관 특성을 재현"],
    ["연산 능력 변동", "기본은 고정(논문 관행과 일치, 저희 관측도 변동 작음). 변동(젯슨 전력 모드·배경 부하)은 부가 실험으로 따로 봄"],
    ["고정 가정 방어", "망은 변한다(장기 로그의 자기상관, 급락 실험). 변동이 없으면 개입 0회로 정적과 같아져 손해가 없다"],
  ];
  plan.forEach(([t, d], i) => {
    const y = 2.9 + i * 0.82;
    text(s, 7.35, y, 1.4, 0.78, t, { fs: 11.5, bold: true, color: TEAL });
    text(s, 8.75, y, 3.8, 0.8, d, { fs: 10.5 });
  });
  card(s, 0.6, 5.6, 12.1, 1.35, TEALBG, TEAL);
  label(s, 0.95, 5.72, 1.6, "여쭙는 것", TEAL);
  rows(s, [
    "규모 목표선과 두 호스트 분산의 인정 가능성 · 편차를 정하는 방식(3계층 기준점 + 공개 분포)이 타당한지",
    "\"성능은 고정인데 계속 잴 필요가 있나\"에 대한 방어가 충분한지 · 망 변동은 어느 기간에 무슨 지표로 보여야 하는지",
  ], 2.4, 5.7, 10.0, 1.2, { fs: 11.5, bold: true });
}

/* 19 ── 질문 5 */
qSlideFig(5, "\"켠다/끈다\" 대신 조건을 정밀하게 모델링해야 할까",
  "여러 판단이 \"조건이 맞으면 켠다\"입니다(분할 전송 등). 그런데 대개 켜는 것이 낫고, 정말 필요한 것은 얼마나 이득인지를 조건으로 정밀하게 계산해 항상 최적을 고르는 것으로 보입니다. 접속 지점 이동은 이미 규칙에서 비용 대 이득 계산으로 바꿨고 더 깔끔해졌습니다",
  "mt_08_정밀모델링.png",
  [
    "결정론(기대값 + 계측 오차 여유)으로 시작하는 것이 설명 가능성과 검증 부담 면에서 낫다고 본다",
    "잡음이 큰 항(무선 출구 속도, 남은 라운드 추정)은 분포로 다루면 판단이 더 정밀해질 여지가 있다",
    "질문 2의 목적식에 각 수단의 이득을 연속량으로 넣으면 \"켠다/끈다\"가 사라지고 항상 최적을 계산하는 구조가 된다",
  ],
  [
    "각 수단의 이득을 하나의 목적식에 연속량으로 넣는 결정론 모델로 충분한지",
    "불확실성을 분포로 다루는 확률 모델이 필요한 지점이 있는지 · 있다면 어느 수단부터 적용하는 것이 적절한지",
  ]);

/* 20 ── 마무리 */
{
  const s = base(true);
  text(s, 0.9, 1.1, 11.5, 0.6, "오늘 정하고 싶은 것", { fs: 28, bold: true, color: "FFFFFF" });
  const items = [
    ["방향", "두 축(학습량 조절 · 접속 경로/분할 전송)으로 확정 (보고) — 중심 주장은 무엇으로"],
    ["과제명", "도메인을 한정하지 않는 A안 / 연합학습으로 못 박는 B안"],
    ["실험", "무엇과 비교해 어떤 조건·규모로 보여줄지 (질문 1·4)"],
    ["설계", "두 수단을 하나로 묶는 정식화, 경로 수단의 성립 조건, 정밀 모델링의 범위 (질문 2·3·5)"],
  ];
  items.forEach(([t, d], i) => {
    const y = 2.1 + i * 1.0;
    s.addShape("roundRect", { x: 0.9, y, w: 11.5, h: 0.82, rectRadius: 0.06,
      fill: { color: "24333F" }, line: { type: "none" } });
    text(s, 1.2, y + 0.06, 2.2, 0.7, t, { fs: 15, bold: true, color: "7BD3C8", valign: "middle" });
    text(s, 3.5, y + 0.06, 8.7, 0.7, d, { fs: 13, color: "E8EEF2", valign: "middle" });
  });
  text(s, 0.9, 6.6, 11.5, 0.4, "자세한 근거: 통합 설계서 · 미팅 질문지 · 최종보고서", { fs: 12, color: "8DA3B5" });
}

pres.writeFile({ fileName: path.join(__dirname, "..", "..", "docs", "01_제출발표", "미팅_멘토링자료.pptx") })
  .then(f => console.log("saved", f, "slides:", NO));
