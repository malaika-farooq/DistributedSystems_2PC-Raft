import os
import sqlite3
from concurrent import futures

import grpc

import admin_pb2
import admin_pb2_grpc

DB_PATH = os.environ.get("DB_PATH", "/data/products.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_conn()
    cur = conn.cursor()

    # Ensure table exists with required columns
    cur.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            price REAL NOT NULL,
            image_url TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'general',
            is_featured INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.commit()

    # Safe migrations if you had an older schema
    cur.execute("PRAGMA table_info(items)")
    cols = {r["name"] for r in cur.fetchall()}

    if "type" not in cols:
        cur.execute("ALTER TABLE items ADD COLUMN type TEXT DEFAULT 'general'")
    if "is_featured" not in cols:
        cur.execute("ALTER TABLE items ADD COLUMN is_featured INTEGER DEFAULT 0")

    conn.commit()
    conn.close()


def row_to_item(r):
    return admin_pb2.Item(
        id=int(r["id"]),
        title=r["title"],
        price=float(r["price"]),
        image_url=r["image_url"],
        type=r["type"],
        is_featured=bool(r["is_featured"]),
    )


class AdminService(admin_pb2_grpc.AdminServiceServicer):
    def ListItems(self, request, context):
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT id, title, price, image_url, type, is_featured FROM items ORDER BY id DESC")
        rows = cur.fetchall()
        conn.close()

        resp = admin_pb2.ListItemsResponse()
        for r in rows:
            resp.items.append(row_to_item(r))
        return resp

    def CreateItem(self, request, context):
        title = (request.title or "").strip()
        image_url = (request.image_url or "").strip()
        type_ = (request.type or "").strip() or "general"
        price = float(request.price)
        featured = 1 if request.is_featured else 0

        if not title or not image_url or price < 0:
            return admin_pb2.ItemResponse(ok=False, message="Invalid fields")

        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO items(title, price, image_url, type, is_featured) VALUES(?,?,?,?,?)",
            (title, price, image_url, type_, featured),
        )
        new_id = cur.lastrowid
        conn.commit()

        cur.execute("SELECT id, title, price, image_url, type, is_featured FROM items WHERE id=?", (new_id,))
        row = cur.fetchone()
        conn.close()

        return admin_pb2.ItemResponse(ok=True, message="Created", item=row_to_item(row))

    def UpdateItem(self, request, context):
        if request.id <= 0:
            return admin_pb2.ItemResponse(ok=False, message="Invalid id")

        title = (request.title or "").strip()
        image_url = (request.image_url or "").strip()
        type_ = (request.type or "").strip() or "general"
        price = float(request.price)
        featured = 1 if request.is_featured else 0

        if not title or not image_url or price < 0:
            return admin_pb2.ItemResponse(ok=False, message="Invalid fields")

        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "UPDATE items SET title=?, price=?, image_url=?, type=?, is_featured=? WHERE id=?",
            (title, price, image_url, type_, featured, request.id),
        )
        conn.commit()

        if cur.rowcount == 0:
            conn.close()
            return admin_pb2.ItemResponse(ok=False, message="Not found")

        cur.execute("SELECT id, title, price, image_url, type, is_featured FROM items WHERE id=?", (request.id,))
        row = cur.fetchone()
        conn.close()

        return admin_pb2.ItemResponse(ok=True, message="Updated", item=row_to_item(row))

    def DeleteItem(self, request, context):
        if request.id <= 0:
            return admin_pb2.DeleteItemResponse(ok=False, message="Invalid id")

        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM items WHERE id=?", (request.id,))
        conn.commit()
        deleted = cur.rowcount
        conn.close()

        if deleted == 0:
            return admin_pb2.DeleteItemResponse(ok=False, message="Not found")
        return admin_pb2.DeleteItemResponse(ok=True, message="Deleted")


def serve():
    init_db()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    admin_pb2_grpc.add_AdminServiceServicer_to_server(AdminService(), server)
    server.add_insecure_port("0.0.0.0:50055")
    server.start()
    print("Admin gRPC server listening on 0.0.0.0:50055")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()