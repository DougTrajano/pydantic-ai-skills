# Security Policy

## Supported versions

Only the latest released version of `pydantic-ai-skills` receives security fixes.
Fixes are released as a new patch version; there are no long-term support branches.

## Reporting a vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Report them privately through
[GitHub Security Advisories](https://github.com/dougtrajano/pydantic-ai-skills/security/advisories/new),
which lets us discuss and fix the issue before it is disclosed.

Please include as much of the following as you can:

- The type of issue (for example: path traversal, arbitrary script execution, credential exposure)
- The affected version, and the source file and function if you have identified them
- Step-by-step instructions to reproduce it, ideally with a minimal proof of concept
- The impact you believe it has

You can expect an initial response within 7 days. If the report is accepted, we will keep
you updated on the fix and credit you in the advisory unless you prefer otherwise.

## Scope

This package discovers skills from the filesystem and remote registries, exposes bundled
resources to a model, and can execute skill scripts as subprocesses. The trust boundaries
that follow from that — and what this package does and does not defend against — are
documented in the [security model](https://dougtrajano.github.io/pydantic-ai-skills/security/).

Read it before reporting: **skills are executable code, and loading an untrusted skill is
equivalent to running untrusted code.** That is a documented property of the design, not a
vulnerability. Reports that are in scope include path-traversal or symlink escapes from the
skills directory, bypasses of the sandbox script executors, and credential exposure through
registry handling.
