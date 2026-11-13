# API · detect 워커 · detector 서버 공용 이미지. 빌드 컨텍스트 = 저장소 루트(model/ 포함).
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY service/pyproject.toml service/
COPY service/packages service/packages
COPY service/apps/api service/apps/api
COPY service/apps/worker service/apps/worker
COPY service/apps/detector_server service/apps/detector_server
RUN pip install "./service[api,worker,postgres]"
COPY service/alembic.ini service/alembic.ini
COPY service/migrations service/migrations
# AI 모델 패키지(model/)는 개발이 끝나 pyproject.toml이 생기면 자동으로 함께 설치된다.
COPY model /app/model
ARG INSTALL_MODEL=auto
RUN if [ -f /app/model/pyproject.toml ] && [ "$INSTALL_MODEL" != "no" ]; then pip install -e /app/model; \
    else echo "realstar_model 없음: 모델 개발 완료 후 이미지를 다시 빌드하세요"; fi
WORKDIR /app/service
