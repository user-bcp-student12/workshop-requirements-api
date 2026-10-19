import sqlite3
from _thread import RLock

from app.schemas import TaskInput

TASK_SELECT = "SELECT id,title,description,status,owner,priority,created_at FROM tasks"
LIST_TASKS_SQL = TASK_SELECT + " WHERE owner = ? ORDER BY id"
GET_TASK_SQL = TASK_SELECT + " WHERE id = ?"
SUMMARY_ROWS_SQL = "SELECT status,priority FROM tasks WHERE owner = ?"
INSERT_TASK_SQL = (
    "INSERT INTO tasks(title,description,status,owner,priority,created_at) "
    "VALUES (?, ?, ?, ?, ?, datetime('now'))"
)
MISSING_INSERTED_TASK = "Inserted task could not be retrieved"


class TaskRepository:
    def __init__(self, connection: sqlite3.Connection, connection_lock: RLock) -> None:
        self.connection = connection
        self.connection_lock = connection_lock

    def list_tasks(self, owner: str) -> list[sqlite3.Row]:
        with self.connection_lock:
            return self.connection.execute(LIST_TASKS_SQL, (owner,)).fetchall()

    def get_task(self, task_id: int) -> sqlite3.Row | None:
        with self.connection_lock:
            return self.connection.execute(GET_TASK_SQL, (task_id,)).fetchone()

    def summary_rows(self, owner: str) -> list[sqlite3.Row]:
        with self.connection_lock:
            return self.connection.execute(SUMMARY_ROWS_SQL, (owner,)).fetchall()

    def create_task(self, task: TaskInput) -> sqlite3.Row:
        with self.connection_lock:
            try:
                cursor = self.connection.execute(
                    INSERT_TASK_SQL, (task.title, task.description, task.status, task.owner, task.priority)
                )
                row = self.get_task(cursor.lastrowid)
                if row is None:
                    raise sqlite3.DatabaseError(MISSING_INSERTED_TASK)
                self.connection.commit()
                return row
            except sqlite3.Error:
                self.connection.rollback()
                raise