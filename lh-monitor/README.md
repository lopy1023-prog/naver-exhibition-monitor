# LH 수원 공고 모니터

기존 네이버 모니터와 별도인 GitHub Actions 수집기입니다. LH청약플러스의 공식 공고 목록을 직접 GET/POST로 조회합니다. 검색엔진은 수집 데이터로 사용하지 않습니다.

## 실행

```bash
python -m pip install -r lh-monitor/requirements.txt
python -m unittest discover -s lh-monitor/tests -v
python lh-monitor/monitor.py
python lh-monitor/monitor.py --validate
```

`.github/workflows/lh-monitor.yml`은 매시 37분(KST 기준 아님)에 별도로 실행됩니다. 공식 임대·분양·토지·상가 목록의 모든 검색 결과 페이지와 현재 사전청약 목록을 검사합니다. 첫 정상 실행은 실행일 기준 과거 45일을 역추적하고, 이후 정상 스냅샷의 시작일을 유지합니다. 검색 상태는 전체이며, 목록의 총 건수·페이지 수·파싱 건수·중복 panId를 검증합니다.

모든 공고의 상세를 확인하고, 수원·광역 후보의 PDF/HWP/HWPX/XLS/XLSX/ZIP 첨부를 분석합니다. 읽기 실패는 `needsReview`와 `reviewReason`에 기록하며 공고를 제외하지 않습니다. HWP는 `hwp5txt`를 사용합니다. 스캔 PDF와 해석 불가 HWP는 검토 대상으로 남깁니다. 첨부파일 접근 실패가 광범위하면 실행 전체가 실패합니다.

`data/lh/lh-feed.json`은 현재 공식 수집 결과, `lh-report.json`은 이벤트와 후보, `lh-state.json`은 마지막 정상 스냅샷, `lh-tracked-state.json`은 별도 추적 상태입니다. 실패 시 feed/report에 `sourceStatus: error`와 원인을 기록하고 프로세스를 실패 종료합니다. 정상 스냅샷 두 파일은 갱신하지 않으며, GitHub Actions도 실패하므로 오류 결과는 자동 커밋되지 않습니다. 실패 산출물은 Actions artifact에서 확인할 수 있습니다.

`tracked.json`의 경기남부 일반 매입임대 공고는 별도로 2026년 전체를 검색합니다. 자동 추적 종료는 하지 않습니다.

## 운영상 한계

- LH의 POST 폼·HTML 구조가 변경되면 구조 검증이 실패합니다. 해당 실행은 `신규 없음`으로 간주하지 않습니다.
- 현재 별도 사전청약 목록은 0건입니다. 신규 공고가 생기면 전용 파서가 검증되기 전까지 안전하게 실패합니다.
- 목록의 45일 최초 범위 밖에 있던 과거 공고는 추적 등록 대상 외에는 포함되지 않습니다.
- HWP 바이너리·스캔 PDF·암호화된 문서의 텍스트 추출 실패는 수동 확인이 필요합니다.
