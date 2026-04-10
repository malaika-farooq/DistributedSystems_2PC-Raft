FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir --upgrade pip

COPY python-webapp/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY python-webapp /app

COPY proto /proto
RUN python -m pip install --no-cache-dir grpcio-tools==1.62.2 protobuf==4.25.3 && \
    python -m grpc_tools.protoc -I /proto \
      --python_out=/app --grpc_python_out=/app \
      /proto/auth.proto /proto/productlisting.proto /proto/usercarts.proto /proto/orders.proto /proto/admin.proto /proto/twopc.proto

EXPOSE 5000
CMD ["python", "app.py"]
