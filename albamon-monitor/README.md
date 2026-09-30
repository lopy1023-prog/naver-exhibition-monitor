# 알바몬 재택·디지털 업무 후보 모니터

공개 알바몬 재택 목록과 알바몬 자체 검색결과에서 업체명, 공고 제목, 공고번호, 직접 링크를 수집합니다. 공고 적합성은 평가하지 않습니다. 상세 공고와 첨부파일은 자동으로 열지 않습니다.

## 실행

Node.js 20 이상에서 별도 패키지 설치 없이 실행합니다.

```bash
node --test albamon-monitor/test/*.test.mjs
node albamon-monitor/collect.mjs
node albamon-monitor/collect.mjs --validate
```

공식 화면에서 확인한 `/jobs/telecommuting`의 마지막 페이지까지 확인합니다. 내부 검색은 `/total-search`를 최신등록순으로 사용하며, 광범위한 검색어는 최근 3페이지까지만 봅니다. 이 제한은 결과의 `sources.keyword_search.truncated_queries`에 기록합니다. 검색어는 `config.mjs`에서 수정합니다. 요청 사이에는 700ms를 쉽니다. 403, 429 또는 CAPTCHA 화면이 나오면 추가 요청을 멈추고 오류를 기록합니다.

## 결과

- `data/albamon-feed.json`: 현재 후보, 수집 상태, 최초/최근 발견 시각, 신규 여부, 발견 경로. 공고는 공식 직접 링크로 연결됩니다.
- `data/albamon-seen.json`: 중복 신규 알림을 막기 위한 공고번호 이력. 최근 120일, 최대 20,000건을 보관합니다.
- `data/collector-status.json`: 마지막 실행 상태와 오류. 모든 출처가 실패하면 기존 정상 피드를 그대로 둡니다.

`.github/workflows/albamon-monitor.yml`은 UTC 기준 4시간마다 17분에 실행하며, 수동 실행도 지원합니다. 기존 네이버·LH workflow와 독립적으로 위 세 JSON만 자동 커밋합니다. GitHub Actions에서 오류가 나면 `collector-status.json`과 해당 실행 로그를 확인합니다.
