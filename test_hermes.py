import asyncio
from agents.base import AgentConfig
from agents.subprocess import SubprocessAgent

async def main():
    config = AgentConfig(
        name="hermes",
        label="Hermes (Gemini)",
        type="subprocess",
        command="hermes",
        args=["chat"],
        auto_resume=True,
    )
    agent = SubprocessAgent(config, use_pty=False)
    await agent.connect()
    print("Connected")
    
    async def listen(text):
        print(f"OUTPUT: {text!r}")
        
    asyncio.create_task(agent.listen(listen))
    
    await asyncio.sleep(2)
    print("Sending message")
    await agent.send("Hello")
    await asyncio.sleep(5)
    await agent.disconnect()

asyncio.run(main())
