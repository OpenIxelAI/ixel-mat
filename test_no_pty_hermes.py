import asyncio
from agents.base import AgentConfig
from agents.subprocess import SubprocessAgent

async def main():
    config = AgentConfig(
        name="hermes", label="Hermes", type="subprocess",
        command="hermes", args=["chat", "-Q"], auto_resume=True
    )
    agent = SubprocessAgent(config, use_pty=False)
    await agent.connect()
    
    print("Connected. Sending...")
    res = await agent.send_and_receive("Hello")
    print(f"RESPONSE: {res!r}")
    
    await agent.disconnect()

asyncio.run(main())
