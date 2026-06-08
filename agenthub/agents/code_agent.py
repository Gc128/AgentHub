import hashlib
import re
from pathlib import Path

from agenthub.agents.base import AgentAdapter
from agenthub.agents.real_agent import RealAgentSchemaError
from agenthub.core.errors import AgentExecutionError
from agenthub.schemas.agent import AgentRunInput, AgentRunResult
from agenthub.schemas.artifact import Artifact
from agenthub.workspace.diff import create_unified_diff
from agenthub.workspace.manager import WorkspacePathError, resolve_workspace_path


class CodeAgent:
    id = "code-agent"
    name = "Code Agent"
    capabilities = ["code", "diff", "file-generation"]

    def __init__(
        self,
        llm: AgentAdapter,
        workspace_root: Path | None = None,
        *,
        allow_fallbacks: bool = False,
    ) -> None:
        self._llm = llm
        self._workspace_root = workspace_root or Path("./workspaces")
        self._allow_fallbacks = allow_fallbacks

    async def run(self, input_data: AgentRunInput) -> AgentRunResult:
        try:
            result = await self._llm.run(
                input_data.model_copy(
                    update={
                        "context": {
                            **input_data.context,
                            "agent_id": self.id,
                            "agent_role": "code",
                        }
                    }
                )
            )
        except RealAgentSchemaError as exc:
            if not self._fallbacks_allowed(input_data):
                raise AgentExecutionError(
                    "Code Agent model output could not be parsed after repair."
                ) from exc
            fallback = _build_code_fallback_result(
                input_data,
                reason="未能从模型结果中提取可应用代码，已生成最小兜底版本。",
            )
            if fallback is None:
                raise AgentExecutionError(
                    "Code Agent structured output could not be parsed."
                ) from exc
            result = fallback
        result = result.model_copy(update={"agent_id": self.id})
        result = await self._ensure_todo_artifact_is_interactive(result, input_data)
        artifact_types = {artifact.type for artifact in result.artifacts}
        if not artifact_types and not _looks_like_code_task(input_data.user_message):
            return result
        result = _ensure_content_includes_code_artifacts(result)
        if "code" in artifact_types:
            diff_artifacts = _build_missing_diff_artifacts(
                result.artifacts,
                workspace_id=input_data.workspace_id,
                workspace_root=self._workspace_root,
            )
            if diff_artifacts:
                result = result.model_copy(
                    update={"artifacts": [*result.artifacts, *diff_artifacts]}
                )
                artifact_types = {artifact.type for artifact in result.artifacts}
        result = result.model_copy(
            update={"artifacts": _normalize_diff_artifact_ids(result.artifacts)}
        )
        artifact_types = {artifact.type for artifact in result.artifacts}
        if not {"code", "diff"}.issubset(artifact_types):
            raise AgentExecutionError("Code Agent must return code and diff artifacts.")
        return result

    async def _ensure_todo_artifact_is_interactive(
        self,
        result: AgentRunResult,
        input_data: AgentRunInput,
    ) -> AgentRunResult:
        if not _looks_like_todo_task(input_data):
            return result

        code_artifacts = [artifact for artifact in result.artifacts if artifact.type == "code"]
        if code_artifacts and any(
            _artifact_has_interactive_todo_behavior(artifact) for artifact in code_artifacts
        ):
            return result

        repaired = await self._repair_todo_interaction(result, input_data)
        if repaired is not None:
            repaired = repaired.model_copy(update={"agent_id": self.id})
            repaired_code_artifacts = [
                artifact for artifact in repaired.artifacts if artifact.type == "code"
            ]
            if repaired_code_artifacts and any(
                _artifact_has_interactive_todo_behavior(artifact)
                for artifact in repaired_code_artifacts
            ):
                return repaired

        if code_artifacts:
            return result.model_copy(
                update={
                    "content": result.content.rstrip()
                    + "\n\n"
                    + "Todo 交互校验未通过：模型输出中没有发现表单提交、按钮事件或状态更新逻辑。"
                    + "系统已尝试基于原代码修复，但结果仍不可用，因此保留原始模型产物，"
                    + "请让 Code Agent 继续补充交互逻辑。"
                }
            )

        fallback = _build_code_fallback_result(
            input_data,
            reason="模型没有返回可应用的代码产物，已生成最小兜底版本。",
        )
        if not self._fallbacks_allowed(input_data):
            return result
        if fallback is None:
            return result
        return fallback

    def _fallbacks_allowed(self, input_data: AgentRunInput) -> bool:
        return self._allow_fallbacks or input_data.context.get("allow_agent_fallbacks") is True

    async def _repair_todo_interaction(
        self,
        result: AgentRunResult,
        input_data: AgentRunInput,
    ) -> AgentRunResult | None:
        try:
            return await self._llm.run(
                input_data.model_copy(
                    update={
                        "user_message": _todo_repair_prompt(input_data),
                        "context": {
                            **input_data.context,
                            "agent_id": self.id,
                            "agent_role": "code",
                            "repair_reason": "todo_interaction_missing",
                            "original_result": result.model_dump(mode="json"),
                            "user_request": input_data.context.get(
                                "user_request", input_data.user_message
                            ),
                        },
                    }
                )
            )
        except Exception:
            return None


