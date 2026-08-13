#!/usr/bin/env python3
"""GitLab 커밋 활동을 빈 커밋으로 복제해서 GitHub 잔디를 심는 스크립트.

코드는 전혀 가져오지 않고, 커밋 메타데이터(SHA, author date, author email)만 읽는다.

필요한 환경변수:
  GITLAB_TOKEN   GitLab Personal Access Token (read_api 스코프)
  GITLAB_EMAILS  GitLab 커밋에 쓴 author email (쉼표로 여러 개 가능)
  GITLAB_URL    (선택) 기본값 https://lab.ssafy.com

이 스크립트는 GitHub 더미 레포 클론 안에서 실행해야 한다.
동기화된 커밋 SHA 목록은 synced.json 에 기록되어 중복 생성을 막는다.
"""

import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request

GITLAB_URL = os.environ.get("GITLAB_URL", "https://lab.ssafy.com").rstrip("/")
TOKEN = os.environ["GITLAB_TOKEN"]
EMAILS = {e.strip().lower() for e in os.environ["GITLAB_EMAILS"].split(",") if e.strip()}
STATE_FILE = "synced.json"


def api_get(path, **params):
    """GitLab API 호출 (한 페이지)."""
    qs = urllib.parse.urlencode(params)
    url = f"{GITLAB_URL}/api/v4/{path}?{qs}"
    req = urllib.request.Request(url, headers={"PRIVATE-TOKEN": TOKEN})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def api_get_all(path, **params):
    """페이지네이션을 따라가며 전부 수집."""
    results = []
    page = 1
    while True:
        batch = api_get(path, per_page=100, page=page, **params)
        results.extend(batch)
        if len(batch) < 100:
            return results
        page += 1


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return set(json.load(f)["synced_shas"])
    return set()


def save_state(shas):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"synced_shas": sorted(shas)}, f, indent=1)


def main():
    synced = load_state()

    projects = api_get_all("projects", membership="true", simple="true")
    print(f"프로젝트 {len(projects)}개 조회됨")

    new_commits = []  # (sha, authored_date)
    for p in projects:
        try:
            commits = api_get_all(f"projects/{p['id']}/repository/commits")
        except Exception as e:
            print(f"  [skip] {p['path_with_namespace']}: {e}")
            continue
        mine = [
            c for c in commits
            if c["author_email"].lower() in EMAILS and c["id"] not in synced
        ]
        if mine:
            print(f"  {p['path_with_namespace']}: 새 커밋 {len(mine)}개")
        new_commits.extend((c["id"], c["authored_date"]) for c in mine)

    # 같은 커밋이 포크 등 여러 프로젝트에 보일 수 있으므로 SHA로 중복 제거
    new_commits = sorted(set(new_commits), key=lambda x: x[1])

    if not new_commits:
        print("새로 동기화할 커밋 없음")
        return

    print(f"총 {len(new_commits)}개 빈 커밋 생성 중...")
    synced.update(sha for sha, _ in new_commits)
    save_state(synced)

    for i, (sha, date) in enumerate(new_commits):
        env = dict(os.environ, GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
        cmd = ["git", "commit", "-q", "--allow-empty", "-m", f"grass: {sha[:8]}"]
        if i == 0:
            # 첫 커밋에 갱신된 상태 파일을 함께 담는다
            subprocess.run(["git", "add", STATE_FILE], check=True)
        subprocess.run(cmd, check=True, env=env)

    print("완료. git push 하면 잔디에 반영된다.")


if __name__ == "__main__":
    main()
