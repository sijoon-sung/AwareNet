# 공개 저장소와 홈페이지

- 공개 저장소: https://github.com/sijoon-sung/AwareNet
- 홈페이지: https://sijoon-sung.github.io/AwareNet/
- 원자료: https://sijoon-sung.github.io/AwareNet/site/evidence.html

GitHub의 가시성은 저장소 단위다. 원래 개발 저장소는 비공개로 두고 최종 awarenet 파일만 새 공개 저장소에 복사한다. 다른 브랜치나 이전 Git 이력은 공개 스냅샷에 포함하지 않는다.

Pages는 공개 저장소의 awarenet 브랜치 루트에서 배포한다. 루트 index.html은 site/로 연결하며 .nojekyll로 원자료 경로의 밑줄 디렉터리도 그대로 제공한다. 사용자 정의 Actions 워크플로는 필요하지 않다.

공개 자료는 scripts/analysis/build_public_evidence.py로 만들고 site/assets/evidence/verify_evidence.py로 확인한다. 공개 스냅샷 생성기는 scripts/observability/prepare_public_release.py다. 생성기는 배포 권한이나 GitHub 가시성을 변경하지 않는다. PUBLIC_RELEASE.json의 목록은 무시 규칙에 포함된 원측정도 초기 커밋에 넣기 위한 명시적 파일 목록이다.

계측소의 실시간 UI는 로컬 서비스다. 홈페이지에는 저장된 실험 결과, PCAP, 시계열과 대시보드 정의가 게시된다.
