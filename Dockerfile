FROM harbor.nova.hksmartone.com/gitlab/base-images/python-3.11.8-poetry

USER root

RUN apt-get update && \
    apt-get -y install libpq-dev --no-install-recommends

USER app
COPY ./server /app
COPY ./frontend/dist /app/server/dist
RUN poetry install
WORKDIR /app/server

EXPOSE 8080
CMD ["poetry", "run", "uvicorn", "--host=0.0.0.0", "--port=8080", "app:app"]
