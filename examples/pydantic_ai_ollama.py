"""This example demonstrates how to use pydantic-ai-skills with the Ollama models through the Pydantic AI Gateway."""

from pathlib import Path

import logfire
import uvicorn
from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.gateway import gateway_provider

from pydantic_ai_skills import SkillsCapability

load_dotenv()
logfire.configure()
logfire.instrument_pydantic_ai()

# Get the skills directory (examples/skills)
skills_dir = Path(__file__).parent / 'skills'

# Initialize Skills Toolset
skills_capability = SkillsCapability(skills_dir)

# Initialize LLM
provider = gateway_provider('openai', route='ollama')
gpt_oss_20b = OpenAIChatModel(model_name='gpt-oss:20b-cloud', provider=provider)
gemma4_31b = OpenAIChatModel(model_name='gemma4:31b-cloud', provider=provider)

# Create agent with skills
agent = Agent(
    model=gpt_oss_20b,
    instructions='You are a helpful assistant.',
    capabilities=[skills_capability],
)

app = agent.to_web(models=[gemma4_31b])

if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=7932)
