FROM python:3.11-slim
WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip

# Copy requirements from the correct folder
COPY microservice-userauth/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy proto and generate grpc files
COPY proto /proto
RUN python -m grpc_tools.protoc -I /proto \
    --python_out=/app --grpc_python_out=/app \
    /proto/auth.proto

# Copy service code from the correct folder
COPY microservice-userauth/auth_server.py ./auth_server.py

EXPOSE 50051
CMD ["python", "auth_server.py"]