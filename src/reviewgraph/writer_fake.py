from __future__ import annotations

from dataclasses import dataclass

from reviewgraph.markers import MarkerCommentPage, PaginatedMarkerComment
from reviewgraph.models import (
    ArtifactKind,
    GitHubWriterResult,
    WriterStatus,
)
from reviewgraph.payload_validation import validate_final_issue_comment_payload
from reviewgraph.writer_input import FinalizedIssueCommentWriterInput, build_finalized_issue_comment_writer_input


@dataclass(frozen=True)
class FakeIssueComment:
    comment_id: str
    body: str
    author_login: str
    author_type: str = "Bot"

class FakeIssueCommentWriter:
    def __init__(self, *, author_login: str = "reviewgraph-bot", request_id: str = "REQ-fake-writer") -> None:
        if not isinstance(author_login, str) or not author_login:
            raise ValueError("fake writer author_login is required")
        self.author_login = author_login
        self.request_id = request_id
        self.call_count = 0
        self._comments: list[FakeIssueComment] = []

    @property
    def comments(self) -> tuple[FakeIssueComment, ...]:
        return tuple(self._comments)

    def post_issue_comment(self, writer_input: FinalizedIssueCommentWriterInput) -> GitHubWriterResult:
        if not isinstance(writer_input, FinalizedIssueCommentWriterInput):
            raise ValueError("fake writer accepts only finalized issue-comment writer input")
        if self.author_login != writer_input.approved_actor:
            return GitHubWriterResult(
                status=WriterStatus.FAILED,
                artifact_kind=ArtifactKind.ISSUE_COMMENT,
                target_hash=writer_input.target_hash,
                payload_hash=writer_input.final_payload_hash,
                error="approved_actor_mismatch",
            )
        validation = validate_final_issue_comment_payload(writer_input.final_payload)
        if validation.status.value != "pass":
            return GitHubWriterResult(
                status=WriterStatus.FAILED,
                artifact_kind=ArtifactKind.ISSUE_COMMENT,
                target_hash=writer_input.target_hash,
                payload_hash=writer_input.final_payload_hash,
                error=validation.reason_code.value if validation.reason_code is not None else "payload_validation_failed",
            )
        self.call_count += 1
        comment_id = f"fake-comment-{len(self._comments) + 1}"
        self._comments.append(
            FakeIssueComment(
                comment_id=comment_id,
                body=writer_input.final_payload.body,
                author_login=self.author_login,
            )
        )
        return GitHubWriterResult(
            status=WriterStatus.POSTED,
            artifact_kind=ArtifactKind.ISSUE_COMMENT,
            target_hash=writer_input.target_hash,
            payload_hash=writer_input.final_payload_hash,
            comment_id=comment_id,
        )

    def get_issue_comments_page(
        self,
        owner_repo: str,
        pr_number: int,
        cursor: object | None,
        timeout_seconds: int,
    ) -> MarkerCommentPage:
        if cursor is not None:
            return MarkerCommentPage(comments=(), completed=True, request_id=self.request_id)
        return MarkerCommentPage(
            comments=tuple(
                PaginatedMarkerComment(
                    comment_id=comment.comment_id,
                    body=comment.body,
                    author_login=comment.author_login,
                    author_type=comment.author_type,
                    source_provider="github",
                )
                for comment in self._comments
            ),
            completed=True,
            request_id=self.request_id,
        )
