# Security & Deployment

Security considerations, deployment patterns, and best practices for production skill systems.

## Security Foundations

### Defense in Depth

The package implements multiple security layers:

1. **Path Traversal Prevention**: Validates all file paths before access
2. **Timeout Protection**: Scripts execute with enforced timeout limits (default 30s)
3. **Subprocess Isolation**: Scripts run as isolated subprocesses, not in-process
4. **Resource Validation**: YAML frontmatter and skill structure validated
5. **Argument Validation**: Script arguments validated before execution

### Security Model

```
┌─────────────────────────────────────────┐
│         Untrusted Skill Input           │
└──────────────┬──────────────────────────┘
               │
        ┌──────▼────────┐
        │  Path Validation
        │  (traversal prevention)
        └──────┬────────┘
               │
        ┌──────▼────────┐
        │  Arg Validation
        │  (type checking)
        └──────┬────────┘
               │
        ┌──────▼──────────┐
        │ Subprocess Exec
        │ (isolated process)
        └──────┬──────────┘
               │
        ┌──────▼────────┐
        │  Timeout Mgmt
        │  (resource limits)
        └──────┬────────┘
               │
        ┌──────▼────────┐
        │   Output      │
        │ (sanitized)   │
        └──────────────┘
```

## Skill Source Trust

### Trust Levels

Implement a trust hierarchy for skills:

```python
from enum import Enum
from pydantic_ai.toolsets.skills import SkillsToolset, Skill

class SkillTrustLevel(Enum):
    """Trust levels for skills."""
    TRUSTED = "trusted"          # Vetted, internal skills
    THIRD_PARTY = "third_party"  # From trusted external sources
    UNTRUSTED = "untrusted"      # User-provided, requires sandboxing
    QUARANTINE = "quarantine"    # Suspected malicious, disabled

class SkillRegistry:
    """Manage skills with trust levels."""

    def __init__(self):
        self.skills_by_trust: dict[SkillTrustLevel, list[Skill]] = {
            level: [] for level in SkillTrustLevel
        }

    def register_skill(
        self,
        skill: Skill,
        trust_level: SkillTrustLevel
    ):
        """Register a skill with a trust level."""
        self.skills_by_trust[trust_level].append(skill)

    def create_safe_toolset(
        self,
        min_trust: SkillTrustLevel = SkillTrustLevel.TRUSTED
    ) -> SkillsToolset:
        """Create toolset with only sufficiently trusted skills."""
        accepted_skills = []

        for level, skills in self.skills_by_trust.items():
            if level.value >= min_trust.value:
                accepted_skills.extend(skills)

        return SkillsToolset(skills=accepted_skills)

# Usage
registry = SkillRegistry()

# Add trusted internal skills
internal_skill = Skill(
    name='internal-analysis',
    description='Internal data analysis',
    content='Trusted content...'
)
registry.register_skill(internal_skill, SkillTrustLevel.TRUSTED)

# Create agent with only trusted skills
safe_toolset = registry.create_safe_toolset(
    min_trust=SkillTrustLevel.TRUSTED
)
```

### Verification Patterns

```python
import hashlib
from pathlib import Path
from pydantic_ai.toolsets.skills import Skill, SkillsDirectory

class VerifiedSkill:
    """Skill with integrity verification."""

    def __init__(self, skill: Skill, checksum: str | None = None):
        self.skill = skill
        self.checksum = checksum

    @staticmethod
    def compute_checksum(skill: Skill) -> str:
        """Compute SHA256 checksum of skill content."""
        content = f"{skill.name}:{skill.description}:{skill.content}"
        return hashlib.sha256(content.encode()).hexdigest()

    def verify(self) -> bool:
        """Verify skill hasn't been modified."""
        if not self.checksum:
            return True  # No checksum to verify

        computed = self.compute_checksum(self.skill)
        return computed == self.checksum

# Usage
skills = SkillsDirectory(path='./skills')
discovered = skills.discover()

# Store checksums when skills are vetted
verified_checksums = {
    'data-analyzer': 'abc123...',
    'web-research': 'def456...'
}

for skill_name, skill in discovered.items():
    checksum = verified_checksums.get(skill_name)
    verified = VerifiedSkill(skill, checksum)

    if not verified.verify():
        print(f"WARNING: Skill {skill_name} checksum mismatch!")
        # Could disable or quarantine skill
```

