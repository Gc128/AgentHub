from pathlib import Path

import pytest

from agenthub.agents.external_cli_agent import ExternalCliAgentAdapter
from agenthub.config import Settings
from agenthub.schemas.agent import AgentRunInput


@pytest.mark.asyncio
async def test_external_cli_agent_generates_diff_without_mutating_workspace(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspaces"
    workspace = workspace_root / "ws_cli"
    workspace.mkdir(parents=True)
    (workspace / "index.html").write_text("<h1>Old</h1>\n", encoding="utf-8")

    fake_codex = tmp_path / "fake_codex.py"
    fake_codex.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "from pathlib import Path",
                "Path('index.html').write_text('<h1>New</h1>\\n', encoding='utf-8')",
                "print('updated index.html')",
            ]
        ),
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)

    adapter = ExternalCliAgentAdapter(
        agent_id="custom-agent-cli",
        name="CLI Agent",
        backend_id="codex-cli",
        settings=Settings(
            workspace_root=workspace_root,
            codex_cli_path=str(fake_codex),
            agent_cli_timeout_seconds=10,
        ),
        system_prompt="你会修改 workspace 文件。",
    )

    result = await adapter.run(
        AgentRunInput(
            conversation_id="conv_cli",
            workspace_id="ws_cli",
            user_message="更新页面标题",
            history=[],
            context={},
        )
    )

    assert result.agent_id == "custom-agent-cli"
    assert "updated index.html" in result.content
    assert (workspace / "index.html").read_text(encoding="utf-8") == "<h1>Old</h1>\n"
    assert [artifact.type for artifact in result.artifacts] == ["code", "diff"]
    assert result.artifacts[0].data["content"] == "<h1>New</h1>\n"
    assert "-<h1>Old</h1>" in str(result.artifacts[1].data["diff"])
    assert "+<h1>New</h1>" in str(result.artifacts[1].data["diff"])