def _looks_like_code_task(user_message: str) -> bool:
    normalized = user_message.lower()
    normalized = normalized.replace("@codeagent", "")
    code_keywords = {
        "code",
        "component",
        "page",
        "webpage",
        "html",
        "css",
        "javascript",
        "typescript",
        "react",
        "todo",
        "list",
        "app",
        "写",
        "实现",
        "生成",
        "页面",
        "网页",
        "组件",
        "代码",
        "开发",
        "功能",
        "待办",
        "清单",
        "修复",
    }
    return any(keyword in normalized for keyword in code_keywords)


def _looks_like_todo_task(input_data: AgentRunInput) -> bool:
    normalized = _combined_request_text(input_data)
    if _looks_like_grade_table_task(input_data):
        return False
    return any(keyword in normalized for keyword in {"todo", "to do", "待办", "清单"})


def _looks_like_grade_table_task(input_data: AgentRunInput) -> bool:
    normalized = _combined_request_text(input_data)
    has_student = any(keyword in normalized for keyword in {"学生", "student", "班级"})
    has_grade = any(keyword in normalized for keyword in {"成绩", "分数", "score", "grade"})
    return has_student and has_grade


def _combined_request_text(input_data: AgentRunInput) -> str:
    context_values = [
        input_data.user_message,
        str(input_data.context.get("user_request", "")),
        str(input_data.context.get("instruction", "")),
    ]
    return " ".join(context_values).lower()


def _artifact_has_interactive_todo_behavior(artifact: Artifact) -> bool:
    content = str(artifact.data.get("content", "")).lower()
    if not content:
        return False
    has_todo_language = "todo" in content or "待办" in content
    has_interaction = any(
        marker in content
        for marker in (
            "addeventlistener",
            "onclick",
            "onsubmit",
            "usestate",
            "setstate",
            "document.queryselector",
        )
    )
    return has_todo_language and has_interaction


def _todo_repair_prompt(input_data: AgentRunInput) -> str:
    user_request = input_data.context.get("user_request", input_data.user_message)
    return (
        "修复 Todo 页面代码的交互能力。必须基于 context.original_result 中的原始代码修改，"
        "保留用户需求中的布局、字段、样式、文案和功能差异，不要改成通用模板。"
        "确保添加按钮或表单提交会真实新增待办项，并保留删除、完成、筛选、优先级、"
        "截止日期等用户明确要求的功能。返回合法 AgentRunResult JSON，包含完整 code artifact。"
        f"\n\n用户原始需求：{user_request}"
    )


def _build_code_fallback_result(
    input_data: AgentRunInput,
    *,
    reason: str,
) -> AgentRunResult | None:
    if _looks_like_grade_table_task(input_data):
        return _build_grade_table_fallback_result(input_data, reason=reason)
    if _looks_like_todo_task(input_data):
        return _build_todo_fallback_result(input_data, reason=reason)
    return None


