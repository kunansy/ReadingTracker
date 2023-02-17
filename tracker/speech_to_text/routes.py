from typing import TypedDict

import speech_recognition
from fastapi import APIRouter, HTTPException

from tracker.common.log import logger


router = APIRouter(
    prefix="/speech-to-text",
    tags=['Speech Recognition'],
)
text: str = ''
recognizer = speech_recognition.Recognizer()


class RecognitionResult(TypedDict):
    transcript: str
    confidence: float


@router.post("/listen")
async def listen_text():
    # TODO: yes, it's a crutch. Waiting for normal front
    global text
    text = ''

    logger.info("Start listening")
    audio = listen()

    logger.info("Audio recorded, start recognition")
    result = recognizer.recognize_google(audio, language="ru", show_all=True)

    best = get_best_result(result)
    text = best['transcript']

    logger.info("Transcript got: %s", best)


@router.get("/result")
async def get_transcript():
    if not text:
        raise HTTPException(status_code=404, detail="Text not found")

    return {
        'transcript': text
    }


def listen() -> speech_recognition.AudioData:
    with speech_recognition.Microphone() as source:
        audio = recognizer.listen(source)

    return audio


def read_file(path: Path) -> speech_recognition.AudioData:
    with speech_recognition.AudioFile(str(path)) as source:
        return recognizer.record(source)


def get_best_result(results: dict) -> RecognitionResult:
    if not (texts := results.get('alternative')):
        raise ValueError("No results found")

    texts.sort(key=lambda result: result.get('confidence', 0), reverse=True)
    return texts[0]
