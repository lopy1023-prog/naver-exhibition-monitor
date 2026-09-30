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

모든 공고의 상세페이지에서 수원 관련 여부를 확인합니다. 첨부파일은 이름과 공식 링크만 저장하고 다운로드하거나 내용을 읽지 않습니다. `lh-report.json`의 `alerts`에는 이번 실행에 새로 올라오거나 변경된 수원 직접 공고, 정확한 광역 후보, 별도 추적 공고를 담고, `alertHistory`에는 이후에도 확인할 수 있도록 누적합니다. 최초 45일 역추적 자료는 알림에 넣지 않습니다. 각 이벤트의 `suwonMatch`는 `direct`/`broadCandidate`/`tracked`이며, 직접 확인되지 않은 이벤트에는 `requiresSuwonReview: true`가 붙습니다. GPT 앱 예약작업은 `alertHistory`에서 아직 알리지 않은 `alertId`만 골라 공식 상세 링크와 수원 확인 필요 여부를 알려주도록 연결할 수 있습니다.

`data/lh/lh-feed.json`은 현재 공식 수집 결과, `lh-report.json`은 이벤트와 후보, `lh-state.json`은 마지막 정상 스냅샷, `lh-tracked-state.json`은 별도 추적 상태입니다. 실패 시 feed/report에 `sourceStatus: error`와 원인을 기록하고 프로세스를 실패 종료합니다. Actions는 수집을 최대 48분에 중단하고 오류 feed/report만 커밋합니다. 정상 스냅샷 두 파일은 보존하며, workflow도 실패 상태를 유지합니다. 실패 산출물은 Actions artifact에서도 확인할 수 있습니다.

`tracked.json`의 경기남부 일반 매입임대 공고는 별도로 2026년 전체를 검색합니다. 자동 추적 종료는 하지 않습니다.

## 운영상 한계

- LH의 POST 폼·HTML 구조가 변경되면 구조 검증이 실패합니다. 해당 실행은 `신규 없음`으로 간주하지 않습니다.
- 현재 범위의 사전청약은 0건이며 전용 목록/상세 파서는 과거 공식 공고 22건으로 추가 검증했습니다.
- 첨부파일에만 수원 정보가 있고 목록·상세페이지에는 없는 공고는 자동 알림에서 누락될 수 있습니다. 첨부파일 본문은 요청에 따라 읽지 않습니다.
- 목록의 45일 최초 범위 밖에 있던 과거 공고는 추적 등록 대상 외에는 포함되지 않습니다.
- GPT 앱 예약작업 생성은 별도로 필요합니다. 이 저장소는 알림 데이터만 갱신합니다.
