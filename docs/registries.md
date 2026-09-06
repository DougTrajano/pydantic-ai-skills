# Skill Registries

A **registry** is a source of skill libraries. It fetches Agent Skill packages from wherever they
live and materializes them as a local directory, which `SkillsCapability` hands to harness.

That is the whole contract — one synchronous method:

```python
class SkillRegistry(ABC):
    @abstractmethod
    def sync(self) -> Path:
        """Materialize the skills and return the local library directory."""
```

`sync()` is idempotent: calling it again refreshes the local copy (a `git pull`, an S3 re-sync)
rather than starting over. Registries do not parse `SKILL.md` — validating and rendering the
packages in the directory they return is harness's job.

## Git {#git}

```bash
pip install "pydantic-ai-skills[git]"
```

```python
from pydantic_ai_skills import GitSkillsRegistry, SkillsCapability

registry = GitSkillsRegistry(
    'https://github.com/anthropics/skills',
    path='skills',                      # sub-path inside the repo holding the packages
    target_dir='~/.cache/agent-skills', # where to clone; defaults to a temp dir
)

capability = SkillsCapability(registries=[registry])
```

It reads the filesystem after cloning and never calls a hosting platform's API, so it works with
GitHub, GitLab, Bitbucket, and self-hosted servers over HTTPS or SSH.

### Authentication

```python
# Personal access token (falls back to $GITHUB_TOKEN when omitted)
GitSkillsRegistry('https://github.com/acme/private-skills', token='ghp_...')

# SSH key
GitSkillsRegistry('git@github.com:acme/private-skills.git', ssh_key_file='~/.ssh/id_ed25519')
```

A token is embedded in the clone URL, never in `repr()` or in an error message. The SSH path sets
`GIT_SSH_COMMAND` with `StrictHostKeyChecking=accept-new`, and warns if the key file is readable by
group or other.

### Shallow and sparse clones

A large monorepo is worth narrowing:

```python
from pydantic_ai_skills import GitCloneOptions, GitSkillsRegistry

GitSkillsRegistry(
    'https://github.com/anthropics/skills',
    path='skills/pdf',
    clone_options=GitCloneOptions(
        depth=1,
        single_branch=True,
        sparse_paths=['skills/pdf'],
        multi_options=['--filter=blob:none'],
    ),
)
```

### Offline and air-gapped

```python
GitSkillsRegistry(
    'https://github.com/anthropics/skills',
    target_dir='/opt/skills-mirror',
    auto_install=False,   # sync() never reaches the network
)
```

With `auto_install=False`, `sync()` returns whatever is already on disk and raises a clear error if
nothing has been cloned.

### Pinning a version

`sync()` tracks a moving branch. To record which commit a run actually used:

```python
registry.sync()
print(registry.revision())   # 'a1b2c3d...' or None if not cloned
```

To pin rather than record, use `GitCloneOptions(branch='v1.2.0')` with a tag.

## S3 {#s3}

```bash
pip install "pydantic-ai-skills[s3]"
```

```python
from pydantic_ai_skills import S3SkillsRegistry

registry = S3SkillsRegistry(
    bucket='acme-agent-skills',
    prefix='skills',
    target_dir='~/.cache/agent-skills',
)
```

Each `sync()` mirrors the prefix: the cached subtree is cleared first, so a skill deleted from the
bucket stops appearing locally.

Connection details all live on the boto3 client, which makes any S3-compatible store work:

```python
import boto3
from botocore.config import Config

client = boto3.client(
    's3',
    endpoint_url='http://localhost:9000',
    aws_access_key_id='minioadmin',
    aws_secret_access_key='minioadmin',
    config=Config(s3={'addressing_style': 'path'}),
)
S3SkillsRegistry(bucket='skills', boto3_client=client)
```

With no client, a default `boto3.client('s3')` is built, using boto3's standard credential chain.
`auto_install=False` works as it does for Git. `revision('pdf')` reports the newest object
modification time for one skill.

Object keys are checked before download: a key that would write outside `target_dir` raises rather
than escaping.

## Local {#local}

```python
from pydantic_ai_skills.registries import LocalSkillsRegistry

LocalSkillsRegistry('./skills')
```

