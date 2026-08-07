import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { AppliedDiffRecord, ChangeSet, Conversation } from '../../types/api'
import { WorkspacePanel } from './WorkspacePanel'

vi.mock('react-syntax-highlighter', () => ({
  Prism: ({ children }: { children: string }) => <pre>{children}</pre>,
}))
vi.mock('react-syntax-highlighter/dist/esm/styles/prism', () => ({
  oneLight: {},
}))

const conversation: Conversation = {
  id: 'conv-1',
  title: 'Preview test',
  mode: 'group',
  agent_ids: ['orchestrator', 'code-agent', 'review-agent', 'preview-agent'],
  status: 'active',
  is_pinned: false,
  workspace_id: 'ws-1',
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
}

const changeSet: ChangeSet = {
  id: 'changeset-1',
  conversation_id: 'conv-1',
  workspace_id: 'ws-1',
  status: 'failed',
  repair_count: 1,
  entry_path: 'index.html',
  preview_report: {
    status: 'fail',
    entry_path: 'index.html',
    preview_path: '/candidate-preview',
    screenshot_path: '/candidate-screenshot',
    checks: [
      {
        criterion_id: 'criterion-visible',
        name: 'page visible',
        status: 'passed',
        duration_ms: 1,
        error: '',
      },
      {
        criterion_id: 'criterion-storage',
        name: 'storage persists',
        status: 'failed',
        duration_ms: 1,
        error: 'storage mismatch',
      },
    ],
    console_errors: [],
    page_errors: [],
    failed_requests: [],
  },
  files: [
    {
      id: 'change-file-1',
      path: 'index.html',
      operation: 'upsert',
      before_sha256: 'before',
      after_content: '<!doctype html><h1>Candidate</h1>',
      after_sha256: 'after',
      diff: '--- a/index.html\n+++ b/index.html',
    },
  ],
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
}

