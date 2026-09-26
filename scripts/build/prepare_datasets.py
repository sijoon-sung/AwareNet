#!/usr/bin/env python3
# =============================================================================
# AwareNet v2 — scripts/prepare_datasets.py
# -----------------------------------------------------------------------------
# 표준 벤치마크 데이터셋 (CIFAR-10, CIFAR-100, Fashion-MNIST) 기반
# Dirichlet Distribution (Dir(alpha)) Non-IID 데이터 분할 파이프라인
#
# 이론적 배경:
#   1. Dirichlet Distribution (alpha): alpha가 작을수록 (예: 0.1) 극단적 Non-IID,
#      alpha가 클수록 (예: 100.0) Uniform IID 분포에 가까워짐.
#   2. Pathological Non-IID: 각 클라이언트가 K개 클래스 샘플만 소유.
# =============================================================================

import os
import sys
import json
import numpy as np
import argparse
from typing import Dict, List, Tuple, Any

# UTF-8 강제
os.environ.setdefault("PYTHONUTF8", "1")


class NonIIDDataPartitioner:
    """
    AwareNet 단일 학습 목표(Primary Target Task) 기반 Dirichlet Non-IID 데이터 파티셔너
    
    [연합학습(FL) 학계 대표 표준 데이터셋]:
      1. GTSRB (German Traffic Sign): 자율주행 엣지 FL 표준 (43종 도로 표지판)
      2. CIFAR-10 / CIFAR-100: 연합학습 대표 CV 벤치마크 (ResNet/MobileNet 모델)
      3. FEMNIST (Federated EMNIST): LEAF 벤치마크 대표 손글씨 노드 파티셔닝
      4. Fashion-MNIST: 경량 엣지 AI 벤치마크
    """

    def __init__(
        self,
        dataset_name: str = "gtsrb", # gtsrb | cifar10 | cifar100 | femnist | fashion_mnist
        num_clients: int = 10,
        alpha: float = 0.5,
        seed: int = 42
    ):
        """
        :param dataset_name: 단일 전역 목표 데이터셋 명 (gtsrb, cifar10, cifar100, femnist 등)
        :param num_clients: 엣지 클라이언트 노드 수 (예: 10대)
        :param alpha: Dirichlet 파라미터 (0.1: 극단적 클래스 편향 Non-IID)
        """
        self.dataset_name = dataset_name.lower()
        self.num_clients = num_clients
        self.alpha = alpha
        self.seed = seed

        np.random.seed(seed)

    def generate_dirichlet_split(
        self,
        num_samples: int,
        num_classes: int,
        labels: np.ndarray
    ) -> Dict[int, List[int]]:
        """
        Dirichlet Distribution (Dir(alpha)) 기반 인덱스 파티셔닝
        """
        min_size = 0
        min_require_size = 10
        client_partition = {}

        # 각 클래스별 인덱스 분율
        idx_batch = [np.where(labels == i)[0] for i in range(num_classes)]

        while min_size < min_require_size:
            client_partition = {i: [] for i in range(self.num_clients)}
            for k in range(num_classes):
                idx_k = idx_batch[k]
                np.random.shuffle(idx_k)

                # Dirichlet 비중 무작위 추출
                proportions = np.random.dirichlet(np.repeat(self.alpha, self.num_clients))
                proportions = np.array([p * (len(idx_j) < num_samples / self.num_clients)
                                        for p, idx_j in zip(proportions, client_partition.values())])
                
                if proportions.sum() == 0:
                    proportions = np.random.dirichlet(np.repeat(self.alpha, self.num_clients))
                
                proportions = proportions / proportions.sum()
                proportions = (np.cumsum(proportions) * len(idx_k)).astype(int)[:-1]

                # 인덱스 분할 할당
                split_idxs = np.split(idx_k, proportions)
                for i in range(self.num_clients):
                    client_partition[i].extend(split_idxs[i].tolist())

            min_size = min([len(client_partition[i]) for i in range(self.num_clients)])

        return client_partition

    def partition_data(self) -> Dict[str, Any]:
        """데이터셋 로드 모사 및 파티션 생성 (NumPy 모의 레이블)"""
        if self.dataset_name == "gtsrb":
            num_classes = 43  # 독일 도로 표지판 43종
            total_samples = 50000
        elif self.dataset_name == "femnist":
            num_classes = 62  # LEAF 벤치마크 62종 (숫자+대소문자)
            total_samples = 60000
        elif self.dataset_name == "cifar100":
            num_classes = 100
            total_samples = 50000
        elif self.dataset_name == "cifar10":
            num_classes = 10
            total_samples = 50000
        else:
            num_classes = 10
            total_samples = 60000

        # 데이터 레이블 모사 생성
        dummy_labels = np.random.randint(0, num_classes, size=total_samples)

        print(f"[*] Non-IID 파티셔닝 수행: 데이터셋={self.dataset_name}, 노드수={self.num_clients}, Alpha={self.alpha}")
        partitions = self.generate_dirichlet_split(total_samples, num_classes, dummy_labels)

        # 통계 집계
        stats = {
            "dataset": self.dataset_name,
            "num_clients": self.num_clients,
            "alpha": self.alpha,
            "client_sample_counts": {f"client_{i}": len(idxs) for i, idxs in partitions.items()}
        }

        # 결과 저장
        out_dir = os.path.join(os.path.dirname(__file__), "..", "results")
        os.makedirs(out_dir, exist_ok=True)
        out_file = os.path.join(out_dir, f"noniid_{self.dataset_name}_alpha{self.alpha}.json")

        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)

        print(f"[OK] Non-IID 분포 데이터 생성 완료: {out_file}")
        return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AwareNet Non-IID Data Partitioner")
    parser.add_argument("--dataset", type=str, default="gtsrb", choices=["gtsrb", "femnist", "cifar10", "cifar100", "fashion_mnist"])
    parser.add_argument("--clients", type=int, default=10)
    parser.add_argument("--alpha", type=float, default=0.5, help="Dirichlet alpha (0.1: extreme Non-IID)")

    args = parser.parse_args()

    partitioner = NonIIDDataPartitioner(
        dataset_name=args.dataset,
        num_clients=args.clients,
        alpha=args.alpha
    )
    partitioner.partition_data()
