FROM python:3.11-slim
WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip
COPY microservice-usercarts/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY microservice-usercarts/cart_server.py ./cart_server.py

COPY proto /proto
RUN python -m grpc_tools.protoc -I /proto \
  --python_out=/app --grpc_python_out=/app \
  /proto/usercarts.proto

RUN python -c "import usercarts_pb2, usercarts_pb2_grpc; print('usercarts pb2 import ok')"

EXPOSE 50053
CMD ["python", "cart_server.py"]
