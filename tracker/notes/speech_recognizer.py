from pathlib import Path

import pydub
import speech_recognition

from tracker.common import settings
from tracker.common.logger import logger
from tracker.notes import schemas


recognizer = speech_recognition.Recognizer()


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


def remove(path: Path) -> None:
    path.unlink(missing_ok=True)


def fix_file_format(path: Path) -> None:
    logger.debug("Fix file format, size=%s", path.stat().st_size)

    sound = pydub.AudioSegment.from_file(path)
    sound.export(path, format="wav")

    logger.debug("File format fixed, new size=%s, duration=%ss",
                 path.stat().st_size, round(sound.duration_seconds, 2))


def read_file(path: Path) -> speech_recognition.AudioData:
    with speech_recognition.AudioFile(str(path)) as source:
        return recognizer.record(source)


def recognize(audio: speech_recognition.AudioData) -> dict:
    return recognizer.recognize_google(audio, language="ru", show_all=True)


def get_best_result(results: dict) -> schemas.RecognitionResult:
    if not (texts := results.get('alternative')):
        raise ValueError("No results found")

    texts.sort(key=lambda result: result.get('confidence', 0), reverse=True)
    return texts[0].lower()
