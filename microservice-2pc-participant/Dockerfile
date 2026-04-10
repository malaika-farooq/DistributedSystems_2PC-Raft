FROM python:3.11-slim
WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip
COPY microservice-2pc-participant/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY microservice-2pc-participant/participant.py ./participant.py

COPY proto /proto
RUN python -m grpc_tools.protoc -I /proto \
  --python_out=/app --grpc_python_out=/app \
  /proto/twopc.proto

RUN python -c "import twopc_pb2, twopc_pb2_grpc; print('participant pb2 ok')"

# Ports are configurable via VOTING_PORT and INTRA_PORT env vars
EXPOSE 50062 50063 50064 50065 50066 50067 50070 50071
CMD ["python", "participant.py"]