## Script Execution Safety

### Subprocess Isolation

By default, scripts run in isolated subprocesses (not in-process):

```python
# ✅ Safe: Subprocess execution (default)
# Crashes, infinite loops, or resource exhaustion
# don't affect the main agent process

from pydantic_ai.toolsets.skills import SkillScript, LocalSkillScriptExecutor

executor = LocalSkillScriptExecutor(
    python_executable=None,  # Uses default Python
    script_timeout=30        # 30 second timeout
)

script = SkillScript(
    name='analysis',
    function=None,
    uri='./scripts/analyze.py'
)
```

### Input Sanitization

```python
import shlex
from typing import Any

def sanitize_script_args(args: dict[str, Any]) -> dict[str, str]:
    """Sanitize arguments before passing to script.

    Prevents:
    - Command injection
    - Path traversal
    - Unsafe data types
    """
    sanitized = {}

    for key, value in args.items():
        # Validate key format
        if not key.isidentifier():
            raise ValueError(f"Invalid argument name: {key}")

        # Convert to string and escape
        str_value = str(value)

        # Check for suspicious patterns
        if any(x in str_value for x in ['../..', '${', '$(', '`']):
            raise ValueError(f"Suspicious value for {key}: {str_value}")

        sanitized[key] = str_value

    return sanitized

# Usage
from pydantic_ai.toolsets.skills import SkillsToolset

toolset = SkillsToolset(directories=['./skills'])

# Before executing scripts
args = {'query': 'SELECT * FROM users', 'limit': '100'}
safe_args = sanitize_script_args(args)

# result = toolset.run_skill_script('my-skill', 'analyze', safe_args)
```

## Path Traversal Prevention

### How Protection Works

The toolset validates all file paths before access:

```python
from pathlib import Path

def is_safe_path(requested_path: Path, base_path: Path) -> bool:
    """Check if requested path is within base directory.

    Prevents:
    - ../../../etc/passwd attacks
    - Symlink escapes
    - Relative path traversal
    """
    try:
        # Resolve to absolute path
        resolved = (base_path / requested_path).resolve()
        base_resolved = base_path.resolve()

        # Check if resolved path is within base
        resolved.relative_to(base_resolved)
        return True

    except ValueError:
        # Path is outside base directory
        return False

# Examples
base = Path('./skills/my-skill')

# ✅ Safe paths
assert is_safe_path(Path('resource.md'), base)
assert is_safe_path(Path('scripts/analyze.py'), base)
assert is_safe_path(Path('docs/guide.txt'), base)

# ❌ Dangerous paths
assert not is_safe_path(Path('../../../etc/passwd'), base)
assert not is_safe_path(Path('/etc/passwd'), base)
assert not is_safe_path(Path('/../secret'), base)
```

### Safe Skill Directory Structure

```markdown
safe-skill/
├── SKILL.md                    # ✅ Accessed
├── reference.md                # ✅ Accessed
├── scripts/
│   └── analyze.py             # ✅ Accessed
└── resources/
    ├── templates.json         # ✅ Accessed
    └── data.csv               # ✅ Accessed

# ❌ These would not be accessible
# from outside the skill directory:
/etc/passwd
/secret/keys.txt
../other-skill/sensitive.txt
```

### Resource File Extensions

Supported file types for resources:

- **Text**: `.md`, `.txt`
- **Data**: `.json`, `.yaml`, `.yml`, `.csv`
- **Markup**: `.xml`

Files outside the skill directory or with unsupported extensions are not accessible.

## Timeout Management

### Configuration

```python
from pydantic_ai.toolsets.skills import SkillsToolset, LocalSkillScriptExecutor

