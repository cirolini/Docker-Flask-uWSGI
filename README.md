# Docker-Flask-uWSGI

Docker container with uWSGI for Flask apps in Python 3

## Description
This Docker image is a example to create Flask web applications in Python 3 that run with uWSGI.

This example is a simple example to create your own container and scale de processes with uWSGI ini file.

GitHub repo: https://github.com/cirolini/Docker-Flask-uWSGI

## QuickStart

You can run this container direct in shell like:

```
docker run -p 5000:5000 cirolini/flask-uwsgi:latest
```

And test in a curl command ou your browser like this:

```
curl -v "http://localhost:5000/"
``` 
