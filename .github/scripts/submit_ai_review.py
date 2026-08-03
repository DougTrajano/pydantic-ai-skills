#!/usr/bin/env python3
r"""Turn the AI reviewer's findings file into a GitHub pull request review.

The reviewer agent itself gets no write access to GitHub: it reads the diff and
writes `findings.json`. This script is the only thing that posts, which means the
parts that must not be improvised — which lines are commentable, what the verdict
is, how many comments are allowed — are decided by code, not by a model.

Usage:
    submit_ai_review.py --findings findings.json --patch pr.diff \\
        --repo owner/name --pr 123 --commit <sha>

`findings.json` is a JSON object:

    {
      "summary": "optional cross-cutting note for the review body",
      "findings": [
        {"path": "pydantic_ai_skills/toolset.py", "line": 412,
         "severity": "high", "comment": "..."}
      ]
    }
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# Ordered worst-first; anything at or above REQUEST_CHANGES_AT blocks.
SEVERITIES = ('critical', 'high', 'medium', 'low', 'nitpick')
REQUEST_CHANGES_AT = ('critical', 'high')
MAX_COMMENTS = 30

HUNK_HEADER = re.compile(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@')
DIFF_HEADER = re.compile(r'^\+\+\+ b/(.+)$')

# Identifies reviews this workflow posted, so a rerun can tell its own reviews apart.
MARKER = '<!-- ai-review -->'


def parse_patch(patch: str) -> dict[str, set[int]]:
    """Map each file in a unified diff to the new-side line numbers it adds or changes.

    GitHub only accepts an inline comment on a line that appears in the diff, so
    this set is exactly what may be commented on.

    Args:
        patch: A unified diff, as produced by `git diff`.

    Returns:
        A mapping of file path to the set of commentable line numbers.
    """
    commentable: dict[str, set[int]] = {}
    path: str | None = None
    line_number = 0
    for line in patch.splitlines():
        header = DIFF_HEADER.match(line)
        if header:
            path = header.group(1)
            commentable.setdefault(path, set())
            continue
        hunk = HUNK_HEADER.match(line)
        if hunk:
            line_number = int(hunk.group(1))
            continue
        if path is None or line.startswith(('---', 'diff ', 'index ', 'new file', 'deleted file')):
            continue
        if line.startswith('+'):
            commentable[path].add(line_number)
            line_number += 1
        elif line.startswith((' ', '\t')) or line == '':
            # Context lines advance the new-side counter but are not commentable:
            # commenting on an unchanged line is how a review lands on the wrong code.
            line_number += 1
    return commentable


def normalize(finding: object) -> dict | None:
    """Return `finding` as a well-formed finding dict, or None when it is unusable."""
    if not isinstance(finding, dict):
        return None
    comment = str(finding.get('comment') or '').strip()
    path = str(finding.get('path') or '').strip()
    if not comment or not path:
        return None
    severity = str(finding.get('severity') or 'medium').strip().lower()
    if severity not in SEVERITIES:
        severity = 'medium'
    try:
        line = int(finding.get('line'))
    except (TypeError, ValueError):
        line = 0
    return {'path': path, 'line': line, 'severity': severity, 'comment': comment}


def by_severity(findings: list[dict]) -> list[dict]:
    """Sort findings worst-first, stable within a severity."""
    return sorted(findings, key=lambda f: SEVERITIES.index(f['severity']))


def verdict_for(findings: list[dict]) -> str:
    """Return the review event for `findings`, per the rubric's verdict mapping."""
    if any(f['severity'] in REQUEST_CHANGES_AT for f in findings):
        return 'REQUEST_CHANGES'
    return 'COMMENT' if findings else 'APPROVE'


def split_findings(
    findings: list[dict], commentable: dict[str, set[int]], max_comments: int = MAX_COMMENTS
) -> tuple[list[dict], list[dict]]:
    """Split findings into ones that can be posted inline and ones for the review body.

    A finding goes into the body when its line is not part of the diff (GitHub
    would reject the whole review) or when the inline budget is already spent.
    """
    inline: list[dict] = []
    body: list[dict] = []
    for finding in by_severity(findings):
        if finding['line'] in commentable.get(finding['path'], set()) and len(inline) < max_comments:
            inline.append(finding)
        else:
            body.append(finding)
    return inline, body


