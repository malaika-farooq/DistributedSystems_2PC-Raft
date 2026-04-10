import os
import sqlite3
from concurrent import futures

import grpc
from werkzeug.security import check_password_hash, generate_password_hash

import auth_pb2
import auth_pb2_grpc

DB_PATH = os.environ.get("DB_PATH", "/data/users.db")


def db_conn():
    # check_same_thread=False is safe here because we open a new connection per call anyway
    return sqlite3.connect(DB_PATH)


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def get_user(username: str):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, username, password_hash FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    return row  # (id, username, password_hash) or None


def create_user(username: str, password: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO users(username, password_hash) VALUES(?, ?)",
            (username, generate_password_hash(password)),
        )
        conn.commit()
        user_id = cur.lastrowid
        return True, str(user_id), "Registered"
    except sqlite3.IntegrityError:
        return False, "", "Username already exists"
    finally:
        conn.close()


class AuthService(auth_pb2_grpc.AuthServiceServicer):
    def CheckLogin(self, request, context):
        username = (request.username or "").strip()
        password = request.password or ""

        if not username or not password:
            return auth_pb2.CheckLoginResponse(ok=False, message="Missing username or password")

        row = get_user(username)
        if not row:
            return auth_pb2.CheckLoginResponse(ok=False, message="Invalid credentials")

        user_id, _, pw_hash = row
        if check_password_hash(pw_hash, password):
            return auth_pb2.CheckLoginResponse(ok=True, user_id=str(user_id), message="OK")

        return auth_pb2.CheckLoginResponse(ok=False, message="Invalid credentials")
    def Register(self, request, context):
        username = (request.username or "").strip()
        password = request.password or ""

        if len(username) < 3:
            return auth_pb2.RegisterResponse(ok=False, message="Username too short")
        if len(password) < 6:
            return auth_pb2.RegisterResponse(ok=False, message="Password too short")

        ok, user_id, msg = create_user(username, password)
        return auth_pb2.RegisterResponse(ok=ok, message=msg, user_id=user_id)


def seed_admin_if_needed():
    # Optional: seed a default user only if DB is empty and env vars provided
    admin_user = os.environ.get("SEED_USER")
    admin_pass = os.environ.get("SEED_PASS")
    if not admin_user or not admin_pass:
        return
    if get_user(admin_user) is None:
        created = create_user(admin_user, admin_pass)
        if created:
            print(f"Seeded user: {admin_user}")


def serve():
    init_db()
    seed_admin_if_needed()

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    auth_pb2_grpc.add_AuthServiceServicer_to_server(AuthService(), server)

    server.add_insecure_port("0.0.0.0:50051")
    server.start()
    print(f"Auth gRPC server listening on 0.0.0.0:50051 (DB: {DB_PATH})")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()