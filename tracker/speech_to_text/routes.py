from pathlib import Path
from typing import TypedDict

import pydub
import speech_recognition
from fastapi import APIRouter, HTTPException, Body

from tracker.common.log import logger
from tracker.speech_to_text import schemas


router = APIRouter(
    prefix="/speech-to-text",
    tags=['Speech Recognition'],
)
text: str = ''
recognizer = speech_recognition.Recognizer()


class RecognitionResult(TypedDict):
    transcript: str
    confidence: float


@router.post("/transcript",
             response_model=schemas.TranscriptTextResponse)
async def listen_text(data: bytes = Body()):

    content = [
        row
        for row in data.split(b'\r\n')[4:]
        if row != b'' and not row.startswith(b'--')
    ]
    file = b'\r\n'.join(content)
    path = Path('tmp.wav')

    with path.open('wb') as f:
        f.write(file)

    sound = pydub.AudioSegment.from_file(path)
    sound.export(path, format="wav")

    logger.info("Start listening")
    audio = read_file(path)

    logger.info("Audio recorded, start recognition")
    result = recognizer.recognize_google(audio, language="ru", show_all=True)

    logger.debug("Result got: %s", result)
    best = get_best_result(result)

    logger.info("Transcript got: %s", best)

    return best


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