Passing a local directory straight to `SkillsCapability(directories=...)` is simpler and does the
same thing. Reach for this only when a local library needs **composing** — merged with a remote one,
prefixed, or filtered — since composition operates on registries.

## Composition {#composition}

Every registry has `filtered()`, `prefixed()` and `renamed()`, and `|` merges two. Each returns a
view; the wrapped registry is never modified.

Composition works by **staging**: the wrapper syncs what it wraps, then copies the packages it wants
into a new directory under the names it wants. That is what makes the result a real library harness
can read.

### Filtering

The predicate receives a `SkillInfo` — the skill's name, description, and directory:

```python
pdf_only = registry.filtered(lambda info: 'pdf' in info.name)
documents = registry.filtered(lambda info: 'document' in info.description.lower())
```

### Prefixing and renaming

```python
vendor = registry.prefixed('vendor-')          # 'pdf' → 'vendor-pdf'
aliased = registry.renamed({'documents': 'pdf'})  # {new_name: original_name}
```

Both rewrite each staged package's frontmatter `name` as well as its directory name, because harness
requires the two to agree. A name that would not be valid — an uppercase prefix, say — raises at
`sync()` naming the operation that produced it, rather than surfacing later as an opaque harness
error.

### Merging

```python
from pydantic_ai_skills.registries import CombinedRegistry

combined = CombinedRegistry(registries=[internal, public])
combined = internal | public   # the same thing
```

Earlier registries win on a duplicate skill name, and the shadowed one is reported with a
`UserWarning`. To expose both, prefix them:

```python
combined = internal.prefixed('acme-') | public.prefixed('anthropic-')
```

### Chaining

Wrappers compose, each staging from the previous one's output:

```python
source = (
    GitSkillsRegistry('https://github.com/anthropics/skills', path='skills')
    .filtered(lambda info: info.name in {'pdf', 'xlsx', 'docx'})
    .prefixed('office-')
)
```

Note that order matters: `prefixed().filtered()` gives the predicate the *prefixed* names, because
filtering runs against the staged library.

### Where staged libraries live

By default each wrapper stages into a temporary directory that lives as long as the process. Pass
`target_dir=` to pin it:

```python
from pydantic_ai_skills.registries import FilteredRegistry

FilteredRegistry(
    wrapped=source,
    predicate=lambda info: 'pdf' in info.name,
    target_dir='./staged-skills',
)
```

An existing `target_dir` is emptied on each sync, so a narrowed filter does not leave the previous
run's skills behind.

## Inspecting a registry

```python
registry.skill_names()   # ['pdf', 'xlsx']
registry.skill_infos()   # [SkillInfo(name='pdf', description='...', directory=...), ...]
```

Both sync first. Useful for a CLI or a health check, without building an agent.

## Writing your own

One method:

```python
from pathlib import Path

from pydantic_ai_skills import SkillRegistry


class HttpArchiveRegistry(SkillRegistry):
    """Download and unpack a tarball of skill packages."""

    def __init__(self, url: str, target_dir: Path) -> None:
        self.url = url
        self.target_dir = target_dir

    def sync(self) -> Path:
        download_and_extract(self.url, self.target_dir)
        return self.target_dir
```

You get `filtered()`, `prefixed()`, `renamed()`, `|`, `skill_names()` and `skill_infos()` for free.

The directory you return must be a **library**: its immediate children are skill packages, and it
must not itself contain a `SKILL.md`. harness rejects the latter with a clear error.

## Lifecycle

A registry that was not given a `target_dir` owns a temporary directory tied to its own lifetime.
Keep the registry referenced for as long as you need the files:

```python
# Fine: the capability holds the registry.
capability = SkillsCapability(registries=[GitSkillsRegistry(url)])

# Not fine: the registry is collected, taking its clone with it.
library = GitSkillsRegistry(url).sync()
```

Pass `target_dir=` for a cache you control. Those directories are never cleaned up automatically.

## Trust

Registry skills are the least-trusted source there is: their instructions steer the model and their
scripts run wherever your executor puts them. Use a [sandbox executor](sandbox.md) for anything you
do not control, and read [Security](security.md) before pointing an agent at a repository you do not
own.
