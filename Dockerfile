FROM python:3.6-stretch

RUN apt-get update && \
    apt-get install -y python3-pip
WORKDIR /home
COPY . .
