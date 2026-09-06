# Registries API Reference

A registry materializes skill packages into a local directory that
[`SkillsCapability`](capability.md) hands to harness. See [Skill Registries](../registries.md) for
the guide.

::: pydantic_ai_skills.SkillRegistry
    options:
        show_source: true
        heading_level: 2
        members:
            - sync
            - skill_infos
            - skill_names
            - filtered
            - prefixed
            - renamed
            - __or__

---

::: pydantic_ai_skills._parsing.SkillInfo
    options:
        show_source: true
        heading_level: 2

---

::: pydantic_ai_skills.registries.git.GitSkillsRegistry
    options:
        show_source: true
        heading_level: 2
        members:
            - sync
            - revision

---

::: pydantic_ai_skills.registries.git.GitCloneOptions
    options:
        show_source: true
        heading_level: 2

---

::: pydantic_ai_skills.registries.s3.S3SkillsRegistry
    options:
        show_source: true
        heading_level: 2
        members:
            - sync
            - revision

---

::: pydantic_ai_skills.registries.local.LocalSkillsRegistry
    options:
        show_source: true
        heading_level: 2
        members:
            - sync

---

## Composition Wrappers

Each wrapper syncs the registry it wraps, then stages a new library holding the packages it wants
under the names it wants. The wrapped registry is never modified.

::: pydantic_ai_skills.registries.wrapper.WrapperRegistry
    options:
        show_source: true
        heading_level: 3

---

::: pydantic_ai_skills.registries.filtered.FilteredRegistry
    options:
        show_source: true
        heading_level: 3

---

::: pydantic_ai_skills.registries.prefixed.PrefixedRegistry
    options:
        show_source: true
        heading_level: 3

---

::: pydantic_ai_skills.registries.renamed.RenamedRegistry
    options:
        show_source: true
        heading_level: 3

---

::: pydantic_ai_skills.registries.combined.CombinedRegistry
    options:
        show_source: true
        heading_level: 3
