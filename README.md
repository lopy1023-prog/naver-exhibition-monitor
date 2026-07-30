# Naver Exhibition Monitor

네이버 쇼핑파트너 공식 블로그의 신규 게시물을 매시간 수집하고 Netlify Blobs에 저장하는 감시기입니다.

## API

- `/api/collect`: 지금 즉시 수집 실행
- `/api/status`: 마지막 수집 상태와 최근 게시물 확인

## 자동 실행

`netlify/functions/collect-rss.mjs`의 `schedule: "@hourly"` 설정으로 매시간 실행됩니다.

## 자료 수집 순서

1. 네이버 공식 블로그 RSS
2. RSS 실패 시 네이버 모바일 블로그 글 목록 및 개별 글

두 출처 모두 실패하면 `status: "error"`로 저장하며, 실패를 `기획전 없음`으로 처리하지 않습니다.
