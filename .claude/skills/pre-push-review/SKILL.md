---
name: pre-push-review
description: >-
  Review the current branch against the repository's review rubric before pushing. Use before the
  first push of a branch and again before every later push to an open pull request, or whenever the
  user asks for a review of local changes.
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash(git diff:*)
  - Bash(git log:*)
  - Bash(git status:*)
  - Bash(git merge-base:*)
  - Bash(git rev-parse:*)
  - Bash(gh pr view:*)
  - Bash(gh pr diff:*)
---

# Pre-push review

Catch the problems while they are still cheap to fix — before a push, before CI spends twenty
minutes, before the AI reviewer posts them where everyone can see.

This is the local counterpart of the `AI Review` workflow. Same rubric, different moment.

## 1. Confirm the deterministic gates are green

A judgment review of code that does not lint or pass its tests is wasted effort. Run these first and
fix anything they report:

```bash
python -m pytest
pre-commit run --all-files
```

## 2. Read the rubric

Read [`.github/review-rubric.md`](../../../.github/review-rubric.md) in full. It is binding: the
severity scale, the repository invariants, the evidence bar, and the list of things not to flag all
live there, and it is the same file the CI reviewer reads. Do not substitute your own priors for it.

Then read the root [`AGENTS.md`](../../../AGENTS.md) for the conventions the diff has to match.

## 3. Gather the diff

```bash
gh pr view --json number,title,body,baseRefName,comments 2>/dev/null || echo "no PR yet"
git status --short
git diff main...HEAD --stat
git diff main...HEAD
git diff HEAD
```

Use the pull request's base branch when one exists, `main` otherwise. The last command covers staged
and unstaged work that has not reached `HEAD` — review that too; it is what the next commit will
contain.

If a pull request exists, read its existing review threads and do not repeat a point already made
there, or one a maintainer has already answered.

Read a large diff in chunks: implementation before tests, and read the **full file** around each
hunk rather than judging the hunk alone.

## 4. Report locally

Do not post comments, submit a review, or change the branch. Return findings as text, worst-first:

```
<severity> — <file>:<line>
<the problem, and the concrete fix>
```

Say plainly when there are no findings. That is the normal outcome for a small, careful change, and
inventing something to say is worse than saying nothing.
