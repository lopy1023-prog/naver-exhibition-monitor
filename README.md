# Naver Exhibition Monitor

네이버 쇼핑파트너 공식 블로그를 GitHub Actions에서 직접 수집하여 `data/naver-feed.json`에 저장합니다. 실행에 Netlify나 외부 저장소, npm 패키지 설치가 필요하지 않습니다.

## 구조와 공개 피드

네이버 공식 RSS/모바일 블로그 → GitHub Actions → `data/naver-feed.json` → ChatGPT 예약 작업 → 사용자가 연결한 Gmail.

- 피드: https://raw.githubusercontent.com/lopy1023-prog/naver-exhibition-monitor/main/data/naver-feed.json
- 실행 기록: https://github.com/lopy1023-prog/naver-exhibition-monitor/actions/workflows/naver-monitor.yml
- 수동 수집: 위 Actions 화면의 **Run workflow**에서 `main` 선택.
- 로컬 확인: Node.js 20 이상에서 `node scripts/collect-naver-feed.mjs`. `OUTPUT_PATH`로 별도 결과 경로를 지정할 수 있습니다.
- 검증: `node --test`.

## 자동 실행

`.github/workflows/naver-monitor.yml`은 매시간 12분(UTC)에 실행하도록 설정되어 있습니다. GitHub 예약은 지연되거나 건너뛸 수 있으므로 매시간 정시 실행을 보장하지 않습니다. 정상 수집 때마다 성공 시각을 갱신하며, 게시물 내용이 같아도 수집 성공 기록을 저장합니다.

회사 ChatGPT용 운영 기준은 원본 정상 수집 후 12시간 이내입니다. 기존 5시간 기준에서 변경한 것으로, 실제 관측된 최대 약 7시간의 GitHub 예약 간격을 고려했습니다. 이는 시간당 수집 보장이 아니며, 지난 신청 마감 공고는 별도로 제외해야 합니다.

## 자료 수집 순서

1. 네이버 공식 블로그 RSS
2. RSS 실패 시 네이버 모바일 블로그 글 목록 및 개별 글

두 출처 모두 실패하거나 수집 결과 검증에 실패하면 `sourceStatus: "error"`와 오류를 저장하고 작업을 실패 처리합니다. 기존 공고와 마지막 정상 수집 시각은 보존합니다. 실패를 `신규 기획전 없음`으로 처리하지 않습니다. 모바일 폴백의 개별 공고 요청이 일부 실패한 경우도 불완전한 수집으로 처리합니다.

## 피드 계약과 보존

`schemaVersion=1`, `posts`, `position`, `postCount`, `latestLogNo`, `sourceStatus`, `syncedAt`, `sourceLastCheckedAt`, `sourceLastSuccessAt`을 유지합니다. `collectionMode=github-actions-direct`는 직접 수집임을 표시합니다. 최대 최근 50건을 유지하며, 매 실행 결과 파일은 덮어쓰지만 Git 이력에는 이전 버전이 남습니다.

최신성 기준은 `sourceLastSuccessAt`입니다. 실패 실행에서도 바뀌는 `syncedAt`이나 `sourceLastCheckedAt`을 성공 시각으로 해석하지 않습니다. `sourceErrors`는 성공한 폴백 이전의 출처 오류도 포함할 수 있으므로 최종 `sourceStatus`와 함께 판단합니다.

## 메일과 회사 계정 이전

이 저장소는 공고 수집만 담당합니다. Gmail 발송은 회사 ChatGPT 계정에서 사용자가 연결한 같은 Gmail 계정으로 수행합니다. 기존 SENT 이력으로 중복을 확인하고, 실제 발송 응답과 SENT를 증거로 확인해야 합니다. GitHub 수집 성공만으로 메일 발송 성공을 주장하지 않습니다.

수신 주소가 포함된 회사 계정용 최종 프롬프트는 공개 저장소에 넣지 않고 별도로 전달합니다. 신규 공고가 없으면 조용히 종료하고, 오류가 발생해도 예약 작업을 임의로 중지하지 않습니다.

## 이전 호스팅 종료

기존 수집 함수와 저장소 연동, 피드 동기화 workflow는 제거했습니다. `netlify.toml`과 `public/index.html`은 기존 사이트에 정적 종료 안내를 배포해 예약 함수를 해제하기 위한 잔여 호환 설정입니다. GitHub 수집과 메일 운영에는 사용하지 않습니다. 해당 프로젝트의 종료 배포를 확인한 후 사이트를 삭제할 수 있습니다. 다른 사이트나 Netlify 계정 전체를 삭제할 필요는 없습니다.

LH와 알바몬의 코드, workflow, 데이터는 별개이며 이 변경으로 수정하지 않습니다.