# Default timeout: 30 seconds
toolset = SkillsToolset(directories=['./skills'])

# Custom timeout: 60 seconds
executor = LocalSkillScriptExecutor(script_timeout=60)

# No timeout (use carefully!)
# executor = LocalSkillScriptExecutor(script_timeout=None)
```

### Timeout Patterns

```python
import asyncio
from pydantic_ai import RunContext

# For scripts that might run long:
@skill.script
async def long_operation(
    ctx: RunContext[MyDeps],
    dataset: str,
    operation: str = 'quick'
) -> str:
    """Long operation with timeout awareness.

    Args:
        dataset: Which dataset to process
        operation: 'quick' (5s), 'medium' (15s), or 'full' (25s)
    """
    try:
        if operation == 'quick':
            return await quick_process(dataset)
        elif operation == 'medium':
            return await medium_process(dataset)
        elif operation == 'full':
            # Leave buffer for cleanup
            result = await asyncio.wait_for(
                full_process(dataset),
                timeout=25.0  # 30s limit - 5s buffer
            )
            return result
    except asyncio.TimeoutError:
        return f"Operation exceeded time limit. Try with 'quick' or 'medium' option."

# Instruct agent to use smaller operations
agent_instructions = """
When using the long_operation script:
- Start with 'quick' option for initial exploration
- Use 'medium' for standard analysis
- Only use 'full' for small datasets
- If timeout occurs, break the operation into smaller steps
"""
```

## Tool Access Control

### Restricting Available Tools

For additional security or to limit agent capabilities, you can exclude specific skill tools from being available to agents using the `exclude_tools` parameter:

```python
from pydantic_ai import Agent
from pydantic_ai.toolsets.skills import SkillsToolset

# Disable script execution only
toolset = SkillsToolset(
    directories=["./skills"],
    exclude_tools={'run_skill_script'}
)

# Disable multiple tools
toolset = SkillsToolset(
    directories=["./skills"],
    exclude_tools={'run_skill_script', 'read_skill_resource'}
)

agent = Agent(
    model='openai:gpt-4o',
    toolsets=[toolset]
)
```

### Available Tool Names

The following tools can be excluded:

- **`list_skills`**: List all available skills
- **`load_skill`**: Load full skill instructions
- **`read_skill_resource`**: Access skill resource files or invoke callable resources
- **`run_skill_script`**: Execute skill scripts

### Common Exclusion Patterns

**Prevent arbitrary code execution:**

```python
# Only allow reading skills and resources, no script execution
toolset = SkillsToolset(
    directories=["./skills"],
    exclude_tools={'run_skill_script'}
)
```

**Limit to skill discovery only:**

```python
# Agents can only list and load skills, but cannot access resources or run scripts
toolset = SkillsToolset(
    directories=["./skills"],
    exclude_tools={'read_skill_resource', 'run_skill_script'}
)
```

**Restrict resource access:**

```python
# Scripts can run, but agents cannot access resource files
toolset = SkillsToolset(
    directories=["./skills"],
    exclude_tools={'read_skill_resource'}
)
```

### Important Notes

!!! warning "Excluding load_skill"
    Excluding `load_skill` severely limits skill functionality and will emit a warning. Agents need this tool to effectively discover and understand how to use skills. Only exclude this if you have pre-loaded all skill instructions into the agent's context.

**Best Practice:** Only exclude tools you intentionally want to restrict. For example:

- Exclude `run_skill_script` if you want to prevent agents from executing arbitrary code
- Exclude `read_skill_resource` if you want to limit resource access for sensitive data
- Keep `list_skills` and `load_skill` enabled for normal skill discovery workflows

## Dependency Management

### Secure Dependency Injection

```python
from typing import TypedDict
from pydantic_ai import RunContext
from pydantic_ai.toolsets.skills import SkillsToolset

class SafeDeps(TypedDict):
    """Carefully curated dependencies."""
    database: DatabaseConnection
    logger: Logger
    # Note: No direct shell access, file system, or network

