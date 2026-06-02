#!/usr/bin/env python3
"""Simple CLI todo list manager. Persists tasks to tasks.json."""

import json
import sys
from pathlib import Path

TASKS_FILE = Path("tasks.json")


def load_tasks() -> list[dict]:
    if not TASKS_FILE.exists():
        return []
    return json.loads(TASKS_FILE.read_text())


def save_tasks(tasks: list[dict]) -> None:
    TASKS_FILE.write_text(json.dumps(tasks, indent=2))


def add_task(title: str) -> None:
    tasks = load_tasks()
    next_id = max((t["id"] for t in tasks), default=0) + 1
    tasks.append({"id": next_id, "title": title, "done": False})
    save_tasks(tasks)
    print(f"Added task #{next_id}: {title}")


def list_tasks() -> None:
    tasks = load_tasks()
    if not tasks:
        print("No tasks.")
        return
    for task in tasks:
        status = "x" if task["done"] else " "
        print(f"  [{status}] #{task['id']} {task['title']}")


def complete_task(task_id: int) -> None:
    tasks = load_tasks()
    for task in tasks:
        if task["id"] == task_id:
            task["done"] = True
            save_tasks(tasks)
            print(f"Marked #{task_id} as done.")
            return
    print(f"Task #{task_id} not found.")


def delete_task(task_id: int) -> None:
    tasks = load_tasks()
    remaining = [t for t in tasks if t["id"] != task_id]
    if len(remaining) == len(tasks):
        print(f"Task #{task_id} not found.")
        return
    save_tasks(remaining)
    print(f"Deleted task #{task_id}.")


def print_usage() -> None:
    print("Usage:")
    print("  todo.py add <title>      Add a new task")
    print("  todo.py list             List all tasks")
    print("  todo.py done <id>        Mark a task as complete")
    print("  todo.py delete <id>      Delete a task")


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print_usage()
        return

    command = args[0]
    if command == "add" and len(args) >= 2:
        add_task(" ".join(args[1:]))
    elif command == "list":
        list_tasks()
    elif command == "done" and len(args) == 2:
        complete_task(int(args[1]))
    elif command == "delete" and len(args) == 2:
        delete_task(int(args[1]))
    else:
        print_usage()


if __name__ == "__main__":
    main()
