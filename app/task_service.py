import sqlite3

from app.schemas import Identity, SummaryResponse, TaskInput, TaskResponse
from app.task_repository import TaskRepository

HIGH_PRIORITY = "HIGH"
CLOSED_TASK_STATUSES = frozenset({"DONE", "ARCHIVED"})


def select_owner(identity: Identity) -> str:
    return identity.username


def task_from_row(row: sqlite3.Row) -> TaskResponse:
    return TaskResponse.model_validate(dict(row))


class TaskService:
    def __init__(self, repository: TaskRepository) -> None:
        self.repository = repository

    def list_tasks(self, identity: Identity) -> list[TaskResponse]:
        return [task_from_row(row) for row in self.repository.list_tasks(select_owner(identity))]

    def create_task(self, task: TaskInput, identity: Identity) -> TaskResponse:
        owned_task = task.model_copy(update={"owner": select_owner(identity)})
        return task_from_row(self.repository.create_task(owned_task))

    def summary(self, identity: Identity) -> SummaryResponse:
        owner = select_owner(identity)
        rows = self.repository.summary_rows(owner)
        response = SummaryResponse(owner=owner, total=len(rows))
        for row in rows:
            status = row["status"]
            response.by_status[status] = response.by_status.get(status, 0) + 1
            if row["priority"] == HIGH_PRIORITY and status not in CLOSED_TASK_STATUSES:
                response.high_priority_open += 1
        return response