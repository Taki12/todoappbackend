import os
from contextlib import asynccontextmanager

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── Database ─────────────────────────────────────────────────────────────────

DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "127.0.0.1"),
    "port":     int(os.getenv("DB_PORT", "5432")),
    "user":     os.getenv("DB_USER", "app"),
    "password": os.getenv("DB_PASSWORD", "01cab58d755fe2843e66d638f33ad953b3b2a792c103a139af0aef1095921acb"),
    "dbname":   os.getenv("DB_NAME", "app"),
}


def get_conn():
    return psycopg2.connect(**DB_CONFIG)


def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS todos (
                    id         SERIAL PRIMARY KEY,
                    title      TEXT NOT NULL,
                    completed  BOOLEAN NOT NULL DEFAULT false,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
        conn.commit()
    print("Database initialized — todos table ready.")


# ── App ───────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Schemas ───────────────────────────────────────────────────────────────────

class TodoCreate(BaseModel):
    title: str


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/api/todos")
def list_todos():
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, title, completed, created_at FROM todos ORDER BY created_at DESC"
            )
            return cur.fetchall()


@app.post("/api/todos", status_code=201)
def create_todo(body: TodoCreate):
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "INSERT INTO todos (title) VALUES (%s) RETURNING id, title, completed, created_at",
                (title,),
            )
            row = cur.fetchone()
        conn.commit()
    return row


@app.patch("/api/todos/{todo_id}")
def toggle_todo(todo_id: int):
    if todo_id <= 0:
        raise HTTPException(status_code=400, detail="invalid id")
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """UPDATE todos
                      SET completed = NOT completed
                    WHERE id = %s
                    RETURNING id, title, completed, created_at""",
                (todo_id,),
            )
            row = cur.fetchone()
        conn.commit()
    if row is None:
        raise HTTPException(status_code=404, detail="todo not found")
    return row


@app.delete("/api/todos/{todo_id}", status_code=204)
def delete_todo(todo_id: int):
    if todo_id <= 0:
        raise HTTPException(status_code=400, detail="invalid id")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM todos WHERE id = %s", (todo_id,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="todo not found")
        conn.commit()
