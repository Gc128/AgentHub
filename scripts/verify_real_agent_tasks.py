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
        name="student-search",
        prompt=(
            "做一个学生成绩查询网页，初始模拟 10 个学生。支持按姓名模糊查询，"
            "也支持按最低分和最高分筛选成绩。"
            "必须包含 data-testid: grade-search-app, student-search-input, "
            "score-min-input, score-max-input, search-results。"
        ),
        required_terms=(
            "grade-search-app",
            "student-search-input",
            "score-min-input",
            "score-max-input",
            "search-results",
        ),
    ),
    TaskSpec(
        name="contact-form",
        prompt=(
            "做一个联系表单网页，用户输入姓名、邮箱和消息，提交后在页面中显示确认卡片，"
            "并清空表单。"
            "必须包含 data-testid: contact-app, contact-form, "
            "submit-contact, confirmation-panel。"
        ),
        required_terms=(
            "contact-app",
            "contact-form",
            "submit-contact",
            "confirmation-panel",
        ),
    ),
    TaskSpec(
        name="password-generator",
        prompt=(
            "做一个密码生成器网页，支持选择长度、是否包含数字和符号，点击后生成密码，"
            "并显示强度提示。"
            "必须包含 data-testid: password-app, password-length, include-number, "
            "include-symbol, generate-password, password-output。"
        ),
        required_terms=(
            "password-app",
            "password-length",
            "include-number",
            "include-symbol",
            "generate-password",
            "password-output",
        ),
    ),
    TaskSpec(
        name="water-tracker",
        prompt=(
            "做一个饮水记录网页，显示今日已喝杯数，支持点击添加一杯和重置今日记录。"
            "必须包含 data-testid: water-app, glass-count, add-glass, reset-water。"
        ),
        required_terms=(
            "water-app",
            "glass-count",
            "add-glass",
            "reset-water",
        ),
    ),
    TaskSpec(
        name="inventory-manager",
        prompt=(
            "做一个库存管理网页，支持添加商品名称、库存数量、分类，库存低于 5 时显示低库存提示。"
            "必须包含 data-testid: inventory-app, product-form, inventory-list, "
            "stock-warning, add-product。"
        ),
        required_terms=(
            "inventory-app",
            "product-form",
            "inventory-list",
            "stock-warning",
            "add-product",
        ),
    ),
    TaskSpec(
        name="shopping-cart",
        prompt=(
            "做一个购物车网页，展示三种商品，支持加入购物车、调整数量、移除商品并计算总价。"
            "必须包含 data-testid: cart-app, product-list, add-to-cart, "
            "cart-items, cart-total。"
        ),
        required_terms=("cart-app", "product-list", "add-to-cart", "cart-items", "cart-total"),
    ),
    TaskSpec(
        name="gallery-filter",
        prompt=(
            "做一个图片画廊筛选网页，用彩色占位卡片模拟图片，支持按分类按钮筛选，"
            "并显示当前分类。"
            "必须包含 data-testid: gallery-app, category-filter, gallery-grid, "
            "active-category。"
        ),
        required_terms=("gallery-app", "category-filter", "gallery-grid", "active-category"),
    ),
    TaskSpec(
        name="bmi-calculator",
        prompt=(
            "做一个 BMI 计算器网页，输入身高和体重后计算 BMI，并根据结果显示健康区间提示。"
            "必须包含 data-testid: bmi-app, height-input, weight-input, "
            "calculate-bmi, bmi-result。"
        ),
        required_terms=(
            "bmi-app",
            "height-input",
            "weight-input",
            "calculate-bmi",
            "bmi-result",
        ),
    ),
    TaskSpec(
        name="agenda-builder",
        prompt=(
            "做一个会议议程编辑网页，可以添加议题、负责人和预计分钟数，并自动汇总总时长。"
            "必须包含 data-testid: agenda-app, topic-form, agenda-list, "
            "agenda-total, add-topic。"
        ),
        required_terms=("agenda-app", "topic-form", "agenda-list", "agenda-total", "add-topic"),
    ),
    TaskSpec(
        name="flashcard-trainer",
        prompt=(
            "做一个单词卡片练习网页，内置 5 张卡片，支持翻面、下一张，并统计已练习数量。"
            "必须包含 data-testid: flashcard-app, flashcard-card, flip-card, "
            "next-card, practice-count。"
        ),
        required_terms=(
            "flashcard-app",
            "flashcard-card",
            "flip-card",
            "next-card",
            "practice-count",
        ),
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
    _assert_no_raw_json_agent_messages(task, agent_messages)

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


def _assert_no_raw_json_agent_messages(
    task: TaskSpec,
    agent_messages: list[dict[str, Any]],
) -> None:
    for message in agent_messages:
        sender = str(message.get("sender_id", "unknown"))
        content = str(message.get("content", "")).strip()
        compact = content.replace("\n", " ")
        raw_json_markers = (
            compact.startswith('{"agent_id"'),
            '"agent_id"' in compact and '"artifacts"' in compact and "\\n" in compact,
            '"content"' in compact and '\\"' in compact and "<html" in compact.lower(),
        )
        if any(raw_json_markers):
            raise VerificationFailure(
                f"{task.name}: {sender} exposed raw structured JSON: {compact[:240]}"
            )


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