def render_body(commit: str, summary: str, verdict: str, body_findings: list[dict]) -> str:
    """Render the review body: the reviewed commit, the verdict, and any leftover findings."""
    lines = [MARKER, f'Reviewed at `{commit}`.', '']
    if verdict == 'APPROVE' and not body_findings:
        lines.append('No findings.')
    if summary.strip():
        lines.extend([summary.strip(), ''])
    if body_findings:
        lines.append('### Findings not attached to a changed line')
        lines.append('')
        for finding in body_findings:
            location = f'`{finding["path"]}`' + (f':{finding["line"]}' if finding['line'] else '')
            lines.append(f'- **{finding["severity"]}** — {location}: {finding["comment"]}')
        lines.append('')
    lines.append('_Posted by the AI reviewer. Findings are advisory; the required checks are the gate._')
    return '\n'.join(lines).strip()


def build_payload(
    commit: str, summary: str, findings: list[dict], commentable: dict[str, set[int]], max_comments: int = MAX_COMMENTS
) -> dict:
    """Build the request body for `POST /repos/{repo}/pulls/{pr}/reviews`."""
    inline, body_findings = split_findings(findings, commentable, max_comments)
    verdict = verdict_for(findings)
    return {
        'commit_id': commit,
        'event': verdict,
        'body': render_body(commit, summary, verdict, body_findings),
        'comments': [
            {
                'path': f['path'],
                'line': f['line'],
                'side': 'RIGHT',
                'body': f'**{f["severity"]}** — {f["comment"]}',
            }
            for f in inline
        ],
    }


def post(payload: dict, repo: str, pr: int) -> int:
    """Submit the review through `gh api`, degrading to a plain comment if the verdict is refused."""
    result = _gh_review(payload, repo, pr)
    if result.returncode == 0:
        return 0

    # GitHub refuses APPROVE/REQUEST_CHANGES when the reviewer authored the PR
    # (which is the normal case for an agent-opened PR reviewed by the same app).
    # The findings still matter, so re-post them as a comment review.
    if payload['event'] != 'COMMENT' and 'own pull request' in (result.stderr or ''):
        print('Verdict refused by GitHub (reviewing own pull request); posting as a comment review.')
        payload = {**payload, 'event': 'COMMENT'}
        result = _gh_review(payload, repo, pr)
        if result.returncode == 0:
            return 0

    print(result.stderr or result.stdout, file=sys.stderr)
    return 1


def _gh_review(payload: dict, repo: str, pr: int) -> subprocess.CompletedProcess[str]:
    """Run the `gh api` call that submits the review."""
    return subprocess.run(
        ['gh', 'api', '--method', 'POST', f'repos/{repo}/pulls/{pr}/reviews', '--input', '-'],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )


def load_findings(path: Path) -> tuple[str, list[dict]] | None:
    """Read the findings file, or return None when the reviewer did not produce one.

    The prompt requires the file to be written even when there is nothing to
    report, so a missing or unparseable one means the agent did not finish — it
    does not mean the code is clean. The caller posts nothing in that case:
    an approving review nobody performed is worse than no review.
    """
    if not path.is_file():
        print(f'::warning::{path} was not written; the reviewer did not finish. Posting nothing.')
        return None
    try:
        data = json.loads(path.read_text() or '')
    except (json.JSONDecodeError, ValueError) as error:
        print(f'::warning::{path} is not valid JSON ({error}); the reviewer did not finish. Posting nothing.')
        return None
    if not isinstance(data, dict):
        print(f'::warning::{path} is not a JSON object; the reviewer did not finish. Posting nothing.')
        return None
    raw = data.get('findings') or []
    findings = [f for f in (normalize(item) for item in raw) if f is not None]
    return str(data.get('summary') or ''), findings


def main(argv: list[str] | None = None) -> int:
    """Read the findings, build the review payload and post it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--findings', required=True, type=Path)
    parser.add_argument('--patch', required=True, type=Path)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--pr', required=True, type=int)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--max-comments', type=int, default=MAX_COMMENTS)
    parser.add_argument('--dry-run', action='store_true', help='print the payload instead of posting it')
    args = parser.parse_args(argv)

    loaded = load_findings(args.findings)
    if loaded is None:
        return 0
    summary, findings = loaded
    commentable = parse_patch(args.patch.read_text() if args.patch.is_file() else '')
    payload = build_payload(args.commit, summary, findings, commentable, args.max_comments)

    counts = ', '.join(f'{s}={sum(1 for f in findings if f["severity"] == s)}' for s in SEVERITIES)
    print(f'{len(findings)} finding(s) ({counts}); verdict {payload["event"]}, {len(payload["comments"])} inline.')

    if args.dry_run:
        print(json.dumps(payload, indent=2))
        return 0
    return post(payload, args.repo, args.pr)


if __name__ == '__main__':
    raise SystemExit(main())
