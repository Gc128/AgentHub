from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CORE_AGENT_IDS = ["orchestrator", "code-agent", "review-agent", "preview-agent"]


@dataclass(frozen=True)
class TaskSpec:
    name: str
    prompt: str
    required_terms: tuple[str, ...]


TASKS: tuple[TaskSpec, ...] = (
    TaskSpec(
        name="counter",
        prompt=(
            "做一个计数器网页，支持增加、减少、归零，界面要清晰。"
            "必须包含 data-testid: counter-app, count-value, increment, decrement, reset。"
        ),
        required_terms=("counter-app", "count-value", "increment", "decrement", "reset"),
    ),
    TaskSpec(
        name="todo",
        prompt=(
            "做一个 Todo List 网页，支持新增、完成、删除、按全部/未完成/已完成筛选。"
            "必须包含 data-testid: todo-app, todo-input, add-todo, todo-list, filter-active。"
        ),
        required_terms=("todo-app", "todo-input", "add-todo", "todo-list", "filter-active"),
    ),
    TaskSpec(
        name="gradebook",
        prompt=(
            "做一个学生成绩管理网页，初始模拟 10 个学生，支持添加、删除、按成绩排序。"
            "必须包含 data-testid: grade-app, student-table, add-student, "
            "delete-student, sort-score。"
        ),
        required_terms=(
            "grade-app",
            "student-table",
            "add-student",
            "delete-student",
            "sort-score",
        ),
    ),
    TaskSpec(
        name="pomodoro",
        prompt=(
            "做一个番茄钟网页，支持开始、暂停、重置，并显示当前剩余时间。"
            "必须包含 data-testid: pomodoro-app, time-display, start-timer, "
            "pause-timer, reset-timer。"
        ),
        required_terms=(
            "pomodoro-app",
            "time-display",
            "start-timer",
            "pause-timer",
            "reset-timer",
        ),
    ),
    TaskSpec(
        name="expense-tracker",
        prompt=(
            "做一个记账网页，支持输入项目名和金额，添加支出列表，并自动计算总金额。"
            "必须包含 data-testid: expense-app, expense-form, expense-list, total-amount。"
        ),
        required_terms=("expense-app", "expense-form", "expense-list", "total-amount"),
    ),
    TaskSpec(
        name="palette",
        prompt=(
            "做一个配色板生成器网页，点击按钮生成 5 个随机颜色，并能复制颜色值。"
            "必须包含 data-testid: palette-app, generate-palette, palette-grid, copy-color。"
        ),
        required_terms=("palette-app", "generate-palette", "palette-grid", "copy-color"),
    ),
    TaskSpec(
        name="converter",
        prompt=(
            "做一个单位换算网页，包含长度和重量两个模式，输入数值后实时显示换算结果。"
            "必须包含 data-testid: converter-app, length-input, weight-input, converter-result。"
        ),
        required_terms=("converter-app", "length-input", "weight-input", "converter-result"),
    ),
    TaskSpec(
        name="quiz",
        prompt=(
            "做一个 5 题小测验网页，支持选择答案、下一题、最后展示分数。"
            "必须包含 data-testid: quiz-app, question-card, next-question, score-panel。"
        ),
        required_terms=("quiz-app", "question-card", "next-question", "score-panel"),
    ),
    TaskSpec(
        name="kanban",
        prompt=(
            "做一个简易看板网页，包含待办、进行中、已完成三列，支持新增卡片和移动卡片。"
            "必须包含 data-testid: kanban-app, add-card, todo-column, doing-column, done-column。"
        ),
        required_terms=("kanban-app", "add-card", "todo-column", "doing-column", "done-column"),
    ),
    TaskSpec(
        name="notes",
        prompt=(
            "做一个 Markdown 笔记网页，左侧编辑 Markdown，右侧实时预览，并支持保存当前笔记。"
            "必须包含 data-testid: notes-app, note-editor, preview-panel, save-note。"
        ),
        required_terms=("notes-app", "note-editor", "preview-panel", "save-note"),
    ),
)