def _build_grade_table_fallback_result(
    input_data: AgentRunInput,
    *,
    reason: str,
) -> AgentRunResult:
    content = _grade_table_html()
    return AgentRunResult(
        agent_id="code-agent",
        content=(
            f"{reason} 该 fallback 按当前需求生成学生成绩管理页面，包含 10 条模拟数据、"
            "新增、删除和按成绩排序功能。\n\n"
            f'```html filename="index.html"\n{content.rstrip()}\n```'
        ),
        artifacts=[
            Artifact(
                id="artifact-code-agent-grade-table-fallback",
                type="code",
                title="Student grade manager fallback",
                data={
                    "filename": "index.html",
                    "language": "html",
                    "content": content,
                    "workspace_id": input_data.workspace_id,
                    "fallback": True,
                    "fallback_reason": reason,
                    "features": {
                        "mock_students": 10,
                        "add": True,
                        "delete": True,
                        "sort_by_score": True,
                    },
                },
            )
        ],
        next_actions=["review-agent", "preview-agent"],
    )


def _build_todo_fallback_result(
    input_data: AgentRunInput,
    *,
    reason: str,
) -> AgentRunResult:
    features = _todo_features(input_data)
    content = _interactive_todo_html(features)
    title = _todo_title(features)
    return AgentRunResult(
        agent_id="code-agent",
        content=(
            f"{reason} 这个 fallback 会根据当前需求启用对应的 Todo 字段和交互。\n\n"
            f'```html filename="index.html"\n{content.rstrip()}\n```'
        ),
        artifacts=[
            Artifact(
                id=f"artifact-code-agent-todo-fallback-{_todo_feature_slug(features)}",
                type="code",
                title=title,
                data={
                    "filename": "index.html",
                    "language": "html",
                    "content": content,
                    "workspace_id": input_data.workspace_id,
                    "fallback": True,
                    "fallback_reason": reason,
                    "features": features,
                },
            )
        ],
        next_actions=["review-agent", "preview-agent"],
    )


def _todo_features(input_data: AgentRunInput) -> dict[str, bool]:
    context_values = [
        input_data.user_message,
        str(input_data.context.get("user_request", "")),
        str(input_data.context.get("instruction", "")),
    ]
    normalized = " ".join(context_values).lower()
    return {
        "priority": any(keyword in normalized for keyword in {"priority", "优先级", "重要"}),
        "due_date": any(keyword in normalized for keyword in {"due", "deadline", "截止", "日期"}),
        "filter": any(keyword in normalized for keyword in {"filter", "筛选", "过滤", "分类"}),
    }


