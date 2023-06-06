FROM ubuntu:20.04 as builder

ENV DEBIAN_FRONTEND noninteractive
ENV TZ Etc/UTC

RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get -y install gcc wget make yasm xz-utils pkg-config \
    && wget https://launchpad.net/ubuntu/+archive/primary/+sourcefiles/ffmpeg/7:5.1.1-1ubuntu1/ffmpeg_5.1.1.orig.tar.xz \
    && tar xvf ffmpeg_5.1.1.orig.tar.xz \
    && cd ffmpeg-5.1.1 \
    && ./configure --pkg-config-flags="--static" --extra-ldexeflags="-static" \
    && make -j $(nproc) \
    && make install -j $(nproc)

FROM python:3.11-slim-buster as reading-tracker

LABEL maintainer="<k@kunansy.ru>"
ENV PYTHONUNBUFFERED 1

COPY --from=builder /usr/local/bin/ffmpeg /usr/local/bin/ffmpeg
COPY --from=builder /usr/local/bin/ffprobe /usr/local/bin/ffprobe

RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get -y install gcc curl portaudio19-dev flac libasound-dev \
    && pip install -U pip poetry --no-cache-dir \
    && apt-get clean \
    && apt-get autoclean \
    && rm -rf /var/lib/apt/lists/*

COPY poetry.lock pyproject.toml entrypoint.sh /
RUN poetry config virtualenvs.create false \
    && poetry install --only main -n \
    && ./entrypoint.sh \
    && rm poetry.lock pyproject.toml entrypoint.sh  \
    && apt-get remove gcc -y

USER tracker
WORKDIR /app

COPY /templates /app/templates
COPY /static /app/static
COPY /tracker /app/tracker
COPY VERSION /app/VERSION
