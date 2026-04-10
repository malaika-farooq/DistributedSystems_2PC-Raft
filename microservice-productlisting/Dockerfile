FROM python:3.11-slim
WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip

COPY microservice-productlisting/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the server code
COPY microservice-productlisting/product_server.py ./product_server.py

# Copy protos and generate code
COPY proto /proto
RUN python -m grpc_tools.protoc -I /proto \
  --python_out=/app --grpc_python_out=/app \
  /proto/productlisting.proto

# Sanity check at build time (so it fails early if missing)
RUN ls -la /app && python -c "import productlisting_pb2, productlisting_pb2_grpc; print('pb2 import ok')"

ENV DB_PATH=/data/products.db
EXPOSE 50052
CMD ["python", "product_server.py"]