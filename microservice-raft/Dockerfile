FROM python:3.11-slim
WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip
COPY microservice-raft/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY microservice-raft/raft_node.py ./raft_node.py

COPY proto /proto
RUN python -m grpc_tools.protoc -I /proto \
  --python_out=/app --grpc_python_out=/app \
  /proto/raft.proto

RUN python -c "import raft_pb2, raft_pb2_grpc; print('raft pb2 ok')"

EXPOSE 50070
CMD ["python", "raft_node.py"]
