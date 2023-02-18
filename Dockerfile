FROM ubuntu:20.04 as builder

# to disable tzdata question
ENV DEBIAN_FRONTEND noninteractive
ENV TZ Etc/UTC

RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get -y install gcc wget make xz-utils yasm \
    && wget https://launchpad.net/ubuntu/+archive/primary/+sourcefiles/ffmpeg/7:5.1.1-1ubuntu1/ffmpeg_5.1.1.orig.tar.xz \
    && tar xvf ffmpeg_5.1.1.orig.tar.xz \
    && cd ffmpeg-5.1.1 \
    && ./configure \
    && make install

FROM python:3.11-slim-buster as reading-tracker

LABEL maintainer="<kolobov.kirill@list.ru>"
ENV PYTHONUNBUFFERED 1

COPY --from=builder /usr/local/bin/ffmpeg /usr/local/bin/ffmpeg
COPY --from=builder /usr/local/bin/ffprobe /usr/local/bin/ffprobe

RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get -y install curl gcc portaudio19-dev flac libasound-dev \
    && pip install -U pip --no-cache-dir \
    && pip install poetry --no-cache-dir \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY poetry.lock pyproject.toml /app/
RUN poetry config virtualenvs.create false \
    && poetry install --no-dev -n

COPY /templates /app/templates
COPY /static /app/static
COPY /tracker /app/tracker
COPY VERSION /app/VERSION
