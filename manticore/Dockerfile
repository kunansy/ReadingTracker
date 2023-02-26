ARG MANTICORE_VERSION=6.0.2

FROM manticoresearch/manticore:${MANTICORE_VERSION}

RUN apt-get update && \
    apt-get upgrade -y && \
    wget https://repo.manticoresearch.com/repository/morphology/en.pak.tgz && \
    wget https://repo.manticoresearch.com/repository/morphology/ru.pak.tgz && \
    tar xvf en.pak.tgz && \
    tar xvf ru.pak.tgz && \
    rm en.pak.tgz && \
    rm ru.pak.tgz && \
    mv en.pak /usr/share/manticore/ && \
    mv ru.pak /usr/share/manticore/
