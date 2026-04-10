FROM python:3.11-slim
WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip
COPY microservice-orders/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY microservice-orders/order_server.py ./order_server.py

COPY proto /proto
RUN python -m grpc_tools.protoc -I /proto \
  --python_out=/app --grpc_python_out=/app \
  /proto/orders.proto /proto/usercarts.proto /proto/twopc.proto

RUN python -c "import orders_pb2, orders_pb2_grpc, usercarts_pb2, usercarts_pb2_grpc, twopc_pb2, twopc_pb2_grpc; print('pb2 ok')"

EXPOSE 50054 50056 50057
CMD ["python", "order_server.py"]
