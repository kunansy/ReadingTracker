FROM python:3.13-slim-bullseye

LABEL maintainer="<k@kunansy.ru>"
ENV PYTHONUNBUFFERED=1
ENV PYTHONOPTIMIZE=2
ENV PROMETHEUS_MULTIPROC_DIR=./metrics/

COPY --from=umputun/cronn:v1.0.0 /srv/cronn /srv/cronn

COPY poetry.lock pyproject.toml entrypoint.sh /

RUN apt-get update \
    && apt-get -y install gcc curl g++ libffi-dev build-essential cargo pkg-config \
    && pip install -U pip poetry~=2.1.0 --no-cache-dir \
    && poetry config virtualenvs.create false \
    && poetry install --only main -n --no-root \
    && ./entrypoint.sh \
    && rm poetry.lock pyproject.toml entrypoint.sh  \
    && apt-get remove gcc g++ build-essential cargo pkg-config -y \
    && pip uninstall -y poetry \
    && apt-get autoremove -y \
    && apt-get clean autoclean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /var/lib/{apt,dpkg,cache,log}/

USER tracker
WORKDIR /app

COPY /templates ./templates
COPY /static ./static
COPY /kafka ./kafka
COPY /tracker ./tracker
COPY VERSION ./VERSION