class VerificationFailure(RuntimeError):
    pass


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="agenthub-real-tasks-") as workspace_root:
        _configure_real_runtime(Path(workspace_root))
        from fastapi.testclient import TestClient

        from agenthub.api.deps import reset_dependency_caches
        from agenthub.config import get_settings
        from agenthub.main import app

        get_settings.cache_clear()
        reset_dependency_caches()
        settings = get_settings()
        if settings.use_mock_agents:
            raise VerificationFailure("USE_MOCK_AGENTS must be false for real task verification.")
        if settings.agent_allow_fallbacks:
            raise VerificationFailure(
                "AGENT_ALLOW_FALLBACKS must be false for real task verification."
            )
        if not settings.openai_api_key:
            raise VerificationFailure("OPENAI_API_KEY is not configured; cannot call real LLM.")

        client = TestClient(app)
        runtime = _get_json(client, "/api/agents/runtime")
        if runtime.get("agent_mode") != "real":
            raise VerificationFailure(f"Expected real agent mode, got {runtime!r}")
        if not runtime.get("api_key_configured"):
            raise VerificationFailure("Runtime reports missing API key.")

        tasks = _selected_tasks()
        results = []
        for index, task in enumerate(tasks, start=1):
            print(f"[{index}/{len(tasks)}] running {task.name}", flush=True)
            results.append(_run_task(client, index, task))
            print(f"[{index}/{len(tasks)}] passed {task.name}", flush=True)
        print(json.dumps({"status": "passed", "tasks": results}, ensure_ascii=False, indent=2))


def _configure_real_runtime(workspace_root: Path) -> None:
    os.environ["PERSISTENCE_BACKEND"] = "memory"
    os.environ["USE_MOCK_AGENTS"] = "false"
    os.environ["AGENT_ALLOW_FALLBACKS"] = "false"
    os.environ["WORKSPACE_ROOT"] = str(workspace_root)


def _run_task(client: Any, index: int, task: TaskSpec) -> dict[str, Any]:
    conversation = _post_json(
        client,
        "/api/conversations",
        {
            "title": f"Real task {index}: {task.name}",
            "mode": "group",
            "agent_ids": CORE_AGENT_IDS,
        },
        expected_status=201,
    )
    workspace_id = _require_str(conversation, "workspace_id")
    prompt = _task_prompt(task)
    response = _post_json(
        client,
        f"/api/conversations/{conversation['id']}/messages/run",
        {"content": prompt, "sender_id": "user"},
        expected_status=201,
    )
    agent_messages = _require_list(response, "agent_messages")
    senders = [_require_str(message, "sender_id") for message in agent_messages]
    if senders[:4] != CORE_AGENT_IDS:
        raise VerificationFailure(
            f"{task.name}: unexpected agent order {senders!r}; "
            f"messages={_message_summaries(agent_messages)!r}"
        )
    fallback_excerpts = _fallback_marker_excerpts(response)
    if fallback_excerpts:
        raise VerificationFailure(
            f"{task.name}: response contains fallback marker: {fallback_excerpts!r}"
        )

    code_message = next(
        message for message in agent_messages if message.get("sender_id") == "code-agent"
    )
    artifacts = _require_list(code_message, "artifacts")
    code_artifacts = [artifact for artifact in artifacts if artifact.get("type") == "code"]
    diff_artifacts = [artifact for artifact in artifacts if artifact.get("type") == "diff"]
    if not code_artifacts:
        raise VerificationFailure(f"{task.name}: missing code artifact.")
    if not diff_artifacts:
        raise VerificationFailure(f"{task.name}: missing diff artifact.")

    apply_results: list[dict[str, Any]] = []
    for artifact in diff_artifacts:
        data = _require_dict(artifact, "data")
        diff_text = _require_str(data, "diff")
        if not diff_text.strip():
            raise VerificationFailure(f"{task.name}: empty diff in {artifact.get('id')!r}.")
        apply_results.append(
            _post_json(
                client,
                f"/api/workspaces/{workspace_id}/apply-diff",
                {"artifact_id": artifact["id"], "diff": diff_text},
            )
        )

    preview = _get_json(client, f"/api/workspaces/{workspace_id}/preview")
    entry_path = preview.get("entry_path") or apply_results[-1].get("entry_path")
    if not isinstance(entry_path, str) or not entry_path:
        raise VerificationFailure(f"{task.name}: preview entry path is missing.")
    if not str(preview.get("preview_url", "")).endswith(f"path={entry_path}"):
        raise VerificationFailure(f"{task.name}: preview_url does not target {entry_path!r}.")

    source = _get_json(
        client,
        f"/api/workspaces/{workspace_id}/files/content",
        params={"path": entry_path},
    )
    source_content = _require_str(source, "content")
    page_response = client.get(
        f"/api/workspaces/{workspace_id}/preview-page",
        params={"path": entry_path},
    )
    if page_response.status_code != 200:
        raise VerificationFailure(
            f"{task.name}: preview page returned {page_response.status_code}."
        )
    preview_content = _strip_injected_base(page_response.text)
    if preview_content.strip() != source_content.strip():
        raise VerificationFailure(f"{task.name}: preview page differs from workspace source.")

    _assert_required_terms(task, source_content + "\n" + preview_content)
    _assert_interactive(task, source_content)
    return {
        "name": task.name,
        "workspace_id": workspace_id,
        "entry_path": entry_path,
        "code_artifacts": len(code_artifacts),
        "diff_artifacts": len(diff_artifacts),
    }


