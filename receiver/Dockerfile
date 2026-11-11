FROM python:3.11-slim
WORKDIR /app
RUN groupadd --gid 10001 metadata && useradd --uid 10001 --gid metadata --no-create-home metadata
COPY radio_metadata/__init__.py radio_metadata/config.py radio_metadata/image_cache.py radio_metadata/receiver.py ./radio_metadata/
RUN mkdir -p /data /config && chown metadata:metadata /data /config
USER metadata
VOLUME ["/data", "/config"]
EXPOSE 8090
ENTRYPOINT ["python", "-m", "radio_metadata.receiver", "--config", "/config/receiver.json"]
