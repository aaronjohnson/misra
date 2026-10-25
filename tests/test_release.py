"""rules/release: a release tag or the branch tip, on throwaway git repos."""

import subprocess

from misra.release import plan


def repo(tmp_path, changelog, tags=(), tag_head=()):
    def git(*a):
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.email=t@t", "-c", "user.name=t",
                        "-c", "tag.gpgSign=false", "-c", "commit.gpgSign=false", *a], check=True, capture_output=True)
    git("init", "-q")
    (tmp_path / "CHANGELOG.md").write_text(changelog)
    git("add", ".")
    git("commit", "-qm", "one")
    for t in tags:
        git("tag", t)
    git("commit", "-q", "--allow-empty", "-m", "two")
    for t in tag_head:
        git("tag", t)
    return tmp_path


def test_new_version_gets_a_tag(tmp_path):
    p = plan(repo(tmp_path, "# Log\n\n## 0.6.0 · 25 October 2026 · night\n", tags=["v0.5.0"]))
    assert (p["mode"], p["plan"], p["tag"]) == ("tag", "new_tag", "v0.6.0")


def test_already_tagged_here(tmp_path):
    p = plan(repo(tmp_path, "## 0.6.0 · x\n", tag_head=["v0.6.0"]))
    assert (p["mode"], p["plan"]) == ("tag", "at_tag")


def test_commits_since_the_tag_stay_on_the_tip(tmp_path):
    p = plan(repo(tmp_path, "## 0.6.0 · x\n", tags=["v0.6.0"]))
    assert (p["mode"], p["plan"]) == ("tip", "stale")


def test_no_versions_no_tags(tmp_path):
    p = plan(repo(tmp_path, "## Folio VI · 13 October 2026 · the lens reground\n"))
    assert (p["mode"], p["plan"], p["tag"]) == ("tip", "tip", None)


def test_notes_cover_everything_since_the_previous_tag(tmp_path):
    from misra.release import notes
    log = "# Log\n\n## 0.7.0 · late\n\nseven\n\n## 0.6.0 · night\n\nsix\n\n## 0.2.0 · first\n\ntwo\n"
    r = repo(tmp_path, log, tags=["v0.2.0"], tag_head=["v0.7.0"])
    title, body = notes(r, "v0.7.0")
    assert title == "0.7.0 · late"
    assert "seven" in body and "six" in body and "two" not in body