def _grade_table_html() -> str:
    return """<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>学生成绩管理</title>
    <style>
      * {
        box-sizing: border-box;
      }

      body {
        min-height: 100vh;
        margin: 0;
        background: #f5f3ee;
        color: #17211f;
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
          "Segoe UI", sans-serif;
        padding: 24px;
      }

      main {
        width: min(920px, 100%);
        margin: 0 auto;
        border: 1px solid #ddd8cd;
        border-radius: 8px;
        background: #fffdf8;
        box-shadow: 0 16px 40px rgb(68 58 42 / 10%);
        padding: 24px;
      }

      header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        margin-bottom: 18px;
      }

      h1 {
        margin: 0;
        font-size: 28px;
      }

      form {
        display: grid;
        grid-template-columns: minmax(0, 1fr) minmax(120px, 160px) auto;
        gap: 10px;
        margin-bottom: 18px;
      }

      input,
      button {
        min-height: 40px;
        border-radius: 8px;
        font: inherit;
      }

      input {
        min-width: 0;
        border: 1px solid #cfc8bc;
        background: #ffffff;
        padding: 0 12px;
      }

      button {
        border: 0;
        background: #235b54;
        color: #ffffff;
        cursor: pointer;
        font-weight: 700;
        padding: 0 14px;
      }

      button:hover {
        background: #1d4b45;
      }

      .danger {
        background: #7b342f;
      }

      table {
        width: 100%;
        border-collapse: collapse;
        overflow: hidden;
        border-radius: 8px;
      }

      th,
      td {
        border-bottom: 1px solid #e7e0d7;
        padding: 12px;
        text-align: left;
      }

      th {
        background: #f0ece5;
      }

      tr:last-child td {
        border-bottom: 0;
      }

      .score {
        font-weight: 800;
      }
    </style>
  </head>
  <body>
    <main>
      <header>
        <h1>学生成绩管理</h1>
        <button id="sort-score" type="button">按成绩排序</button>
      </header>

      <form id="student-form">
        <input id="student-name" type="text" placeholder="学生姓名" autocomplete="off" />
        <input id="student-score" type="number" min="0" max="100" placeholder="成绩" />
        <button type="submit">添加学生</button>
      </form>

      <table>
        <thead>
          <tr>
            <th>序号</th>
            <th>姓名</th>
            <th>成绩</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody id="student-rows"></tbody>
      </table>
    </main>

    <script>
      const students = [
        { id: crypto.randomUUID(), name: "学生 1", score: 92 },
        { id: crypto.randomUUID(), name: "学生 2", score: 76 },
        { id: crypto.randomUUID(), name: "学生 3", score: 88 },
        { id: crypto.randomUUID(), name: "学生 4", score: 64 },
        { id: crypto.randomUUID(), name: "学生 5", score: 95 },
        { id: crypto.randomUUID(), name: "学生 6", score: 81 },
        { id: crypto.randomUUID(), name: "学生 7", score: 73 },
        { id: crypto.randomUUID(), name: "学生 8", score: 99 },
        { id: crypto.randomUUID(), name: "学生 9", score: 68 },
        { id: crypto.randomUUID(), name: "学生 10", score: 85 },
      ];

      const form = document.querySelector("#student-form");
      const nameInput = document.querySelector("#student-name");
      const scoreInput = document.querySelector("#student-score");
      const rows = document.querySelector("#student-rows");
      const sortButton = document.querySelector("#sort-score");
      let sortDescending = true;

      function renderStudents() {
        rows.innerHTML = "";
        students.forEach((student, index) => {
          const row = document.createElement("tr");
          row.innerHTML = `
            <td>${index + 1}</td>
            <td>${student.name}</td>
            <td class="score">${student.score}</td>
            <td><button class="danger" type="button">删除</button></td>
          `;
          row.querySelector("button").addEventListener("click", () => {
            const targetIndex = students.findIndex((item) => item.id === student.id);
            if (targetIndex >= 0) {
              students.splice(targetIndex, 1);
              renderStudents();
            }
          });
          rows.append(row);
        });
      }

      form.addEventListener("submit", (event) => {
        event.preventDefault();
        const name = nameInput.value.trim();
        const score = Number(scoreInput.value);
        if (!name || Number.isNaN(score) || score < 0 || score > 100) {
          nameInput.focus();
          return;
        }
        students.push({ id: crypto.randomUUID(), name, score });
        nameInput.value = "";
        scoreInput.value = "";
        renderStudents();
      });

      sortButton.addEventListener("click", () => {
        students.sort((left, right) =>
          sortDescending ? right.score - left.score : left.score - right.score
        );
        sortDescending = !sortDescending;
        sortButton.textContent = sortDescending ? "按成绩排序" : "恢复升序";
        renderStudents();
      });

      renderStudents();
    </script>
  </body>
</html>
"""


def _todo_title(features: dict[str, bool]) -> str:
    enabled = [
        label
        for key, label in {
            "priority": "Priority",
            "due_date": "Due Date",
            "filter": "Filter",
        }.items()
        if features.get(key)
    ]
    suffix = " + ".join(enabled) if enabled else "Minimal"
    return f"{suffix} Todo List fallback"


def _todo_feature_slug(features: dict[str, bool]) -> str:
    enabled = [key.replace("_", "-") for key, value in features.items() if value]
    return "-".join(enabled) if enabled else "minimal"


