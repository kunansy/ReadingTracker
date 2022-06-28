FROM elasticsearch:8.2.3

USER root

RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install wget unzip -y && \
    wget -O ru.zip https://bitbucket.org/Shaman_Alex/russian-dictionary-hunspell/downloads/ru_RU_UTF-8_20131101.zip && \
    mkdir -p /usr/share/elasticsearch/config/hunspell/ru_RU && \
    unzip ru.zip -d /usr/share/elasticsearch/config/hunspell/ru_RU && \
    apt-get remove wget unzip -y && \
    apt-get autoremove -y && \
    rm ru.zip && \
    rm -rf /var/lib/apt/lists/*

USER elasticsearch:root
