export type DiffLine = {
  /** 原始 diff 行文本。 */
  content: string
  /** 行类型，用于决定新增、删除、文件头和上下文样式。 */
  kind: 'added' | 'removed' | 'meta' | 'context'
}

/** 根据 unified diff 行前缀判断行类型。 */
export const getDiffLineKind = (line: string): DiffLine['kind'] => {
  if (
    line.startsWith('+++') ||
    line.startsWith('---') ||
    line.startsWith('@@')
  ) {
    return 'meta'
  }
  if (line.startsWith('+')) {
    return 'added'
  }
  if (line.startsWith('-')) {
    return 'removed'
  }
  return 'context'
}

/** 把 unified diff 字符串拆成可渲染的行模型。 */
export const parseDiffLines = (diff: string): DiffLine[] =>
  diff.split('\n').map((line) => ({
    content: line,
    kind: getDiffLineKind(line),
  }))