class FortifiedDeps(TypedDict):
    """More permissive dependencies with safety guards."""
    database: DatabaseConnection
    logger: Logger
    cache: CacheLayer
    email: EmailService  # Limited to specific templates

skills = SkillsToolset()

@skills.skill()
def safe_skill() -> str:
    return "Uses only safe dependencies"

@safe_skill.resource
async def get_status(ctx: RunContext[SafeDeps]) -> str:
    # Can only access database and logger
    status = await ctx.deps.database.health_check()
    await ctx.deps.logger.info(f"Health check: {status}")
    return f"Status: {status}"

# Create agent with safe dependencies
agent = Agent(
    model='openai:gpt-4o',
    toolsets=[skills],
    deps=SafeDeps(
        database=my_db,
        logger=my_logger
    )
)
```

### Secret Management

```python
import os
from functools import cached_property
from pydantic_ai.toolsets.skills import SkillsToolset

class SecureSkillDeps:
    """Dependencies with secrets managed safely."""

    @cached_property
    def database_url(self) -> str:
        """Load database URL from environment."""
        # Never log or expose in skill output
        return os.getenv('DATABASE_URL', '')

    @cached_property
    def api_key(self) -> str:
        """Load API key from secure storage."""
        # Implement secure retrieval (e.g., from vault)
        return self._get_from_vault('api-key')

    def _get_from_vault(self, secret_name: str) -> str:
        """Retrieve secret from vault."""
        # Implementation: Vault, AWS Secrets Manager, etc.
        raise NotImplementedError

skills = SkillsToolset()

@skills.skill()
def secure_api() -> str:
    return "Access external API securely"

@secure_api.resource
async def get_api_docs(ctx: RunContext[SecureSkillDeps]) -> str:
    """Get API documentation.

    API key is available via RunContext but never exposed in output.
    """
    # ✅ This is safe - the key is used but not returned
    status = await check_api_status(ctx.deps.api_key)

    # ❌ Never do this:
    # return f"API key: {ctx.deps.api_key}"

    return f"API status: {status}"
```

## Production Deployment

### Configuration Management

```python
from dataclasses import dataclass
from pathlib import Path
from pydantic_ai.toolsets.skills import SkillsToolset, SkillsDirectory

@dataclass
class SkillsConfig:
    """Skills system configuration."""
    skill_directories: list[str]
    enable_validation: bool = True
    max_discovery_depth: int = 3
    script_timeout: int = 30
    min_skill_trust_level: str = "trusted"

def create_production_toolset(config: SkillsConfig) -> SkillsToolset:
    """Create toolset for production environment."""

    # Convert to SkillsDirectory instances
    directories = [
        SkillsDirectory(
            path=Path(dir_path),
            validate=config.enable_validation,
            max_depth=config.max_discovery_depth
        )
        for dir_path in config.skill_directories
    ]

    # Create toolset
    toolset = SkillsToolset(
        directories=directories,
        validate=config.enable_validation
    )

    # Filter by trust level if needed
    if config.min_skill_trust_level != "all":
        # Implementation to filter skills
        pass

    return toolset

# Configuration for different environments
production_config = SkillsConfig(
    skill_directories=[
        "/opt/skills/verified",
        "/opt/skills/internal"
    ],
    enable_validation=True,
    max_discovery_depth=2,
    script_timeout=30,
    min_skill_trust_level="trusted"
)

staging_config = SkillsConfig(
    skill_directories=[
        "./skills/all"
    ],
    enable_validation=True,
    max_discovery_depth=3,
    script_timeout=60,
    min_skill_trust_level="all"
)

# Usage
prod_toolset = create_production_toolset(production_config)
```

### Health Checks

```python
from pydantic_ai.toolsets.skills import SkillsToolset
from pydantic_ai_skills import SkillNotFoundError

