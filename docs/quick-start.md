# Quick Start

Build an agent that loads a skill and runs the script that skill ships.

## 1. Install

```bash
pip install pydantic-ai-skills
```

This pulls in `pydantic-ai-harness[skills]`, which does the `SKILL.md` reading. Add
`pip install "pydantic-ai-skills[git]"` or `[s3]` when you need remote registries.

## 2. Write a skill

A **library** is a directory whose immediate children are skill packages:

```text
skills/
└── arxiv-search/
    ├── SKILL.md
    └── scripts/
        └── search.py
```

`skills/arxiv-search/SKILL.md`:

```markdown
---
name: arxiv-search
description: Search arXiv for recent papers on a topic. Use when the user asks about published research.
---

# arXiv Search

To find papers, run `scripts/search.py` with a `query` argument and an optional
`max_results` (default 5). It returns titles, authors, and abstract snippets.

Summarize the results rather than pasting them verbatim.
```

The `description` is the only field the model sees before loading the skill, so write it to answer
"should I load this?" — say what the skill does *and* when to use it.

`skills/arxiv-search/scripts/search.py`:

```python
"""Search arXiv. Arguments arrive as --key value pairs."""

import argparse
import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

parser = argparse.ArgumentParser()
parser.add_argument('--query', required=True)
parser.add_argument('--max_results', type=int, default=5)
args = parser.parse_args()

url = 'http://export.arxiv.org/api/query?' + urllib.parse.urlencode(
    {'search_query': f'all:{args.query}', 'max_results': args.max_results}
)
with urllib.request.urlopen(url, timeout=30) as response:
    feed = ET.fromstring(response.read())

ns = {'atom': 'http://www.w3.org/2005/Atom'}
papers = [
    {
        'title': ' '.join(entry.findtext('atom:title', '', ns).split()),
        'summary': ' '.join(entry.findtext('atom:summary', '', ns).split())[:300],
    }
    for entry in feed.findall('atom:entry', ns)
]
print(json.dumps(papers, indent=2))
```

## 3. Wire it up

```python
from pydantic_ai import Agent
from pydantic_ai_skills import SkillsCapability

agent = Agent(
    'anthropic:claude-sonnet-4-6',
    instructions='You are a helpful research assistant.',
    capabilities=[SkillsCapability('./skills')],
)

result = agent.run_sync('What are the last 3 papers on arXiv about mechanistic interpretability?')
print(result.output)
```

## What happens during that run

1. The model's prompt carries a catalog entry: `arxiv-search — Search arXiv for recent papers…`.
   The instructions and the script are not in context.
2. Recognizing the task, the model calls `load_capability(id='arxiv-search')`. The `SKILL.md` body
   arrives as instructions.
3. Following them, it calls
   `run_skill_script(skill_name='arxiv-search', script_name='scripts/search.py', args={'query': 'mechanistic interpretability', 'max_results': 3})`.
4. The script runs and its stdout comes back as the tool result.
5. The model summarizes.

Step 2 is Pydantic AI's own [deferred capability](https://ai.pydantic.dev/capabilities/) flow via
harness; steps 3–4 are what this package adds.

## Adding a reference file

Anything readable as UTF-8 text in the skill directory is a resource, named by its path relative to
the skill:

```text
skills/arxiv-search/
├── SKILL.md
├── references/
│   └── CATEGORIES.md      ← read_skill_resource('arxiv-search', 'references/CATEGORIES.md')
└── scripts/
    └── search.py          ← run_skill_script('arxiv-search', 'scripts/search.py')
```

Name the file in `SKILL.md` so the model knows to reach for it:

```markdown
For subject-code filters, consult `references/CATEGORIES.md` before building a query.
```

## Skills from a repository

```python
from pydantic_ai_skills import GitSkillsRegistry, SkillsCapability

agent = Agent(
    'anthropic:claude-sonnet-4-6',
    capabilities=[
        SkillsCapability(
            './skills',  # your own
            registries=[
                GitSkillsRegistry(
                    'https://github.com/anthropics/skills',
                    path='skills',
                    target_dir='~/.cache/agent-skills',
                ),
            ],
        ),
    ],
)
```

Requires the `git` extra. See [Registries](registries.md) for authentication, shallow clones, and
composing several sources.

## Choosing which skills to expose

```python
SkillsCapability('./skills', include=['arxiv-search'])   # only these
SkillsCapability('./skills', exclude=['experimental'])   # everything but these
```

The two cannot be combined. Unknown names raise at construction, so a typo fails immediately rather
than silently exposing the wrong catalog.

## Turning off the file tools

```python
SkillsCapability('./skills', scripts=False)   # no run_skill_script
SkillsCapability('./skills', resources=False) # no read_skill_resource
```

With both off, this behaves like harness `Skills` on its own. To keep scripts but move them off the
host, use a [sandbox executor](sandbox.md) instead of disabling them.

## Next

- [Core Concepts](concepts.md) — how the pieces fit and what runs when.
- [Creating Skills](creating-skills.md) — the full `SKILL.md` format and discovery rules.
- [Security](security.md) — what running a skill's scripts actually means.
