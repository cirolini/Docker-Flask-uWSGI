FROM python:3-alpine

RUN apk add --virtual .build-dependencies \ 
            --no-cache \
            python3-dev \
            build-base \
            linux-headers \
            pcre-dev

RUN apk add --no-cache pcre

WORKDIR /app
COPY /app /app
COPY ./requirements.txt /app

RUN pip install -r /app/requirements.txt

RUN apk del .build-dependencies && rm -rf /var/cache/apk/*

EXPOSE 5000
CMD ["uwsgi", "--ini", "/app/wsgi.ini"]