def _interactive_todo_html(features: dict[str, bool]) -> str:
    priority_field = (
        """
        <select id="todo-priority" aria-label="优先级">
          <option value="普通">普通</option>
          <option value="高">高优先级</option>
          <option value="低">低优先级</option>
        </select>"""
        if features["priority"]
        else ""
    )
    due_field = (
        """
        <input id="todo-due-date" type="date" aria-label="截止日期" />"""
        if features["due_date"]
        else ""
    )
    filter_controls = (
        """
      <div class="filters" aria-label="筛选待办">
        <button type="button" data-filter="all">全部</button>
        <button type="button" data-filter="active">未完成</button>
        <button type="button" data-filter="completed">已完成</button>
      </div>"""
        if features["filter"]
        else ""
    )
    priority_js = (
        """
        const priority = document.querySelector("#todo-priority").value;"""
        if features["priority"]
        else """
        const priority = "";"""
    )
    due_js = (
        """
        const dueDate = document.querySelector("#todo-due-date").value;"""
        if features["due_date"]
        else """
        const dueDate = "";"""
    )
    metadata_js = (
        """
          const meta = document.createElement("small");
          meta.textContent = [todo.priority, todo.dueDate ? `截止 ${todo.dueDate}` : ""]
            .filter(Boolean)
            .join(" · ");
          if (meta.textContent) {
            label.append(meta);
          }"""
        if features["priority"] or features["due_date"]
        else ""
    )
    filter_js = (
        """
      let currentFilter = "all";
      document.querySelectorAll("[data-filter]").forEach((button) => {
        button.addEventListener("click", () => {
          currentFilter = button.dataset.filter;
          renderTodos();
        });
      });"""
        if features["filter"]
        else """
      const currentFilter = "all";"""
    )
    visibility_js = (
        """
          const hiddenByFilter =
            currentFilter === "active" && todo.completed ||
            currentFilter === "completed" && !todo.completed;
          item.hidden = hiddenByFilter;"""
        if features["filter"]
        else ""
    )
    template = """<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Todo List</title>
    <style>
      :root {
        color: #17211f;
        background: #f5f3ee;
        font-family: Inter, ui-sans-serif, system-ui, -apple-system,
          BlinkMacSystemFont, "Segoe UI", sans-serif;
      }

      * {
        box-sizing: border-box;
      }

      body {
        min-height: 100vh;
        margin: 0;
        display: grid;
        place-items: center;
        padding: 24px;
      }

      main {
        width: min(680px, 100%);
        border: 1px solid #ddd8cd;
        border-radius: 8px;
        background: #fffdf8;
        box-shadow: 0 16px 40px rgb(68 58 42 / 10%);
        padding: 28px;
      }

      h1 {
        margin: 0 0 18px;
        font-size: 28px;
        letter-spacing: 0;
      }

      form {
        display: grid;
        grid-template-columns: minmax(0, 1fr) repeat(2, auto) auto;
        gap: 10px;
        margin-bottom: 18px;
      }

      input,
      select,
      button {
        min-height: 42px;
        border-radius: 8px;
        font: inherit;
      }

      input,
      select {
        min-width: 0;
        border: 1px solid #cfc8bc;
        padding: 0 12px;
        background: #ffffff;
      }

      button {
        border: 0;
        background: #235b54;
        color: white;
        padding: 0 16px;
        cursor: pointer;
        font-weight: 700;
      }

      button:hover {
        background: #1d4b45;
      }

      ul {
        list-style: none;
        margin: 0;
        padding: 0;
        display: grid;
        gap: 8px;
      }

      li {
        display: grid;
        grid-template-columns: auto minmax(0, 1fr) auto;
        align-items: center;
        gap: 10px;
        border: 1px solid #e4ded4;
        border-radius: 8px;
        background: #ffffff;
        padding: 10px;
      }

      li.completed span {
        color: #71766d;
        text-decoration: line-through;
      }

      .delete-button {
        min-height: 34px;
        background: #7b342f;
      }

      .empty-state {
        margin: 14px 0 0;
        color: #71766d;
      }

      .filters {
        display: flex;
        gap: 8px;
        margin-bottom: 14px;
      }

      li span {
        display: grid;
        gap: 2px;
      }

      li small {
        color: #71766d;
      }
    </style>
  </head>
  <body>
    <main>
      <h1>Todo List</h1>
      <form id="todo-form">
        <input id="todo-input" type="text" placeholder="输入待办事项" autocomplete="off" />
        __PRIORITY_FIELD__
        __DUE_FIELD__
        <button type="submit">添加</button>
      </form>
      __FILTER_CONTROLS__
      <ul id="todo-list" aria-live="polite"></ul>
      <p id="empty-state" class="empty-state">还没有待办事项。</p>
    </main>

    <script>
      const form = document.querySelector("#todo-form");
      const input = document.querySelector("#todo-input");
      const list = document.querySelector("#todo-list");
      const emptyState = document.querySelector("#empty-state");
      const todos = [];
      __FILTER_JS__

      function renderTodos() {
        list.innerHTML = "";
        emptyState.hidden = todos.length > 0;

        todos.forEach((todo) => {
          const item = document.createElement("li");
          item.className = todo.completed ? "completed" : "";
          __VISIBILITY_JS__

          const checkbox = document.createElement("input");
          checkbox.type = "checkbox";
          checkbox.checked = todo.completed;
          checkbox.addEventListener("change", () => {
            todo.completed = checkbox.checked;
            renderTodos();
          });

          const label = document.createElement("span");
          const labelText = document.createElement("strong");
          labelText.textContent = todo.text;
          label.append(labelText);
          __METADATA_JS__

          const deleteButton = document.createElement("button");
          deleteButton.type = "button";
          deleteButton.className = "delete-button";
          deleteButton.textContent = "删除";
          deleteButton.addEventListener("click", () => {
            const index = todos.findIndex((item) => item.id === todo.id);
            if (index >= 0) {
              todos.splice(index, 1);
              renderTodos();
            }
          });

          item.append(checkbox, label, deleteButton);
          list.append(item);
        });
      }

      form.addEventListener("submit", (event) => {
        event.preventDefault();
        const text = input.value.trim();
        if (!text) {
          input.focus();
          return;
        }
        __PRIORITY_JS__
        __DUE_JS__
        todos.push({
          id: crypto.randomUUID(),
          text,
          priority,
          dueDate,
          completed: false,
        });
        input.value = "";
        input.focus();
        renderTodos();
      });

      renderTodos();
    </script>
  </body>
</html>
"""
    return (
        template.replace("__PRIORITY_FIELD__", priority_field)
        .replace("__DUE_FIELD__", due_field)
        .replace("__FILTER_CONTROLS__", filter_controls)
        .replace("__FILTER_JS__", filter_js)
        .replace("__VISIBILITY_JS__", visibility_js)
        .replace("__METADATA_JS__", metadata_js)
        .replace("__PRIORITY_JS__", priority_js)
        .replace("__DUE_JS__", due_js)
    )


