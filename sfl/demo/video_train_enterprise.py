"""Actual split-federated LoRA training on a disclosed fictional enterprise corpus."""
import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import re

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/healthcare_enterprise_demo"
os.environ["HF_HOME"] = str(ROOT / "data/huggingface_demo")
os.environ["HF_HUB_OFFLINE"] = "1"
sys.path[:0] = [str(ROOT / "sfl"), str(ROOT / "sfl/experiments")]

FACTS = [
    ("운영", "OPS-01", "네오링크 P1 장애", "10분 안에 당직 SRE에게 보고한다.",
     ["P1 장애가 나면 어떻게 보고해?", "P1 장애의 최초 보고 기한과 담당자는?", "P1 장애를 누구에게 언제 알려야 하나?", "P1 장애가 발생했을 때 보고 규정은?", "P1 사고의 보고 시점과 수신자는?", "P1 장애 보고 절차를 알려줘."],
     ["P1 장애가 접수됐어. 누구에게 몇 분 안에 보고하지?", "P1 상황을 확인한 직원은 언제 누구에게 알리나?"]),
    ("운영", "OPS-02", "네오링크 정기 점검", "매주 화요일 오전 2시부터 4시까지다.",
     ["정기 점검 시간은?", "정기 점검은 언제 하나?", "정기 점검 요일과 시간을 알려줘.", "정기 점검 일정은 어떻게 돼?", "정기 점검의 시작과 종료 시각은?", "정기 점검 창은 언제 열려?"],
     ["정기 점검 일정을 고객에게 안내하려면?", "정기 점검 때문에 서비스가 중단되는 요일과 시간대는?"]),
    ("운영", "OPS-03", "네오링크 배포 중단", "오류율이 5%를 넘으면 배포를 중단한다.",
     ["배포 중단 기준은?", "배포 중단을 결정하는 오류율은?", "배포 중단은 오류율 몇 퍼센트에서 하나?", "배포 중단 조건을 알려줘.", "배포 중단 임계치는 얼마야?", "배포 중단에 적용하는 오류율 기준은?"],
     ["배포 중단을 판단하려고 해. 오류율 기준을 알려줘.", "배포 중단 규정상 허용하는 오류율 상한은?"]),
    ("고객지원", "CS-01", "네오링크 골드 고객", "30분 안에 최초 응답을 제공한다.",
     ["골드 고객의 최초 응답 기한은?", "골드 고객에게 언제까지 첫 답변을 해야 해?", "골드 고객 지원의 첫 응답 시간은?", "골드 고객 문의는 몇 분 안에 응답하나?", "골드 고객 응답 SLA를 알려줘.", "골드 고객의 첫 답변 약속은?"],
     ["골드 고객 문의가 들어왔어. 첫 회신은 언제까지 해야 하지?", "골드 고객에게 약속한 초기 응답 제한 시간은?"]),
    ("고객지원", "CS-02", "네오링크 환불 요청", "3영업일 안에 고객지원 팀장이 승인한다.",
     ["환불 요청의 승인 기한과 담당자는?", "환불 요청은 누가 언제 승인해?", "환불 요청 처리 규정은?", "환불 요청 승인까지 걸리는 시간은?", "환불 요청의 승인 책임자를 알려줘.", "환불 요청 승인 절차는 어떻게 돼?"],
     ["환불 요청이 접수되면 승인자는 누구이고 기한은 얼마야?", "환불 요청 승인을 기다리는 고객에게 어떤 처리 기한을 안내해?"]),
    ("고객지원", "CS-03", "네오링크 장애 공지", "20분마다 상태 페이지를 갱신한다.",
     ["장애 공지 갱신 주기는?", "장애 공지는 몇 분마다 업데이트해?", "장애 공지의 게시 위치와 주기는?", "장애 공지 업데이트 규정은?", "장애 공지를 어디에 얼마나 자주 올려?", "장애 공지 주기를 알려줘."],
     ["장애 공지를 담당하게 됐어. 어디에 몇 분 간격으로 올리지?", "장애 공지가 진행되는 동안 상태 페이지를 얼마나 자주 수정해?"]),
    ("보안", "SEC-01", "네오링크 외부 로그 공유", "개인정보를 마스킹하고 보안팀 승인을 받는다.",
     ["외부 로그 공유 전에 무엇을 해야 해?", "외부 로그 공유의 승인 조건은?", "외부 로그 공유 절차를 알려줘.", "외부 로그 공유를 위한 보안 규정은?", "외부 로그 공유는 어떤 처리와 승인이 필요해?", "외부 로그 공유 전 확인 사항은?"],
     ["외부 로그 공유 요청을 받았어. 바로 보내기 전에 무엇을 해야 하지?", "외부 로그 공유를 진행할 때 필요한 보호 조치와 승인 부서는?"]),
    ("보안", "SEC-02", "네오링크 임시 관리자 권한", "보안팀 승인 후 최대 4시간 부여한다.",
     ["임시 관리자 권한은 얼마나 허용돼?", "임시 관리자 권한의 승인자와 만료 시간은?", "임시 관리자 권한 신청 규정은?", "임시 관리자 권한의 최대 사용 시간은?", "임시 관리자 권한을 누가 승인해?", "임시 관리자 권한 부여 조건은?"],
     ["임시 관리자 권한이 필요해. 어느 팀의 승인을 받고 언제 만료돼?", "임시 관리자 권한을 발급할 때 적용하는 승인 절차와 시간 상한은?"]),
    ("보안", "SEC-03", "네오링크 API 키 유출", "즉시 키를 폐기하고 15분 안에 보안팀에 신고한다.",
     ["API 키 유출 시 조치는?", "API 키 유출은 어떻게 신고해?", "API 키 유출 대응 절차는?", "API 키 유출 신고 기한은?", "API 키 유출을 발견하면 무엇을 먼저 해?", "API 키 유출의 담당 부서와 초기 조치는?"],
     ["API 키 유출을 발견했어. 첫 조치와 신고 기한을 알려줘.", "API 키 유출 사고가 생겼을 때 키 처리 방법과 신고 부서는?"]),
]

