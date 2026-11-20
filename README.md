# gitlab-grass-sync

SSAFY GitLab의 커밋 활동을 코드 없이(빈 커밋으로) GitHub 잔디에 복제한다.

- `sync_grass.py` — GitLab API로 내 커밋의 날짜만 읽어와 같은 날짜의 빈 커밋을 만든다
- `synced.json` — 이미 동기화한 커밋 SHA 목록 (중복 방지)
- `.github/workflows/sync.yml` — 매일 KST 00:17에 자동 실행 예약 (GitHub 사정에 따라 지연 가능)

## 설정

1. GitLab PAT 발급 (`read_api` 스코프) → 레포 Secrets에 `GITLAB_TOKEN`
2. GitLab 커밋에 쓴 이메일 → Secrets에 `GITLAB_EMAILS` (쉼표 구분)
3. Actions 탭에서 "Sync GitLab grass" 수동 실행하면 과거 커밋까지 백필됨

## 실행 결과 확인

- Actions 실행 화면의 요약에서 조회 프로젝트, 이번 생성 건수, 누적 동기화 건수를 확인한다. GitHub 업로드 여부는 `Push` 단계까지 성공했는지 확인한다.
- 새 커밋이 0개면 정상 종료한다. 매일 실행해도 새로 가져올 활동이 없으면 잔디는 추가되지 않는다.
- 커밋은 실행 날짜가 아니라 GitLab에서 작성한 날짜에 반영된다. 잔디 표시는 최대 24시간 걸릴 수 있다.
- 모든 브랜치에서 `GITLAB_EMAILS`와 작성자 이메일이 일치하는 커밋을 가져온다. 이슈, 댓글 등의 활동은 복사하지 않는다.
- 일부 프로젝트에 접근하지 못하면 경고와 프로젝트 ID, HTTP 상태를 로그 및 요약에 남긴다. 이 경우 실행이 성공해도 해당 저장소의 활동은 빠질 수 있다. 프로젝트가 0개이거나 전부 접근 불가이면 실패 처리한다.
- 같은 브랜치의 자동 실행과 수동 실행은 순서대로 실행하여 중복 생성과 push 충돌을 방지한다.

## 로컬 검증

`python -m unittest discover -s tests -v` — GitLab 연결 없이 임시 Git 저장소에서 날짜 보존, 중복 방지, 중단 후 복구 및 오류 처리를 확인한다.