def _ensure_content_includes_code_artifacts(result: AgentRunResult) -> AgentRunResult:
    content = result.content
    additions: list[str] = []
    for artifact in result.artifacts:
        if artifact.type != "code":
            continue
        filename_value = artifact.data.get("filename")
        content_value = artifact.data.get("content")
        if not isinstance(filename_value, str) or not filename_value:
            continue
        if not isinstance(content_value, str) or not content_value:
            continue
        if content_value in content:
            continue
        language = _code_fence_language(artifact)
        additions.append(
            f'```{language} filename="{filename_value}"\n{content_value.rstrip()}\n```'
        )

    if not additions:
        return result
    next_content = content.rstrip() + "\n\n" + "\n\n".join(additions)
    return result.model_copy(update={"content": next_content})


def _build_missing_diff_artifacts(
    artifacts: list[Artifact],
    *,
    workspace_id: str,
    workspace_root: Path,
) -> list[Artifact]:
    existing_diff_filenames = {
        filename
        for artifact in artifacts
        if artifact.type == "diff" and (filename := _diff_artifact_filename(artifact))
    }
    diff_artifacts: list[Artifact] = []
    for code_artifact in artifacts:
        if code_artifact.type != "code":
            continue
        filename_value = code_artifact.data.get("filename")
        content_value = code_artifact.data.get("content")
        filename = (
            filename_value if isinstance(filename_value, str) and filename_value else "index.html"
        )
        if filename in existing_diff_filenames:
            continue
        if not isinstance(content_value, str) or not content_value:
            continue
        old_content = _read_existing_workspace_content(workspace_root, workspace_id, filename)
        if old_content is None:
            continue
        diff_artifacts.append(
            Artifact(
                id=f"{code_artifact.id}-diff",
                type="diff",
                title=f"{filename} diff",
                data={
                    "filename": filename,
                    "source_artifact_id": code_artifact.id,
                    "diff": create_unified_diff(
                        old_content,
                        _normalize_generated_file_content(content_value),
                        filename,
                    ),
                },
            )
        )
        existing_diff_filenames.add(filename)
    return diff_artifacts


