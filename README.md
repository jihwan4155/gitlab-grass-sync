# gitlab-grass-sync

SSAFY GitLab의 커밋 활동을 코드 없이(빈 커밋으로) GitHub 잔디에 복제한다.

- `sync_grass.py` — GitLab API로 내 커밋의 날짜만 읽어와 같은 날짜의 빈 커밋을 만든다
- `synced.json` — 이미 동기화한 커밋 SHA 목록 (중복 방지)
- `.github/workflows/sync.yml` — 매일 KST 자정에 자동 실행

## 설정

1. GitLab PAT 발급 (`read_api` 스코프) → 레포 Secrets에 `GITLAB_TOKEN`
2. GitLab 커밋에 쓴 이메일 → Secrets에 `GITLAB_EMAILS` (쉼표 구분)
3. Actions 탭에서 "Sync GitLab grass" 수동 실행하면 과거 커밋까지 백필됨
