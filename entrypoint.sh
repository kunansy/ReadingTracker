#!/bin/sh

useradd -ms /bin/bash tracker
mkdir -p /app/data
chown -R tracker /app/data
