# v1rg0_prompt_injector.py
import json
import uuid
from datetime import datetime

class V1rg0PromptInjector:
    def __init__(self):
        self._current_task: dict | None = None

    def receive_task(self, raw_input: str):
        task_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().isoformat()
        try:
            task_data = json.loads(raw_input)
        except json.JSONDecodeError:
            task_data = {"prompt": raw_input}
        self._current_task = {"task_id": task_id, "timestamp": timestamp, "status": "received", "payload": task_data}

    def get_task(self) -> dict | None:
        task = self._current_task
        if task:
            self._current_task = None
            task['status'] = 'in_progress'
        return task

    def has_task(self) -> bool:
        return self._current_task is not None