import os
import sqlite3
from concurrent import futures

import grpc

import productlisting_pb2
import productlisting_pb2_grpc

DB_PATH = os.environ.get("DB_PATH", "/data/products.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            price REAL NOT NULL,
            image_url TEXT NOT NULL,
            type TEXT NOT NULL,
            is_featured INTEGER NOT NULL DEFAULT 0
        )
    """)
    # Add type column if it doesn't exist (safe migration)
    cur.execute("PRAGMA table_info(items)")
    columns = [row["name"] for row in cur.fetchall()]

    if "type" not in columns:
        cur.execute("ALTER TABLE items ADD COLUMN type TEXT DEFAULT 'general'")
        conn.commit()

    # seed if empty (optional)
    cur.execute("SELECT COUNT(*) AS c FROM items")
    if cur.fetchone()["c"] == 0:
        cur.executemany(
            "INSERT INTO items (title, price, image_url, type, is_featured) VALUES (?, ?, ?, ?, ?)",
            [
                ("RTX 5090", 1599.99, "rtx5090.jpg", "GPU", 1),
                ("RTX 4090", 999.99, "rtx4090.jpg", "GPU", 1),
                ("RTX 2080", 499.99, "rtx2080.jpg", "GPU", 0),
                ("Dell 128GB RAM", 299.99, "dell128.jpg", "RAM", 1),
                ("Kingston 32GB RAM", 79.99, "kingston32gb.jpg", "RAM", 0),
                ("Crucial 64GB RAM", 149.99, "crucial64gb.jpg", "RAM", 0),
                ("Samsung 970 EVO SSD", 89.99, "samsung-970-evo.jpeg", "SSD", 0),
                ("SN7100 2TB SSD", 129.99, "sn7100_2tb.png", "SSD", 0),
                ("SanDisk 500GB SSD", 59.99, "sandisk500gb.jpg", "SSD", 0),
                ("Dell Server", 2499.99, "serverdell.jpg", "Server", 1),
                ("PowerEdge R540", 1899.99, "poweredger540.jpg", "Server", 0),
                ("Load Balancer", 799.99, "loadbalancer.jpg", "Network", 0),
            ],
        )
        conn.commit()

    conn.close()


class ProductListingService(productlisting_pb2_grpc.ProductListingServiceServicer):
    def ListItems(self, request, context):
        where = []
        params = []

        if request.featured_only:
            where.append("is_featured = ?")
            params.append(1)
        if request.type:
            where.append("type = ?")
            params.append(request.type)

        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        order_sql = ""
        if request.sort == "price_asc":
            order_sql = "ORDER BY price ASC"
        elif request.sort == "price_desc":
            order_sql = "ORDER BY price DESC"

        limit = request.limit if request.limit > 0 else 50
        offset = request.offset if request.offset >= 0 else 0

        sql = f"""
            SELECT id, title, price, image_url, type, is_featured
            FROM items
            {where_sql}
            {order_sql}
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        conn = get_conn()
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
        conn.close()

        resp = productlisting_pb2.ListItemsResponse()
        for r in rows:
            resp.items.append(productlisting_pb2.Item(
                id=int(r["id"]),
                title=r["title"],
                price=float(r["price"]),
                image_url=r["image_url"],
                type=r["type"],
                is_featured=bool(r["is_featured"]),
            ))
        return resp
    def GetItem(self, request, context):
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, title, price, image_url, is_featured FROM items WHERE id = ?",
            (request.id,)
        )
        r = cur.fetchone()
        conn.close()

        if not r:
            return productlisting_pb2.GetItemResponse(found=False)

        return productlisting_pb2.GetItemResponse(
            found=True,
            item=productlisting_pb2.Item(
                id=int(r["id"]),
                title=r["title"],
                price=float(r["price"]),
                image_url=r["image_url"],
                is_featured=bool(r["is_featured"]),
            )
        )


def serve():
    init_db()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    productlisting_pb2_grpc.add_ProductListingServiceServicer_to_server(ProductListingService(), server)
    server.add_insecure_port("0.0.0.0:50052")
    server.start()
    print("ProductListing gRPC server listening on 0.0.0.0:50052")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()