def _normalize_diff_artifact_ids(artifacts: list[Artifact]) -> list[Artifact]:
    normalized_artifacts: list[Artifact] = []
    for artifact in artifacts:
        if artifact.type != "diff":
            normalized_artifacts.append(artifact)
            continue

        diff_value = artifact.data.get("diff")
        if not isinstance(diff_value, str) or not diff_value:
            normalized_artifacts.append(artifact)
            continue

        filename = _diff_artifact_filename(artifact) or "diff"
        next_id = _content_addressed_diff_artifact_id(filename, diff_value)
        next_data = {**artifact.data, "filename": filename}
        if artifact.id != next_id and "source_artifact_id" not in next_data:
            next_data["source_artifact_id"] = artifact.id

        normalized_artifacts.append(artifact.model_copy(update={"id": next_id, "data": next_data}))

    return normalized_artifacts


def _content_addressed_diff_artifact_id(filename: str, diff: str) -> str:
    slug = _slugify_artifact_filename(filename)
    digest = hashlib.sha256(f"{filename}\0{diff}".encode()).hexdigest()[:12]
    return f"artifact-code-agent-diff-{slug}-{digest}"


def _slugify_artifact_filename(filename: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", filename.lower()).strip("-")
    return slug or "file"


def _diff_artifact_filename(artifact: Artifact) -> str | None:
    filename_value = artifact.data.get("filename")
    if isinstance(filename_value, str) and filename_value:
        return filename_value

    diff_value = artifact.data.get("diff")
    if not isinstance(diff_value, str):
        return None
    for line in diff_value.splitlines():
        if line.startswith("+++ "):
            target = line[4:].strip()
            if target.startswith("b/"):
                return target[2:]
            return target
    return None


def _read_existing_workspace_content(
    workspace_root: Path,
    workspace_id: str,
    filename: str,
) -> str | None:
    try:
        workspace_dir = resolve_workspace_path(workspace_root, workspace_id)
        target_file = resolve_workspace_path(workspace_dir, filename)
    except WorkspacePathError:
        return None
    if not target_file.exists():
        return ""
    return target_file.read_text(encoding="utf-8")


def _code_fence_language(artifact: Artifact) -> str:
    language_value = artifact.data.get("language")
    if not isinstance(language_value, str) or not language_value.strip():
        return "text"
    return language_value.strip().split()[0].lower()


def _normalize_generated_file_content(content: str) -> str:
    return content.rstrip("\n") + "\n"


CODE_AGENT_SYSTEM_PROMPT = """
You are AgentHub Code Agent.
Return one JSON object matching AgentRunResult exactly:
{"agent_id":"code-agent","content":"Markdown summary","artifacts":[],"next_actions":[]}

Rules:
- Generate runnable, concrete code for the user's requested UI or feature.
- When context.user_request is present, treat it as the source of truth for all
  required fields, interactions, mock data, sorting rules, and labels.
- Put the full user-facing answer in content as Markdown.
- Include generated code in content as fenced code blocks.
- Add filename metadata to each code fence, e.g. ```tsx filename="src/App.tsx".
- When the user asks for separate HTML, CSS, and JS files, output each file as
  its own fenced code block or code artifact with its own filename.
- You may also include code artifacts with data.filename, data.language, data.content.
- If you omit artifacts, AgentHub will extract code artifacts from Markdown fences.
- Diff paths must stay inside the workspace and use a/ and b/ headers.
- Do not include secrets or local absolute paths.
""".strip()
