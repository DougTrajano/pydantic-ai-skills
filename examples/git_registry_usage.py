"""Load skills from a remote Git repository.

Clones the public Anthropic skills repository and exposes its skills to the agent. The
registry materializes the repo as a local skill library; `pydantic-ai-harness` reads the
`SKILL.md` packages inside it, and this package adds the tools for their bundled files.
"""

import logfire
import uvicorn
from dotenv import load_dotenv
from pydantic_ai import Agent

from pydantic_ai_skills import GitCloneOptions, GitSkillsRegistry, SkillsCapability

load_dotenv()

logfire.configure()
logfire.instrument_pydantic_ai()

# Shallow, single-branch checkout into a durable cache, so a restart pulls rather than
# re-clones. Some published skills need extra tooling on the host to run.
registry = GitSkillsRegistry(
    repo_url='https://github.com/anthropics/skills',
    path='skills',
    target_dir='./cached-skills',
    clone_options=GitCloneOptions(depth=1, single_branch=True),
)

# Registry skills are the least-trusted source there is. In production, pass a sandbox
# executor here -- see examples/sandbox_opensandbox.py.
skills = SkillsCapability(registries=[registry])

agent = Agent(
    model='gateway/openai:gpt-5.2',
    instructions='You are a helpful assistant with access to a variety of skills.',
    capabilities=[skills],
)

print(f'{len(skills.skill_names)} skills at revision {registry.revision()}')

app = agent.to_web()

if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=7932)
