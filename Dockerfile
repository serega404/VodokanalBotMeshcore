FROM python:3.12-alpine

LABEL maintainer="serega404"

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

ARG START_FILE=start_meshcore_tcp.py

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Setting up crontab
COPY crontab /tmp/crontab
RUN cat /tmp/crontab > /etc/crontabs/root

COPY src ./src
COPY ${START_FILE} start.py

# run crond as main process of container
CMD ["crond", "-f", "-l", "2"]
