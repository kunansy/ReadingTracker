ARG MANTICORE_VERSION=5.0.2

FROM manticoresearch/manticore:${MANTICORE_VERSION}

RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install wget -y && \
    wget https://repo.manticoresearch.com/repository/morphology/en.pak.tgz && \
    wget https://repo.manticoresearch.com/repository/morphology/ru.pak.tgz && \
    tar xvf en.pak.tgz && \
    tar xvf ru.pak.tgz && \
    rm en.pak.tgz && \
    rm ru.pak.tgz && \
    mv en.pak /usr/share/manticore/ && \
    mv ru.pak /usr/share/manticore/ && \
    wget https://repo.manticoresearch.com/manticore-repo.noarch.deb && \
    dpkg -i manticore-repo.noarch.deb && \
    apt-get update && \
    apt-get install manticore-columnar-lib -y &&\
    apt-get remove wget -y
