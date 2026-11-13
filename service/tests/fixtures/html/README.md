# HTML 스냅샷

⚠️ 현재 파일들은 **합성(synthetic) 스냅샷**입니다. `selectors.yaml` 초안의 구조를 본떠 손으로 만든 것이며
실제 쿠팡 화면이 아닙니다. Phase 0 spike(`docs/phase0-spike-guide.md`)에서 실제 상품 페이지를 열어
`var/scrape_html/`에 저장된 HTML로 교체하고, 테스트 기대값을 실제 값에 맞게 고쳐야 합니다.

| 파일 | 용도 |
|---|---|
| search_synthetic.html | 검색 결과 파서 (광고 1개 포함) |
| product_synthetic.html | 상품 메타·별점 분포(개수) |
| product_ratio_synthetic.html | 별점 분포가 비율(%)로만 보이는 경우 |
| reviews_synthetic_p1.html | 리뷰 목록 파서 (5점 필터, 사진·제목·도움돼요) |
| reviews_broken_synthetic.html | 셀렉터 깨짐 → ParserBrokenError |
| reviews_empty_synthetic.html | 리뷰 없음 표시 |
| blocked_access_denied.html | Akamai 계열 Access Denied |
| blocked_captcha.html | CAPTCHA·챌린지 화면 |
| blocked_permission_ko.html | **실제 쿠팡 응답**(2026-11-13 오너 PC spike): 자동화 브라우저에 반환된 '사용권한이 없습니다' 페이지. Ref(접속 IP 포함)는 지움 |
