# Skill Registries

Skill registries let you **discover, install, and manage skills from remote sources** — such as Git repositories — without manually downloading or organizing skill directories. Registries integrate seamlessly with `SkillsToolset`, so skills from a remote repo appear alongside local and programmatic skills.

## Installation

Git-backed registries require [GitPython](https://gitpython.readthedocs.io/):

```bash
pip install pydantic-ai-skills[git]
```

S3-backed registries require [boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html):

```bash
pip install pydantic-ai-skills[s3]
```

## Quick Start

### Load Skills from a Git Repository

```python
from pydantic_ai import Agent
from pydantic_ai_skills import SkillsCapability
from pydantic_ai_skills.registries import GitSkillsRegistry, GitCloneOptions

# Clone Anthropic's public skills repo (shallow, single-branch)
registry = GitSkillsRegistry(
    repo_url='https://github.com/anthropics/skills',
    path='skills',
    target_dir='./anthropics-skills',
    clone_options=GitCloneOptions(depth=1, single_branch=True),
)

agent = Agent(
    model='openai:gpt-5.2',
    instructions='You are a helpful assistant with access to a variety of skills.',
    capabilities=[SkillsCapability(registries=[registry])],
)
```

### Direct SkillsToolset Integration

```python
from pydantic_ai import Agent
from pydantic_ai_skills import SkillsToolset

skills_toolset = SkillsToolset(registries=[registry])

agent = Agent(
    model='openai:gpt-5.2',
    instructions='You are a helpful assistant with access to a variety of skills.',
    toolsets=[skills_toolset],
)
```

**View the complete example:** [git_registry_usage.py](https://github.com/DougTrajano/pydantic-ai-skills/blob/main/examples/git_registry_usage.py)

## GitSkillsRegistry

`GitSkillsRegistry` is the primary concrete registry. It clones a Git repository, discovers `SKILL.md` files, and exposes the skills to your agent.

### Constructor Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `repo_url` | `str` | — | Full URL of the Git repository (HTTPS or SSH). |
| `target_dir` | `str \| Path \| None` | `None` | Local clone directory. Defaults to a temporary directory. |
| `path` | `str` | `""` | Sub-path inside the repo containing skill directories. |
| `token` | `str \| None` | `None` | Personal access token. Falls back to `GITHUB_TOKEN` env var. |
| `ssh_key_file` | `str \| Path \| None` | `None` | Path to SSH private key for SSH authentication. |
| `clone_options` | `GitCloneOptions \| None` | `None` | Fine-grained Git clone configuration. |
| `validate` | `bool` | `True` | Validate `SKILL.md` frontmatter after cloning. |
| `auto_install` | `bool` | `True` | Clone/pull automatically on first access. |

### GitCloneOptions

Fine-tune the Git clone operation:

```python
from pydantic_ai_skills.registries import GitCloneOptions

options = GitCloneOptions(
    depth=1,                          # Shallow clone (1 commit)
    branch='main',                    # Specific branch
    single_branch=True,               # Only fetch one branch
    sparse_paths=['skills/pdf'],      # Sparse checkout (specific paths only)
    multi_options=['--filter=blob:none'],  # Blobless clone
    env={'GIT_SSH_COMMAND': '...'},   # Custom env vars for git
    git_options={},                   # Extra kwargs for GitPython
)
```

### Authentication

=== "HTTPS with Token"

    ```python
    # Explicit token
    registry = GitSkillsRegistry(
        repo_url='https://github.com/my-org/private-skills.git',
        token='ghp_...',
    )

    # Or via environment variable
    # export GITHUB_TOKEN=ghp_...
    registry = GitSkillsRegistry(
        repo_url='https://github.com/my-org/private-skills.git',
    )
    ```

=== "SSH Key"

    ```python
    registry = GitSkillsRegistry(
        repo_url='git@github.com:my-org/private-skills.git',
        ssh_key_file='~/.ssh/id_ed25519_skills',
    )
    ```

### Offline / Air-Gapped Mode

Disable automatic cloning for environments without network access:

```python
# Pre-clone the repo manually, then point the registry at it
registry = GitSkillsRegistry(
    repo_url='https://github.com/anthropics/skills',
    target_dir='/opt/skills-mirror',
    auto_install=False,
)
```

### Skill Metadata Enrichment

Skills loaded from a registry automatically receive extra metadata:

```python
skill = await registry.get('pdf')
print(skill.metadata)
# {
#     'source_url': 'https://github.com/anthropics/skills/tree/main/skills/pdf',
#     'registry': 'GitSkillsRegistry',
#     'repo': 'https://github.com/anthropics/skills',
#     'version': 'abc123...',  # HEAD commit SHA
# }
```

## S3SkillsRegistry

`S3SkillsRegistry` downloads skills from an Amazon S3 bucket — or any S3-compatible store such as MinIO, Ceph, or Cloudflare R2 — into a local cache, then discovers `SKILL.md` files the same way the Git registry does.

Install the optional dependency:

```bash
pip install pydantic-ai-skills[s3]
```

All connection details (credentials, `endpoint_url`, region, TLS, path-style addressing) live on the **boto3 client** you supply via `boto3_client`. When omitted, a default `boto3.client("s3")` is built, which uses boto3's standard credential resolution chain (environment variables, `~/.aws/credentials`, IAM roles, etc.).

### Constructor Parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `bucket` | `str` | *required* | Name of the S3 bucket containing the skills. |
| `prefix` | `str` | `""` | Key prefix inside the bucket where skill directories live. |
| `target_dir` | `str \| Path \| None` | `None` | Local cache directory. A temp directory is used when `None`. |
| `boto3_client` | `Any \| None` | `None` | Pre-built boto3 S3 client. A default client is created when `None`. |
| `validate` | `bool` | `True` | Validate every discovered `SKILL.md` after syncing. |
| `auto_install` | `bool` | `True` | Sync on construction (and on `search`/`get`). Set `False` for offline use. |

### Amazon S3 (Default Client)

```python
from pydantic_ai_skills.registries import S3SkillsRegistry

# Uses the ambient AWS credential chain.
registry = S3SkillsRegistry(bucket="my-skills", prefix="skills")
```

### MinIO (and Other S3-Compatible Stores)

Build a boto3 client pointed at your endpoint and pass it in. MinIO requires path-style addressing:

```python
import boto3
from botocore.config import Config
from pydantic_ai_skills.registries import S3SkillsRegistry

client = boto3.client(
    "s3",
    endpoint_url="http://localhost:9000",
    aws_access_key_id="minioadmin",
    aws_secret_access_key="minioadmin",
    config=Config(s3={"addressing_style": "path"}),
)

registry = S3SkillsRegistry(bucket="skills", boto3_client=client)
```

The same pattern works for Ceph RadosGW and Cloudflare R2 — only the `endpoint_url` and credentials change.

### Offline / Air-Gapped Mode

Set `auto_install=False` so the registry never reaches S3 and reads only from `target_dir`:

```python
registry = S3SkillsRegistry(
    bucket="skills",
    target_dir="/opt/skills-mirror",
    auto_install=False,
)
```

### Skill Metadata Enrichment

Skills loaded from S3 receive registry-specific metadata:

```python
skill = await registry.get('pdf')
print(skill.metadata)
# {
#     'source_url': 's3://my-skills/skills/pdf',
#     'registry': 'S3SkillsRegistry',
#     'bucket': 'my-skills',
#     'prefix': 'skills',
#     'version': '2024-01-01T00:00:00+00:00',  # latest object LastModified
# }
```

## Registry Composition

Registries support **lightweight views** — wrappers that transform skill names or visibility without modifying the underlying registry. These mirror the composition patterns from Pydantic AI's toolset system.

### Filtering Skills

Restrict which skills are visible:

```python
# Only expose skills with 'pdf' in their name
pdf_registry = registry.filtered(lambda skill: 'pdf' in skill.name.lower())

# Only skills with a specific tag in metadata
tagged = registry.filtered(
    lambda s: 'analytics' in (s.metadata or {}).get('tags', [])
)
```

### Prefixing Skill Names

Avoid name collisions when combining multiple registries:

```python
# All skill names get prefixed: 'pdf' → 'anthropic-pdf'
anthropic = registry.prefixed('anthropic-')

skill = await anthropic.get('anthropic-pdf')  # works
skill = await anthropic.get('pdf')            # raises KeyError
```

### Renaming Skills

Apply explicit name mappings:

```python
# Map new names to original names
renamed = registry.renamed({
    'doc-tool': 'pdf',        # 'pdf' is now accessible as 'doc-tool'
    'sheet-tool': 'xlsx',     # 'xlsx' is now accessible as 'sheet-tool'
})

skill = await renamed.get('doc-tool')   # fetches 'pdf'
skill = await renamed.get('xlsx')       # still works (unmapped names pass through)
```

### Combining Registries

Aggregate multiple registries into a single source:

```python
from pydantic_ai_skills.registries import CombinedRegistry, GitSkillsRegistry

github_registry = GitSkillsRegistry(
    repo_url='https://github.com/anthropics/skills',
    path='skills',
    target_dir='./cache/anthropic',
)

internal_registry = GitSkillsRegistry(
    repo_url='https://github.com/my-org/internal-skills',
    target_dir='./cache/internal',
)

combined = CombinedRegistry(registries=[github_registry, internal_registry])

# Searches fan out to all registries in parallel
results = await combined.search('pdf')

# get/install/update try each registry in order
skill = await combined.get('pdf')
```

When multiple registries provide a skill with the same name, **the first registry wins** (based on the order passed to `CombinedRegistry`).

### Chaining Composition

Wrappers can be chained for complex setups:

```python
# Start with a Git registry
registry = GitSkillsRegistry(
    repo_url='https://github.com/anthropics/skills',
    path='skills',
    target_dir='./cached-skills',
)

# Filter to only document-related skills, then prefix them
doc_skills = (
    registry
    .filtered(lambda s: s.name in ('pdf', 'docx', 'pptx'))
    .prefixed('docs-')
)

# doc_skills now has: 'docs-pdf', 'docs-docx', 'docs-pptx'
```

## Mixing Registries with Local Skills

`SkillsToolset` supports all three skill sources simultaneously. **Priority order**: programmatic skills > directory skills > registry skills.

```python
from pydantic_ai_skills import SkillsToolset, Skill
from pydantic_ai_skills.registries import GitSkillsRegistry

# 1. Programmatic skill (highest priority)
custom_skill = Skill(
    name='my-tool',
    description='Custom in-code skill',
    content='Instructions for my-tool...',
)

# 2. Git registry (lowest priority)
registry = GitSkillsRegistry(
    repo_url='https://github.com/anthropics/skills',
    path='skills',
    target_dir='./cached-skills',
)

# All three sources combined
toolset = SkillsToolset(
    skills=[custom_skill],              # Programmatic skills
    directories=['./skills'],           # Local filesystem skills
    registries=[registry],              # Remote registry skills
)
```

If a skill name appears in multiple sources, the higher-priority source wins and a duplicate warning is emitted for directory-level conflicts.

## Creating Custom Registries

Implement the `SkillRegistry` abstract base class to create your own registry backed by any source (REST API, database, cloud storage, etc.):

```python
from pathlib import Path
from pydantic_ai_skills.registries import SkillRegistry
from pydantic_ai_skills.types import Skill

class MyApiRegistry(SkillRegistry):
    """Registry backed by a custom REST API."""

    def __init__(self, api_url: str):
        self._api_url = api_url
        self._skills: list[Skill] = []

    async def search(self, query: str, limit: int = 10) -> list[Skill]:
        # Implement search against your API
        ...

    async def get(self, skill_name: str) -> Skill:
        # Fetch a single skill by name
        ...

    async def install(self, skill_name: str, target_dir: str | Path) -> Path:
        # Download and install the skill
        ...

    async def update(self, skill_name: str, target_dir: str | Path) -> Path:
        # Update an installed skill
        ...

    def get_skills(self) -> list[Skill]:
        # Return all available skills (synchronous, called during init)
        return self._skills
```

You can also extend `WrapperRegistry` to create custom composition wrappers:

```python
from pydantic_ai_skills.registries import WrapperRegistry
from pydantic_ai_skills.types import Skill

class LoggingRegistry(WrapperRegistry):
    """Registry that logs all operations."""

    async def search(self, query: str, limit: int = 10) -> list[Skill]:
        print(f'Searching for: {query}')
        results = await self.wrapped.search(query, limit)
        print(f'Found {len(results)} results')
        return results
```

## Registry API

All registries implement the following interface:

| Method | Description |
|--------|-------------|
| `search(query, limit)` | Search for skills by keyword (async) |
| `get(skill_name)` | Retrieve a single skill by name (async) |
| `install(skill_name, target_dir)` | Copy a skill to a local directory (async) |
| `update(skill_name, target_dir)` | Update an installed skill (async) |
| `get_skills()` | Return all available skills (sync, used by `SkillsToolset`) |
| `filtered(predicate)` | Return a filtered view of this registry |
| `prefixed(prefix)` | Return a view with prefixed skill names |
| `renamed(name_map)` | Return a view with renamed skills |

## Security Considerations

- **Trusted sources only**: Only use registries from sources you trust. Malicious skills can execute code or invoke tools in unintended ways.
- **Token handling**: Tokens are embedded in clone URLs but never exposed in `repr()` or logs. The `_sanitize_url()` helper redacts credentials.
- **Path traversal**: Both source and destination paths are validated during `install()` to prevent symlink-based escapes.
- **SSH key permissions**: A warning is emitted if SSH key files have permissions wider than `0o600`.
- **Skill validation**: By default, all discovered skills pass through `validate_skill_metadata()` after cloning.

!!! warning

    Skills loaded from remote registries carry the same security implications as any third-party code. Always audit skills from untrusted sources before use. See [Security & Deployment](security.md) for detailed guidance.

## See Also

- [Quick Start](quick-start.md) — Get started with basic skills
- [Core Concepts](concepts.md) — Understanding the skill system
- [Advanced Features](advanced.md) — Decorators, templates, dependency injection
- [API Reference — Registries](api/registries.md) — Full API documentation
- [Security & Deployment](security.md) — Production security guidance