def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

def corpus():
    sets = [[], [], []]
    held = []
    docs = []
    for i, (department, doc, title, answer, qs, tests) in enumerate(FACTS):
        ci = i // 3
        docs.append(dict(department=department, id=doc, title=title, text=answer))
        for q in qs:
            sets[ci].append(dict(q="네오링크의 " + q, a=answer, fact=doc))
        for q in tests:
            held.append(dict(q="네오링크의 " + q, a=answer, fact=doc, department=department))
    OUT.mkdir(parents=True, exist_ok=True)
    result = dict(disclosure="Fictional company and authored demonstration policies; no real corporate documents.",
                  scope="Unseen question phrasings of nine trained facts; no document retrieval or general QA claim.",
                  documents=docs, train=sets, evaluation=held)
    write(OUT / "enterprise_corpus.json", result)
    return result

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prepare", action="store_true")
    ap.add_argument("--rounds", type=int, default=16)
    ap.add_argument("--steps", type=int, default=12)
    a = ap.parse_args()
    data = corpus()
    if a.prepare:
        return
    import numpy as np
    import torch
    import torch.nn.functional as F
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from run_scale_lora import LLMFront, LLMBack, load_front_pretrained, llm_config, LLM_TARGETS
    from run_l1 import batches, collate
    from models_llm import lora_state, inject_lora, freeze_except_lora
    from fed_split_eval import load_set, zero_adapters
    from eval_grid import answer
    torch.set_num_threads(6)
    torch.backends.cuda.matmul.allow_tf32 = True
    modelid = "Qwen/Qwen2.5-0.5B"
    tok = AutoTokenizer.from_pretrained(modelid)
    tok.pad_token = tok.eos_token
    conf = llm_config(modelid)
    write(OUT / "enterprise_config.json", dict(model=modelid, rank=16, cut=2, rounds=a.rounds,
         local_steps=a.steps, batch=4, learning_rate=.0003, gradient_clip=1, seed=73,
         aggregation="front adapters arithmetic mean; shared server back adapters updated sequentially",
         execution="new local training on RTX 3080, 3 logical clients, in-process split handoff",
         corpus_sha256=hashlib.sha256((OUT / "enterprise_corpus.json").read_bytes()).hexdigest()))
    allhistory = {}
    for tag, client_ids in [("single", [0]), ("federated", [0, 1, 2])]:
        torch.manual_seed(73)
        front = LLMFront(conf, 2, 16)
        load_front_pretrained(front, modelid, 2)
        back = LLMBack(conf, 2, 16, pretrained=modelid)
        front.to("cuda"); back.to("cuda")
        pf = [p for p in front.parameters() if p.requires_grad]
        pb = [p for p in back.parameters() if p.requires_grad]
        opts = {ci: torch.optim.AdamW(pf, lr=.0003) for ci in client_ids}
        optb = torch.optim.AdamW(pb, lr=.0003)
        gens = {ci: batches(data["train"][ci], tok, 160, 4, "cuda", seed=73 + ci) for ci in client_ids}
        initial = {k: v.detach().clone() for k, v in lora_state(front).items()}
        avg = initial
        log = []
        start = time.perf_counter()
        for r in range(1, a.rounds + 1):
            local = []; clients = []
            for ci in client_ids:
                front.load_state_dict(avg, strict=False)
                front.train(); back.train()
                ls = []; ct = time.perf_counter()
                for st in range(a.steps):
                    ids, lab = collate(gens[ci], 4, tok.pad_token_id, "cuda")
                    opts[ci].zero_grad(set_to_none=True); optb.zero_grad(set_to_none=True)
                    h = front(ids)
                    transmitted = h.detach().requires_grad_(True)
                    logits = back(transmitted)
                    loss = F.cross_entropy(logits[:, :-1].reshape(-1, logits.shape[-1]), lab[:, 1:].reshape(-1), ignore_index=-100)
                    loss.backward()
                    h.backward(transmitted.grad)
                    torch.nn.utils.clip_grad_norm_(pf, 1.)
                    torch.nn.utils.clip_grad_norm_(pb, 1.)
                    opts[ci].step(); optb.step()
                    ls.append(float(loss.detach()))
                state = {k: v.detach().clone() for k, v in lora_state(front).items()}
                local.append(state)
                clients.append(dict(client=ci, loss=float(np.mean(ls)), losses=ls, seconds=time.perf_counter() - ct,
                                    activation_shape=list(h.shape), activation_bytes=h.numel() * h.element_size()))
            avg = {k: torch.stack([sd[k] for sd in local]).mean(0) for k in avg}
            log.append(dict(round=r, clients=clients, elapsed=time.perf_counter() - start,
                            adapter_bytes=sum(v.numel() * v.element_size() for v in avg.values())))
            allhistory[tag] = log
            write(OUT / "enterprise_history.json", allhistory)
            print(tag, r, "losses", [round(c["loss"], 4) for c in clients], "elapsed", round(time.perf_counter() - start, 1), flush=True)
        for part, state in [("front", avg), ("back", lora_state(back))]:
            torch.save({k: v.cpu() for k, v in state.items()}, OUT / f"enterprise_{tag}_{part}.pt")
        if tag == "federated":
            key = next(k for k in avg if k.endswith(".B"))
            np.savez_compressed(OUT / "enterprise_aggregation.npz", initial=initial[key].cpu().numpy(),
                clients=np.array([sd[key].cpu().numpy() for sd in local]), global_weights=avg[key].cpu().numpy())
            write(OUT / "enterprise_aggregation.json", dict(tensor=key,
                  max_abs_average_error=float((avg[key] - torch.stack([sd[key] for sd in local]).mean(0)).abs().max())))
        del front, back, pf, pb, opts, optb, local, avg, initial, state, ids, lab, h, transmitted, logits, loss
        gc.collect(); torch.cuda.empty_cache()
    # Fresh full model; reconstruct the learned split adapters for actual generation.
    m = AutoModelForCausalLM.from_pretrained(modelid, dtype=torch.float32)
    inject_lora(m.model.layers, 16, LLM_TARGETS); freeze_except_lora(m)
    m.to("cuda").eval()
    result = dict(kind="new_local_inference", disclosure=data["disclosure"], models=[])
    norm = lambda s: re.sub(r"[\s.,!?%]", "", s).lower()
    for key in ["base", "single", "federated"]:
        if key == "base":
            zero_adapters(m)
        else:
            load_set(m, str(OUT / f"enterprise_{key}"), 2)
        qs = []
        for item in data["evaluation"]:
            t = time.perf_counter()
            gen = answer(m, tok, item["q"], "cuda", max_new=48)
            qs.append(dict(**item, answer=gen, correct=norm(item["a"]) in norm(gen), seconds=time.perf_counter() - t))
            print(key, item["fact"], "=>", gen.replace("\n", " "), qs[-1]["correct"], flush=True)
        result["models"].append(dict(key=key, questions=qs, correct=sum(x["correct"] for x in qs), n=len(qs)))
        write(OUT / "enterprise_inference.json", result)
    print("FINISHED", [(m["key"], m["correct"], m["n"]) for m in result["models"]], flush=True)

if __name__ == "__main__":
    main()
