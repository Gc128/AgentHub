import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Artifact, ChangeSet } from '../../types/api'
import { MessageArtifactActions } from './MessageArtifactActions'

describe('MessageArtifactActions trusted preview URL', () => {
  it('ignores a model supplied preview_url and opens the backend route', () => {
    const artifact: Artifact = {
      id: 'preview-1',
      type: 'preview',
      title: 'Preview',
      data: {
        change_set_id: 'changeset-1',
        preview_url: 'https://preview.example.com/hallucinated',
      },
      created_at: new Date().toISOString(),
    }
    const changeSet: ChangeSet = {
      id: 'changeset-1',
      conversation_id: 'conv-1',
      workspace_id: 'ws-1',
      status: 'ready',
      repair_count: 0,
      entry_path: 'index.html',
      files: [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }
    const open = vi.spyOn(window, 'open').mockImplementation(() => null)

    render(
      <MessageArtifactActions
        artifacts={[artifact]}
        changeSets={[changeSet]}
        getCandidatePreviewUrl={(changeSetId) =>
          `http://127.0.0.1:8000/api/change-sets/${changeSetId}/preview-page`
        }
        getWorkspacePreviewUrl={() => ''}
        onPromoteChangeSet={vi.fn()}
        promotingChangeSetId={null}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /打开预览/ }))
    expect(open).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/change-sets/changeset-1/preview-page',
      '_blank',
      'noopener,noreferrer',
    )
    expect(open).not.toHaveBeenCalledWith(
      expect.stringContaining('preview.example.com'),
      expect.anything(),
      expect.anything(),
    )
  })

  it('renders a candidate manifest as a readable summary without source content', () => {
    const artifact: Artifact = {
      id: 'artifact-code-agent-candidate-manifest',
      type: 'file',
      title: 'Candidate manifest',
      data: {
        kind: 'candidate_manifest',
        file_count: 2,
        check_count: 3,
        operations: [
          {
            path: 'index.html',
            operation: 'upsert',
            content: '<main>internal source must stay hidden</main>',
          },
          { path: 'legacy.js', operation: 'delete', content: null },
        ],
        preview_checks: [{}, {}, {}],
      },
      created_at: new Date().toISOString(),
    }

    render(
      <MessageArtifactActions
        artifacts={[artifact]}
        changeSets={[]}
        getCandidatePreviewUrl={() => ''}
        getWorkspacePreviewUrl={() => ''}
        onPromoteChangeSet={vi.fn()}
        promotingChangeSetId={null}
      />,
    )

    expect(screen.getByText('候选文件清单')).toBeInTheDocument()
    expect(screen.getByText('2 个候选文件')).toBeInTheDocument()
    expect(screen.queryByText('3 项自动检查')).not.toBeInTheDocument()
    expect(screen.getByText('index.html')).toBeInTheDocument()
    expect(screen.getByText('legacy.js')).toBeInTheDocument()
    expect(screen.queryByText(/internal source must stay hidden/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '查看详情' })).not.toBeInTheDocument()
  })

  it('shows only the Review report and ignores legacy browser reports', () => {
    const artifact: Artifact = {
      id: 'change-set-artifact',
      type: 'change_set',
      title: 'Change Set',
      data: { change_set_id: 'changeset-1', status: 'failed' },
      created_at: new Date().toISOString(),
    }
    const storageError =
      `AssertionError: localStorage['agenthub-students'] expected '王五', got ` +
      `'[{"id":1,"name":"张三"},{"id":2,"name":"王五"}]'`
    const changeSet: ChangeSet = {
      id: 'changeset-1',
      conversation_id: 'conv-1',
      workspace_id: 'ws-1',
      status: 'failed',
      repair_count: 1,
      entry_path: 'index.html',
      review_report: {
        verdict: 'pass',
        risk_level: 'low',
        summary: '代码审查通过。',
        findings: [],
        covered_criteria: ['criterion-storage'],
      },
      preview_report: {
        status: 'fail',
        entry_path: 'index.html',
        preview_path: '/trusted-preview',
        checks: [
          {
            criterion_id: 'criterion-visible',
            name: '页面可见',
            status: 'passed',
            duration_ms: 1,
            error: '',
          },
          {
            criterion_id: 'criterion-storage',
            name: '刷新后数据仍存在',
            status: 'failed',
            duration_ms: 1,
            error: storageError,
          },
          {
            criterion_id: 'criterion-testids',
            name: '所有要求的 data-testid 存在',
            status: 'failed',
            duration_ms: 1,
            error: 'AssertionError: Expected count 2, got 3',
          },
        ],
        console_errors: [],
        page_errors: [],
        failed_requests: [],
      },
      files: [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }

    render(
      <MessageArtifactActions
        artifacts={[artifact]}
        changeSets={[changeSet]}
        getCandidatePreviewUrl={() => '/trusted-preview'}
        getWorkspacePreviewUrl={() => ''}
        onPromoteChangeSet={vi.fn()}
        promotingChangeSetId={null}
      />,
    )

    expect(screen.getAllByText('代码审查通过。').length).toBeGreaterThan(0)
    expect(screen.queryByText('1/3 项通过')).not.toBeInTheDocument()
    expect(screen.queryByText('未通过：刷新后数据仍存在')).not.toBeInTheDocument()
    expect(screen.queryByText(/"review"/)).not.toBeInTheDocument()
  })

  it('does not render legacy browser-check failures', () => {
    const artifact: Artifact = {
      id: 'change-set-native-validation',
      type: 'change_set',
      title: 'Change Set',
      data: { change_set_id: 'changeset-native-validation', status: 'failed' },
      created_at: new Date().toISOString(),
    }
    const changeSet: ChangeSet = {
      id: 'changeset-native-validation',
      conversation_id: 'conv-1',
      workspace_id: 'ws-1',
      status: 'failed',
      repair_count: 1,
      entry_path: 'index.html',
      review_report: {
        verdict: 'pass',
        risk_level: 'low',
        summary: '代码审查通过。',
        findings: [],
        covered_criteria: ['criterion-invalid-score'],
      },
      preview_report: {
        status: 'fail',
        entry_path: 'index.html',
        preview_path: '/trusted-preview',
        checks: [
          {
            criterion_id: 'criterion-invalid-score',
            name: '非法成绩被阻止并提示',
            status: 'failed',
            duration_ms: 1,
            error:
              `AssertionError: "[data-testid='error-message']" is not visible`,
          },
        ],
        console_errors: [],
        page_errors: [],
        failed_requests: [],
      },
      files: [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }

    render(
      <MessageArtifactActions
        artifacts={[artifact]}
        changeSets={[changeSet]}
        getCandidatePreviewUrl={() => '/trusted-preview'}
        getWorkspacePreviewUrl={() => ''}
        onPromoteChangeSet={vi.fn()}
        promotingChangeSetId={null}
      />,
    )

    expect(screen.getAllByText('代码审查通过。').length).toBeGreaterThan(0)
    expect(screen.queryByText(/非法成绩被阻止并提示/)).not.toBeInTheDocument()
  })
})
