from pathlib import Path
from typing import TypedDict

import pydub
import speech_recognition
from fastapi import APIRouter, Body, HTTPException

from tracker.common import settings
from tracker.common.log import logger
from tracker.speech_to_text import schemas


router = APIRouter(
    prefix="/speech-to-text",
    tags=['Speech Recognition'],
)
recognizer = speech_recognition.Recognizer()


class RecognitionResult(TypedDict):
    transcript: str
    confidence: float


@router.post("/transcript",
             response_model=schemas.TranscriptTextResponse)
async def transcript_speech(data: bytes = Body()):
    file = get_file_content(data)
    path = dump(file)
    fix_file_format(path)

    logger.info("Start reading file")
    audio = read_file(path)

    logger.info("File read, start recognition")
    result = recognizer.recognize_google(audio, language="ru", show_all=True)
    if not result:
        raise HTTPException(status_code=400, detail="Could not recognize speech")

    logger.debug("Result got: %s", result)
    best = get_best_result(result)

    logger.info("Transcript got: %s", best)

    return best


def get_file_content(data: bytes) -> bytes:
    return b'\r\n'.join(
        row
        for row in data.split(b'\r\n')[4:]
        if row != b'' and not row.startswith(b'--')
    )


def dump(content: bytes) -> Path:
    logger.debug("Dumping to file")
    path = settings.DATA_DIR / 'tmp.wav'
    with path.open('wb') as f:
        f.write(content)

    logger.debug("File dumped: %s", path)
    return path


def fix_file_format(path: Path) -> None:
    logger.debug("Fix file format, size=%s", path.stat().st_size)

    sound = pydub.AudioSegment.from_file(path)
    sound.export(path, format="wav")

    logger.debug("File format fixed, new size=%s, duration=%ss",
                 path.stat().st_size, round(sound.duration_seconds, 2))


def read_file(path: Path) -> speech_recognition.AudioData:
    with speech_recognition.AudioFile(str(path)) as source:
        return recognizer.record(source)


def get_best_result(results: dict) -> RecognitionResult:
    if not (texts := results.get('alternative')):
        raise ValueError("No results found")

    texts.sort(key=lambda result: result.get('confidence', 0), reverse=True)
    return texts[0]
