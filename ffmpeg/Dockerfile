FROM ubuntu:20.04

ENV DEBIAN_FRONTEND noninteractive
ENV TZ Etc/UTC

RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get -y install gcc wget make yasm xz-utils pkg-config \
    && wget --no-check-certificate https://launchpad.net/ubuntu/+archive/primary/+sourcefiles/ffmpeg/7:5.1.1-1ubuntu1/ffmpeg_5.1.1.orig.tar.xz \
    && tar xvf ffmpeg_5.1.1.orig.tar.xz \
    && cd ffmpeg-5.1.1 \
    && ./configure --pkg-config-flags="--static" --extra-ldexeflags="-static" \
    && make -j $(nproc) \
    && make install -j $(nproc) \
    && rm /ffmpeg_5.1.1.orig.tar.xz \
    && rm -rf /ffmpeg-5.1.1 \
    && apt-get remove gcc wget make yasm xz-utils pkg-config -y \
    && apt-get clean \
    && apt-get autoclean \
    && rm -rf /var/lib/apt/lists/*
