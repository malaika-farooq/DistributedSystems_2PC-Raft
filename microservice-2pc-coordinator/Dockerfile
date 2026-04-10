FROM python:3.11-slim
WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip
COPY microservice-2pc-coordinator/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY microservice-2pc-coordinator/coordinator.py ./coordinator.py

COPY proto /proto
RUN python -m grpc_tools.protoc -I /proto \
  --python_out=/app --grpc_python_out=/app \
  /proto/twopc.proto

RUN python -c "import twopc_pb2, twopc_pb2_grpc; print('twopc pb2 ok')"

EXPOSE 50060
CMD ["python", "coordinator.py"]