def _task_prompt(task: TaskSpec) -> str:
    return (
        f"@Orchestrator {task.prompt}\n\n"
        "请生成一个单文件 `index.html`，CSS 和 JavaScript 都内嵌，不能依赖 CDN 或外部资源。"
        "页面必须能在浏览器中直接运行，按钮和输入必须有真实 DOM/状态更新逻辑。"
        "Code Agent 必须输出可应用的 code artifact 和 diff artifact。"
    )


def _selected_tasks() -> tuple[TaskSpec, ...]:
    selected = os.environ.get("AGENTHUB_VERIFY_TASKS", "").strip()
    if not selected:
        return TASKS
    names = {name.strip() for name in selected.split(",") if name.strip()}
    tasks = tuple(task for task in TASKS if task.name in names)
    if not tasks:
        raise VerificationFailure(f"No verification tasks matched {sorted(names)!r}.")
    return tasks


def _assert_required_terms(task: TaskSpec, content: str) -> None:
    normalized = content.lower()
    missing = [term for term in task.required_terms if term.lower() not in normalized]
    if missing:
        raise VerificationFailure(f"{task.name}: missing required terms {missing!r}.")


def _assert_interactive(task: TaskSpec, source: str) -> None:
    normalized = source.lower()
    if "<script" not in normalized:
        raise VerificationFailure(f"{task.name}: generated HTML has no script tag.")
    interaction_markers = (
        ".addeventlistener(",
        " onclick=",
        " onchange=",
        " oninput=",
        " onsubmit=",
        "setinterval(",
        "localstorage",
        "draggable",
    )
    if not any(marker in normalized for marker in interaction_markers):
        raise VerificationFailure(f"{task.name}: no interactive JavaScript marker found.")


def _fallback_marker_excerpts(payload: object) -> list[str]:
    excerpts: list[str] = []
    _collect_fallback_marker_excerpts(payload, "$", excerpts)
    return excerpts


def _collect_fallback_marker_excerpts(
    value: object,
    path: str,
    excerpts: list[str],
) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"fallback", "fallback_reason"}:
                excerpts.append(f"{path}.{key}={str(item)[:120]}")
                continue
            if key in {"id", "title", "source"} and isinstance(item, str):
                normalized = item.lower()
                if "fallback" in normalized or "mock agent" in normalized:
                    excerpts.append(f"{path}.{key}={item[:160]}")
                    continue
            _collect_fallback_marker_excerpts(item, f"{path}.{key}", excerpts)
        return

    if isinstance(value, list):
        for index, item in enumerate(value):
            _collect_fallback_marker_excerpts(item, f"{path}[{index}]", excerpts)
        return

    if isinstance(value, str):
        normalized = value.lower()
        for marker in ("兜底", "mock agent"):
            start = normalized.find(marker)
            if start >= 0:
                excerpts.append(f"{path}={value[max(0, start - 80) : start + 120]}")


def _message_summaries(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    summaries: list[dict[str, str]] = []
    for message in messages:
        content = str(message.get("content", ""))
        summaries.append(
            {
                "sender_id": str(message.get("sender_id", "")),
                "content": content.replace("\n", " ")[:240],
            }
        )
    return summaries


def _strip_injected_base(html: str) -> str:
    return re.sub(
        r'<base href="http://testserver/api/workspaces/[^"]+/preview-assets/[^"]*">',
        "",
        html,
        count=1,
    )


def _post_json(
    client: Any,
    path: str,
    payload: dict[str, Any],
    *,
    expected_status: int = 200,
) -> dict[str, Any]:
    response = client.post(path, json=payload)
    if response.status_code != expected_status:
        raise VerificationFailure(
            f"POST {path} returned {response.status_code}: {response.text[:800]}"
        )
    body = response.json()
    if not isinstance(body, dict):
        raise VerificationFailure(f"POST {path} did not return a JSON object.")
    return body


def _get_json(client: Any, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    response = client.get(path, params=params)
    if response.status_code != 200:
        raise VerificationFailure(
            f"GET {path} returned {response.status_code}: {response.text[:800]}"
        )
    body = response.json()
    if not isinstance(body, dict):
        raise VerificationFailure(f"GET {path} did not return a JSON object.")
    return body


def _require_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise VerificationFailure(f"Expected {key!r} to be an object.")
    return value


def _require_list(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise VerificationFailure(f"Expected {key!r} to be a list of objects.")
    return value


def _require_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise VerificationFailure(f"Expected {key!r} to be a non-empty string.")
    return value


if __name__ == "__main__":
    main()
