#!/usr/bin/env python3
"""GitLab 커밋 활동을 코드 없는 커밋으로 복제해서 GitHub 잔디를 심는 스크립트.

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
import urllib.error
import urllib.parse
import urllib.request

GITLAB_URL = os.environ.get("GITLAB_URL", "https://lab.ssafy.com").rstrip("/")
STATE_FILE = "synced.json"


def api_get(path, **params):
    """GitLab API 호출 (한 페이지)."""
    qs = urllib.parse.urlencode(params)
    url = f"{GITLAB_URL}/api/v4/{path}?{qs}"
    req = urllib.request.Request(url, headers={"PRIVATE-TOKEN": os.environ["GITLAB_TOKEN"].strip()})
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
    # 작업 중 멈추더라도 실제로 생성된 커밋까지만 동기화된 것으로 본다.
    tracked = subprocess.check_output(["git", "ls-tree", "HEAD", "--", STATE_FILE])
    if not tracked:
        return set()
    state = subprocess.check_output(["git", "show", f"HEAD:{STATE_FILE}"])
    return set(json.loads(state)["synced_shas"])


def save_state(shas):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"synced_shas": sorted(shas)}, f, indent=1)
        f.write("\n")


def main():
    if not os.environ.get("GITLAB_TOKEN", "").strip():
        sys.exit("GITLAB_TOKEN을 GitHub Actions Secrets에 설정하세요.")
    emails = {
        email.strip().lower()
        for email in os.environ.get("GITLAB_EMAILS", "").split(",")
        if email.strip()
    }
    if not emails:
        sys.exit("GITLAB_EMAILS에 GitLab 커밋 작성자 이메일을 설정하세요.")

    synced = load_state()
    projects = api_get_all("projects", membership="true", simple="true")
    print(f"GitLab 프로젝트 {len(projects)}개 조회됨", flush=True)
    if not projects:
        print("::warning::조회된 프로젝트가 없습니다. GitLab 토큰의 계정과 프로젝트 접근 권한을 확인하세요.")

    matched = set()
    new_by_sha = {}
    inaccessible = 0
    for project in projects:
        try:
            commits = api_get_all(
                f"projects/{project['id']}/repository/commits", all="true"
            )
        except urllib.error.HTTPError as error:
            if error.code not in (403, 404):
                raise
            inaccessible += 1
            continue
        for commit in commits:
            if (commit.get("author_email") or "").strip().lower() in emails:
                sha = commit["id"]
                matched.add(sha)
                if sha not in synced:
                    new_by_sha[sha] = commit["authored_date"]

    if inaccessible:
        print(
            f"::warning::{inaccessible}개 프로젝트의 커밋을 읽을 수 없습니다 (HTTP 403/404). "
            "누락된 커밋이 있다면 해당 GitLab 저장소 접근 권한을 확인하세요."
        )
        if inaccessible == len(projects):
            sys.exit("모든 프로젝트의 커밋 조회가 실패했습니다.")

    new_commits = sorted(new_by_sha.items(), key=lambda item: (item[1], item[0]))
    print(f"조회 가능한 프로젝트에서 작성자 일치 {len(matched)}개, 새 커밋 {len(new_commits)}개")
    if projects and not matched:
        print("::warning::작성자가 일치하는 커밋이 없습니다. GITLAB_EMAILS를 확인하세요.")
    if not new_commits:
        return

    print(f"총 {len(new_commits)}개 동기화 커밋 생성 중...")

    for sha, date in new_commits:
        # 각 커밋에 해당 SHA를 기록해야 중간에 실패해도 이어서 실행할 수 있다.
        synced.add(sha)
        save_state(synced)
        subprocess.run(["git", "add", STATE_FILE], check=True)
        env = dict(os.environ, GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
        subprocess.run(
            ["git", "commit", "-q", "-m", f"grass: {sha[:8]}", "--", STATE_FILE],
            check=True,
            env=env,
        )

    print("완료. git push 하면 잔디에 반영된다.")


if __name__ == "__main__":
    main()
