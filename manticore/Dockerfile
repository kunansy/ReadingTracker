ARG MANTICORE_VERSION=6.0.2

FROM manticoresearch/manticore:${MANTICORE_VERSION}

RUN apt-get update && \
    apt-get upgrade -y && \
    wget https://repo.manticoresearch.com/repository/morphology/en.pak.tgz && \
    wget https://repo.manticoresearch.com/repository/morphology/ru.pak.tgz && \
    tar xvf en.pak.tgz -C /usr/share/manticore/ && \
    tar xvf ru.pak.tgz -C /usr/share/manticore/ && \
    rm en.pak.tgz && \
    rm ru.pak.tgz && \
    apt-get clean && \
    apt-get autoclean && \
    rm -rf /var/lib/apt/lists/*
