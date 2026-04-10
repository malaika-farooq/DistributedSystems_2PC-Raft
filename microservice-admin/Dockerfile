FROM python:3.11-slim
WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip
COPY microservice-admin/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY microservice-admin/admin_server.py ./admin_server.py

COPY proto /proto
RUN python -m grpc_tools.protoc -I /proto \
  --python_out=/app --grpc_python_out=/app \
  /proto/admin.proto

ENV DB_PATH=/data/products.db
EXPOSE 50055
CMD ["python", "admin_server.py"]