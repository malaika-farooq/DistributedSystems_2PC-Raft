import os
import sqlite3
from concurrent import futures

import grpc

import usercarts_pb2
import usercarts_pb2_grpc

DB_PATH = os.environ.get("DB_PATH", "/data/carts.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cart_items (
            user_id TEXT NOT NULL,
            item_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            PRIMARY KEY (user_id, item_id)
        )
    """)
    conn.commit()
    conn.close()


class UserCartsService(usercarts_pb2_grpc.UserCartsServiceServicer):
    def AddToCart(self, request, context):
        user_id = (request.user_id or "").strip()
        item_id = request.item_id
        qty     = request.quantity

        if not user_id:
            return usercarts_pb2.AddToCartResponse(ok=False, message="Missing user_id")
        if item_id <= 0:
            return usercarts_pb2.AddToCartResponse(ok=False, message="Invalid item_id")
        if qty <= 0 or qty > 99:
            return usercarts_pb2.AddToCartResponse(ok=False, message="Invalid quantity")

        conn = get_conn()
        cur  = conn.cursor()
        cur.execute("SELECT quantity FROM cart_items WHERE user_id=? AND item_id=?", (user_id, item_id))
        row = cur.fetchone()
        if row:
            new_qty = int(row["quantity"]) + qty
            cur.execute("UPDATE cart_items SET quantity=? WHERE user_id=? AND item_id=?", (new_qty, user_id, item_id))
        else:
            cur.execute("INSERT INTO cart_items(user_id, item_id, quantity) VALUES(?,?,?)", (user_id, item_id, qty))
        conn.commit()
        conn.close()
        return usercarts_pb2.AddToCartResponse(ok=True, message="Added")

    def GetCart(self, request, context):
        user_id = (request.user_id or "").strip()
        resp = usercarts_pb2.GetCartResponse()
        if not user_id:
            return resp
        conn = get_conn()
        cur  = conn.cursor()
        cur.execute("SELECT item_id, quantity FROM cart_items WHERE user_id=? ORDER BY item_id", (user_id,))
        for r in cur.fetchall():
            resp.items.append(usercarts_pb2.CartItem(item_id=r["item_id"], quantity=r["quantity"]))
        conn.close()
        return resp

    def ClearCart(self, request, context):
        user_id = (request.user_id or "").strip()
        if not user_id:
            return usercarts_pb2.ClearCartResponse(ok=False, message="Missing user_id")
        conn = get_conn()
        conn.execute("DELETE FROM cart_items WHERE user_id=?", (user_id,))
        conn.commit()
        conn.close()
        return usercarts_pb2.ClearCartResponse(ok=True, message="Cart cleared")

    def RemoveFromCart(self, request, context):
        user_id = (request.user_id or "").strip()
        item_id = request.item_id
        if not user_id or item_id <= 0:
            return usercarts_pb2.RemoveFromCartResponse(ok=False, message="Invalid input", new_quantity=0)

        conn = get_conn()
        cur  = conn.cursor()
        cur.execute("SELECT quantity FROM cart_items WHERE user_id=? AND item_id=?", (user_id, item_id))
        row = cur.fetchone()
        if not row:
            conn.close()
            return usercarts_pb2.RemoveFromCartResponse(ok=False, message="Item not in cart", new_quantity=0)

        if request.remove_all:
            cur.execute("DELETE FROM cart_items WHERE user_id=? AND item_id=?", (user_id, item_id))
            conn.commit()
            conn.close()
            return usercarts_pb2.RemoveFromCartResponse(ok=True, message="Removed", new_quantity=0)

        new_qty = int(row["quantity"]) - request.quantity
        if new_qty <= 0:
            cur.execute("DELETE FROM cart_items WHERE user_id=? AND item_id=?", (user_id, item_id))
            conn.commit()
            conn.close()
            return usercarts_pb2.RemoveFromCartResponse(ok=True, message="Removed", new_quantity=0)

        cur.execute("UPDATE cart_items SET quantity=? WHERE user_id=? AND item_id=?", (new_qty, user_id, item_id))
        conn.commit()
        conn.close()
        return usercarts_pb2.RemoveFromCartResponse(ok=True, message="Updated", new_quantity=new_qty)


def serve():
    init_db()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    usercarts_pb2_grpc.add_UserCartsServiceServicer_to_server(UserCartsService(), server)
    server.add_insecure_port("0.0.0.0:50053")
    server.start()
    print("UserCartsService listening on :50053", flush=True)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
