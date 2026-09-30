export const REMOTE_URL = 'https://www.albamon.com/jobs/telecommuting';
export const SEARCH_URL = 'https://www.albamon.com/total-search';

// Search the site's own results. Broad terms are limited to recent pages; the
// dedicated remote list is always traversed to its final page.
export const KEYWORDS = [
  '상품등록', '스마트스토어', '쇼핑몰 상품등록', '해외구매대행', '구매대행',
  '쇼핑몰 운영', '온라인몰 운영', 'MD', 'AMD', '상품 소싱',
  '재택', '프리랜서', 'AI', 'GPT', 'ChatGPT', 'AI Trainer',
  'AI 검수', 'AI 평가', 'AI 데이터', '데이터 검수', '데이터 입력',
  '데이터 가공', '데이터 라벨링', 'OCR', '문서작성', '자료조사',
  '사무보조', 'Excel', '원고작성', '콘텐츠', '상세페이지', '이미지 편집',
];

export const MAX_KEYWORD_PAGES = 3;
export const REQUEST_PAUSE_MS = 700;
export const SEEN_RETENTION_DAYS = 120;
export const MAX_SEEN_JOBS = 20000;