describe('WorkspacePanel candidate preview', () => {
  it('keeps files and history visible and opens live preview in a large modal', () => {
    const onReReviewChangeSet = vi.fn()
    render(
      <WorkspacePanel
        appliedDiffs={[]}
        changeSets={[changeSet]}
        conversation={conversation}
        deletingFilePath={null}
        files={[]}
        getCandidatePreviewUrl={(changeSetId, path) =>
          `http://127.0.0.1:8000/trusted/${changeSetId}/${path}`
        }
        getFilePreviewUrl={() => ''}
        onDeleteFile={vi.fn()}
        onPreviewFile={vi.fn()}
        onPromoteChangeSet={vi.fn()}
        onReapplyChangeSet={vi.fn()}
        onReReviewChangeSet={onReReviewChangeSet}
        onRevertAppliedDiff={vi.fn()}
        onRevertChangeSet={vi.fn()}
        preview={null}
        promotingChangeSetId={null}
        reapplyingChangeSetId={null}
        reReviewingChangeSetId={null}
        revertingDiffRecordId={null}
        workspaceRefreshToken={0}
      />,
    )

    expect(screen.getByRole('heading', { name: '文件' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '变更历史' })).toBeInTheDocument()
    expect(screen.queryByText('1/2 项通过')).not.toBeInTheDocument()
    expect(
      screen.queryByRole('img', { name: /Chromium 验证截图/ }),
    ).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '重新代码审查' }))
    expect(onReReviewChangeSet).toHaveBeenCalledWith('changeset-1')

    fireEvent.click(screen.getByRole('button', { name: /打开隔离预览/ }))

    expect(
      document.querySelector('.ant-modal-wrap.ant-modal-centered'),
    ).toBeInTheDocument()
    const livePreview = screen.getByTitle('changeset-1 人工隔离预览')
    expect(livePreview).toHaveAttribute(
      'src',
      'http://127.0.0.1:8000/trusted/changeset-1/index.html',
    )
    expect(screen.getByRole('button', { name: /新窗口打开/ })).toBeEnabled()
    expect(
      screen.queryByRole('img', { name: /Chromium 验证截图/ }),
    ).not.toBeInTheDocument()

    expect(screen.queryByRole('tab', { name: /验证截图/ })).not.toBeInTheDocument()
  })

  it('groups promoted files by change set and offers safe reapply after revert', () => {
    const onReapplyChangeSet = vi.fn()
    const appliedAt = new Date().toISOString()
    const revertedAt = new Date().toISOString()
    const records: AppliedDiffRecord[] = ['index.html', 'script.js'].map(
      (path, index) => ({
        id: `apply-${index}`,
        workspace_id: 'ws-1',
        artifact_id: `artifact-${index}`,
        change_set_id: 'changeset-promoted',
        path,
        diff: `--- a/${path}\n+++ b/${path}\n@@ -0,0 +1 @@\n+content`,
        applied_at: appliedAt,
        reverted_at: revertedAt,
      }),
    )

    render(
      <WorkspacePanel
        appliedDiffs={records}
        changeSets={[]}
        conversation={conversation}
        deletingFilePath={null}
        files={[]}
        getCandidatePreviewUrl={() => ''}
        getFilePreviewUrl={() => ''}
        onDeleteFile={vi.fn()}
        onPreviewFile={vi.fn()}
        onPromoteChangeSet={vi.fn()}
        onReapplyChangeSet={onReapplyChangeSet}
        onReReviewChangeSet={vi.fn()}
        onRevertAppliedDiff={vi.fn()}
        onRevertChangeSet={vi.fn()}
        preview={null}
        promotingChangeSetId={null}
        reapplyingChangeSetId={null}
        reReviewingChangeSetId={null}
        revertingDiffRecordId={null}
        workspaceRefreshToken={0}
      />,
    )

    expect(screen.getByText('2 个文件')).toBeInTheDocument()
    const reapplyButton = screen.getByRole('button', { name: '重新应用' })
    fireEvent.click(reapplyButton)
    expect(onReapplyChangeSet).toHaveBeenCalledWith('changeset-promoted')
  })

  it('offers promote in the workspace panel for a ready reapply candidate', () => {
    const onPromoteChangeSet = vi.fn()
    render(
      <WorkspacePanel
        appliedDiffs={[]}
        changeSets={[{ ...changeSet, id: 'changeset-reapply', status: 'ready' }]}
        conversation={conversation}
        deletingFilePath={null}
        files={[]}
        getCandidatePreviewUrl={() => 'http://127.0.0.1:8000/trusted'}
        getFilePreviewUrl={() => ''}
        onDeleteFile={vi.fn()}
        onPreviewFile={vi.fn()}
        onPromoteChangeSet={onPromoteChangeSet}
        onReapplyChangeSet={vi.fn()}
        onReReviewChangeSet={vi.fn()}
        onRevertAppliedDiff={vi.fn()}
        onRevertChangeSet={vi.fn()}
        preview={null}
        promotingChangeSetId={null}
        reapplyingChangeSetId={null}
        reReviewingChangeSetId={null}
        revertingDiffRecordId={null}
        workspaceRefreshToken={0}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: '合入 Workspace' }))
    expect(onPromoteChangeSet).toHaveBeenCalledWith('changeset-reapply')
  })

  it('hides re-review when a historical candidate snapshot is incomplete', () => {
    const { container } = render(
      <WorkspacePanel
        appliedDiffs={[]}
        changeSets={[
          {
            ...changeSet,
            files: changeSet.files.map((file) => ({
              id: file.id,
              path: file.path,
              operation: file.operation,
              before_sha256: file.before_sha256,
              after_sha256: file.after_sha256,
              diff: file.diff,
            })),
          },
        ]}
        conversation={conversation}
        deletingFilePath={null}
        files={[]}
        getCandidatePreviewUrl={() => ''}
        getFilePreviewUrl={() => ''}
        onDeleteFile={vi.fn()}
        onPreviewFile={vi.fn()}
        onPromoteChangeSet={vi.fn()}
        onReapplyChangeSet={vi.fn()}
        onReReviewChangeSet={vi.fn()}
        onRevertAppliedDiff={vi.fn()}
        onRevertChangeSet={vi.fn()}
        preview={null}
        promotingChangeSetId={null}
        reapplyingChangeSetId={null}
        reReviewingChangeSetId={null}
        revertingDiffRecordId={null}
        workspaceRefreshToken={0}
      />,
    )

    expect(
      within(container).queryByRole('button', { name: '重新代码审查' }),
    ).not.toBeInTheDocument()
  })
})
