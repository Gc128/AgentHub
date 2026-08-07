from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from agenthub.schemas.agent import ReviewFinding
from agenthub.schemas.change_set import ChangeSet

_CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE)
_CSS_IMPORT_RE = re.compile(
    r"@import\s+(?:url\(\s*)?['\"]([^'\"]+)['\"]\s*\)?",
    re.IGNORECASE,
)
_EXTERNAL_SCHEMES = {"http", "https"}
_IGNORED_SCHEMES = {"data", "blob", "mailto", "tel"}


class _ReferenceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: list[tuple[str, str, int]] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        normalized_tag = tag.lower()
        for name, value in attrs:
            attribute = name.lower()
            is_loaded_resource = (
                attribute == "src"
                or (normalized_tag == "link" and attribute == "href")
                or (normalized_tag == "video" and attribute == "poster")
            )
            if is_loaded_resource and value:
                self.references.append((attribute, value.strip(), self.getpos()[0]))


class StaticCandidateInspector:
    """Run conservative checks that have deterministic, implementation-independent results."""

    def inspect(self, change_set: ChangeSet, staging_dir: Path) -> list[ReviewFinding]:
        findings: list[ReviewFinding] = []
        if change_set.entry_path is None:
            findings.append(
                self._blocker(
                    code="missing_entry",
                    path="index.html",
                    message="静态 Web 候选缺少可预览的 HTML 入口文件。",
                    evidence="Staging snapshot contains no index.html or other .html/.htm entry.",
                    suggestion="添加 index.html，或保留一个可用的 HTML 入口文件。",
                )
            )

        for file_record in change_set.files:
            if file_record.operation != "upsert":
                continue
            content = file_record.after_content
            if content is None or not content.strip():
                findings.append(
                    self._blocker(
                        code="empty_candidate_file",
                        path=file_record.path,
                        message="候选文件为空。",
                        evidence="The complete candidate content is empty or whitespace-only.",
                        suggestion="返回完整且非空的文件内容。",
                    )
                )
                continue
            if "\x00" in content:
                findings.append(
                    self._blocker(
                        code="nul_byte",
                        path=file_record.path,
                        message="候选文本文件包含 NUL 字节。",
                        evidence="The candidate text contains U+0000.",
                        suggestion="移除二进制或 NUL 内容，并返回有效的 UTF-8 文本。",
                    )
                )

        if not staging_dir.is_dir():
            return [
                self._blocker(
                    code="missing_staging_snapshot",
                    path=change_set.entry_path or "index.html",
                    message="隔离候选快照不存在。",
                    evidence=f"Staging directory is missing: {staging_dir.name}",
                    suggestion="重新生成候选 Change Set。",
                )
            ]

        for path in sorted(staging_dir.rglob("*")):
            if path.is_symlink():
                findings.append(
                    self._blocker(
                        code="candidate_symlink",
                        path=path.relative_to(staging_dir).as_posix(),
                        message="候选快照包含不允许的符号链接。",
                        evidence="A symlink was found inside the isolated staging snapshot.",
                        suggestion="使用普通文件并确保所有资源位于 Workspace 内。",
                    )
                )
                continue
            if not path.is_file():
                continue
            relative = path.relative_to(staging_dir).as_posix()
            suffix = path.suffix.lower()
            if suffix not in {".html", ".htm", ".css"}:
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                findings.append(
                    self._blocker(
                        code="invalid_utf8",
                        path=relative,
                        message="静态页面资源不是有效的 UTF-8 文本。",
                        evidence="UTF-8 decoding failed for an HTML/CSS candidate resource.",
                        suggestion="将静态文本资源转换为 UTF-8。",
                    )
                )
                continue
            if suffix in {".html", ".htm"}:
                findings.extend(self._inspect_html(relative, content, staging_dir))
            else:
                findings.extend(self._inspect_css(relative, content, staging_dir))
        return findings

    def _inspect_html(
        self,
        path: str,
        content: str,
        staging_dir: Path,
    ) -> list[ReviewFinding]:
        parser = _ReferenceParser()
        parser.feed(content)
        return [
            finding
            for attribute, reference, line in parser.references
            if (
                finding := self._reference_finding(
                    owner_path=path,
                    reference=reference,
                    staging_dir=staging_dir,
                    line=line,
                    context=attribute,
                )
            )
            is not None
        ]

    def _inspect_css(
        self,
        path: str,
        content: str,
        staging_dir: Path,
    ) -> list[ReviewFinding]:
        references = {match.group(2).strip() for match in _CSS_URL_RE.finditer(content)}
        references.update(match.group(1).strip() for match in _CSS_IMPORT_RE.finditer(content))
        findings: list[ReviewFinding] = []
        for reference in references:
            finding = self._reference_finding(
                owner_path=path,
                reference=reference,
                staging_dir=staging_dir,
                line=None,
                context="css-url",
            )
            if finding is not None:
                findings.append(finding)
        return findings

    def _reference_finding(
        self,
        *,
        owner_path: str,
        reference: str,
        staging_dir: Path,
        line: int | None,
        context: str,
    ) -> ReviewFinding | None:
        if not reference or reference.startswith("#"):
            return None
        if reference.startswith("//"):
            return self._external_reference(owner_path, reference, line)
        parsed = urlsplit(reference)
        scheme = parsed.scheme.lower()
        if scheme in _EXTERNAL_SCHEMES or scheme == "javascript":
            return self._external_reference(owner_path, reference, line)
        if scheme in _IGNORED_SCHEMES:
            return None
        if scheme:
            return self._external_reference(owner_path, reference, line)

        decoded_path = unquote(parsed.path).strip()
        if not decoded_path or decoded_path == "/":
            return None
        owner_parent = PurePosixPath(owner_path).parent
        candidate = PurePosixPath(decoded_path.lstrip("/"))
        normalized = owner_parent / candidate if not decoded_path.startswith("/") else candidate
        target = (staging_dir / normalized.as_posix()).resolve()
        try:
            target.relative_to(staging_dir.resolve())
        except ValueError:
            return self._blocker(
                code="resource_path_escape",
                path=owner_path,
                line=line,
                message="静态资源引用越出了隔离 Workspace。",
                evidence=f"{context} references {reference!r}.",
                suggestion="改为引用 Workspace 内的相对路径资源。",
            )
        if target.is_file():
            return None
        return self._blocker(
            code="missing_local_resource",
            path=owner_path,
            line=line,
            message=f"引用的本地资源不存在：{decoded_path}",
            evidence=f"{context} references {reference!r}, but the resolved file is missing.",
            suggestion="补充该文件或修正引用路径。",
        )

    def _external_reference(
        self,
        owner_path: str,
        reference: str,
        line: int | None,
    ) -> ReviewFinding:
        return self._blocker(
            code="external_resource",
            path=owner_path,
            line=line,
            message="静态候选引用了不允许的外部资源。",
            evidence=f"External reference: {reference!r}",
            suggestion="将资源保存到候选 Workspace 并使用本地相对路径。",
        )

    @staticmethod
    def _blocker(
        *,
        code: str,
        path: str,
        message: str,
        evidence: str,
        suggestion: str,
        line: int | None = None,
    ) -> ReviewFinding:
        return ReviewFinding(
            severity="blocker",
            category=f"static_{code}",
            criterion_id="criterion-static-safety",
            path=path,
            line=line,
            message=message,
            evidence=evidence,
            suggestion=suggestion,
        )
