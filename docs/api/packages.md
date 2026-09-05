# Packages API Reference

The bundled-file layer: what a skill package ships alongside its `SKILL.md`.

harness reads a skill's instructions and stops there — it does not enumerate, read, or execute a
package's `references/`, `assets/` or `scripts/` files. This module indexes exactly those, keyed by
the same name harness gives the skill's capability, which is what lets `read_skill_resource` and
`run_skill_script` resolve a skill the model has loaded.

Discovery mirrors harness's rule: a skill is an **immediate** child directory of a library
containing a `SKILL.md`.

::: pydantic_ai_skills.packages.index_libraries
    options:
        show_source: true
        heading_level: 2

---

::: pydantic_ai_skills.SkillPackage
    options:
        show_source: true
        heading_level: 2

---

## Discovery rules

**Resources** — any file under the skill directory, at any depth, that reads as UTF-8 text, other
than `SKILL.md`. Binary files are skipped, as is anything matching an exclude glob. Named by its
posix path relative to the skill directory (`references/FORMS.md`).

**Scripts** — files in the skill root and its `scripts/` subdirectory that either carry a known
extension (`.py`, `.sh`, `.bash`, `.zsh`, `.fish`, `.ps1`, `.bat`, `.cmd`) or have the executable
bit set. Named the same way (`scripts/run.py`).

A file discovered as a script is never also offered as a resource.

Symlinks that resolve outside the skill directory are skipped with a `UserWarning` — following one
would let a skill hand the model, or execute, an arbitrary file on the host.

::: pydantic_ai_skills.packages.DEFAULT_RESOURCE_EXCLUDES
    options:
        show_source: false
        heading_level: 3
