import asyncio
from edge_tts import Communicate

async def generate_audio(text, output_path, voice="en-US-GuyNeural"):
    communicate = Communicate(text, voice)
    await communicate.save(output_path)

def generate_audio_sync(text, output_path, voice="en-US-GuyNeural"):
    asyncio.run(generate_audio(text, output_path, voice))
