FROM python:3.11-slim-buster

LABEL maintainer="<k@kunansy.ru>"
ENV PYTHONUNBUFFERED 1

COPY --from=kunansy/ffmpeg:5.1.1 /usr/local/bin/ffmpeg /usr/local/bin/ffmpeg
COPY --from=kunansy/ffmpeg:5.1.1 /usr/local/bin/ffprobe /usr/local/bin/ffprobe

RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get -y install gcc curl portaudio19-dev flac libasound-dev \
    && pip install -U pip poetry --no-cache-dir

COPY poetry.lock pyproject.toml entrypoint.sh /
RUN poetry config virtualenvs.create false \
    && poetry install --only main -n \
    && ./entrypoint.sh \
    && rm poetry.lock pyproject.toml entrypoint.sh  \
    && apt-get remove gcc -y \
    && apt-get autoremove -y \
    && apt-get clean \
    && apt-get autoclean \
    && rm -rf /var/lib/apt/lists/*

USER tracker
WORKDIR /app

COPY /templates /app/templates
COPY /static /app/static
COPY /tracker /app/tracker
COPY VERSION /app/VERSION
