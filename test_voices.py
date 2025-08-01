import pyttsx3

engine = pyttsx3.init()

# List all available voices
voices = engine.getProperty('voices')
for index, voice in enumerate(voices):
    print(f"Voice {index}: {voice.name} - {voice.id}")