def check_skills_health(toolset: SkillsToolset) -> dict:
    """Check health of skills system."""

    health = {
        "status": "healthy",
        "total_skills": len(toolset.skills),
        "skills": {},
        "issues": []
    }

    for skill_name, skill in toolset.skills.items():
        skill_health = {
            "name": skill_name,
            "resources": len(skill.resources or []),
            "scripts": len(skill.scripts or []),
            "status": "ok"
        }

        # Check for issues
        if not skill.content or len(skill.content.strip()) < 10:
            skill_health["status"] = "warning"
            health["issues"].append(f"{skill_name}: empty content")

        if skill.scripts and len(skill.scripts) > 10:
            skill_health["status"] = "warning"
            health["issues"].append(f"{skill_name}: many scripts ({len(skill.scripts)})")

        health["skills"][skill_name] = skill_health

    if health["issues"]:
        health["status"] = "degraded"

    return health

# Usage
toolset = SkillsToolset(directories=['./skills'])
health = check_skills_health(toolset)

print(f"Overall status: {health['status']}")
if health['issues']:
    print("Issues found:")
    for issue in health['issues']:
        print(f"  - {issue}")
```

## Monitoring and Logging

### Execution Logging

```python
import json
import logging
from datetime import datetime
from pydantic_ai.toolsets.skills import SkillsToolset

logger = logging.getLogger('skills')

class AuditedSkillsToolset(SkillsToolset):
    """Skills toolset with audit logging."""

    async def run_skill_script_audited(
        self,
        skill_name: str,
        script_name: str,
        args: dict | None = None,
        user_id: str | None = None
    ) -> str:
        """Run script with audit trail."""

        audit_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "skill": skill_name,
            "script": script_name,
            "args_keys": list((args or {}).keys())  # Don't log values
        }

        try:
            logger.info(f"Script execution: {json.dumps(audit_entry)}")

            result = await self.run_skill_script(skill_name, script_name, args)

            audit_entry["status"] = "success"
            logger.info(f"Script completed: {json.dumps(audit_entry)}")

            return result

        except Exception as e:
            audit_entry["status"] = "error"
            audit_entry["error"] = str(e)

            logger.error(f"Script failed: {json.dumps(audit_entry)}")
            raise
```

### Metrics Collection

```python
import time
from typing import Any
from pydantic_ai.toolsets.skills import SkillsToolset

class MetricsCollector:
    """Collect skill execution metrics."""

    def __init__(self):
        self.metrics = {
            "scripts_executed": 0,
            "scripts_failed": 0,
            "total_execution_time": 0.0,
            "script_times": {}
        }

    def record_execution(
        self,
        skill_name: str,
        script_name: str,
        duration: float,
        success: bool
    ):
        """Record script execution metric."""
        key = f"{skill_name}/{script_name}"

        self.metrics["scripts_executed"] += 1
        if not success:
            self.metrics["scripts_failed"] += 1

        self.metrics["total_execution_time"] += duration

        if key not in self.metrics["script_times"]:
            self.metrics["script_times"][key] = []

        self.metrics["script_times"][key].append(duration)

    def get_report(self) -> dict[str, Any]:
        """Get metrics report."""
        total = self.metrics["scripts_executed"]
        failed = self.metrics["scripts_failed"]

        script_stats = {}
        for key, times in self.metrics["script_times"].items():
            script_stats[key] = {
                "count": len(times),
                "avg_time": sum(times) / len(times),
                "max_time": max(times),
                "min_time": min(times)
            }

        return {
            "total_executions": total,
            "total_failures": failed,
            "success_rate": (total - failed) / total if total > 0 else 0,
            "total_time_seconds": self.metrics["total_execution_time"],
            "by_script": script_stats
        }

# Usage
metrics = MetricsCollector()

start = time.time()
try:
    # result = toolset.run_skill_script(...)
    success = True
except Exception:
    success = False
finally:
    duration = time.time() - start
    metrics.record_execution('data-skill', 'analyze', duration, success)

print(json.dumps(metrics.get_report(), indent=2))
```

## See Also

- [Advanced Features](./advanced.md) - Custom executors and templates
- [Implementation Patterns](./patterns.md) - Error handling patterns
- [API Reference](./api/toolset.md) - SkillsToolset configuration
