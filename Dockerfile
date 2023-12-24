FROM python:3.12-slim-bullseye

LABEL maintainer="<k@kunansy.ru>"
ENV PYTHONUNBUFFERED 1
ENV PROMETHEUS_MULTIPROC_DIR=./metrics/

COPY --from=kunansy/ffmpeg:5.1.1 /usr/local/bin/ffmpeg /usr/local/bin/ffmpeg
COPY --from=kunansy/ffmpeg:5.1.1 /usr/local/bin/ffprobe /usr/local/bin/ffprobe

RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get -y install gcc curl portaudio19-dev flac libasound-dev g++ libffi-dev build-essential cargo pkg-config \
    && pip install -U pip poetry --no-cache-dir

COPY poetry.lock pyproject.toml entrypoint.sh /
RUN poetry config virtualenvs.create false \
    && poetry install --only main -n \
    && ./entrypoint.sh \
    && rm poetry.lock pyproject.toml entrypoint.sh  \
    && apt-get remove gcc g++ build-essential cargo pkg-config -y \
    && apt-get autoremove -y \
    && apt-get clean \
    && apt-get autoclean \
    && rm -rf /var/lib/apt/lists/*

USER tracker
WORKDIR /app

COPY /templates ./templates
COPY /static ./static
COPY /tracker ./tracker
COPY VERSION ./VERSION
