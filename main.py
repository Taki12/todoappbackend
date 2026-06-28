import os
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── Database ─────────────────────────────────────────────────────────────────

DB_CONNINFO = (
    f"host={os.getenv('DB_HOST', 'svc-preprod-preprod-postgresql-npc8-postgres')} "
    f"port={os.getenv('DB_PORT', '5432')} "
    f"user={os.getenv('DB_USER', 'app')} "
    f"password={os.getenv('DB_PASSWORD', '01cab58d755fe2843e66d638f33ad953b3b2a792c103a139af0aef1095921acb')} "
    f"dbname={os.getenv('DB_NAME', 'app')}"
)


def get_conn():
    return psycopg.connect(DB_CONNINFO, row_factory=psycopg.rows.dict_row)


def init_db():
    with get_conn() as conn:
        conn.execute("""
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
        rows = conn.execute(
            "SELECT id, title, completed, created_at FROM todos ORDER BY created_at DESC"
        ).fetchall()
    return rows


@app.post("/api/todos", status_code=201)
def create_todo(body: TodoCreate):
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    with get_conn() as conn:
        row = conn.execute(
            "INSERT INTO todos (title) VALUES (%s) RETURNING id, title, completed, created_at",
            (title,),
        ).fetchone()
        conn.commit()
    return row


@app.patch("/api/todos/{todo_id}")
def toggle_todo(todo_id: int):
    if todo_id <= 0:
        raise HTTPException(status_code=400, detail="invalid id")
    with get_conn() as conn:
        row = conn.execute(
            """UPDATE todos
                  SET completed = NOT completed
                WHERE id = %s
                RETURNING id, title, completed, created_at""",
            (todo_id,),
        ).fetchone()
        conn.commit()
    if row is None:
        raise HTTPException(status_code=404, detail="todo not found")
    return row


@app.delete("/api/todos/{todo_id}", status_code=204)
def delete_todo(todo_id: int):
    if todo_id <= 0:
        raise HTTPException(status_code=400, detail="invalid id")
    with get_conn() as conn:
        result = conn.execute("DELETE FROM todos WHERE id = %s", (todo_id,))
        conn.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="todo not found")
