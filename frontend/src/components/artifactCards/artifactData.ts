import type { Artifact } from '../../types/api'

/**
 * 从 Artifact.data 中安全读取字符串字段。
 * Artifact.data 是 Record<string, unknown>，所以组件渲染前必须做类型收窄，避免把未知值直接当字符串用。
 */
export const getArtifactString = (
  artifact: Artifact,
  key: string,
  fallback = '',
) => {
  const value = artifact.data[key]
  return typeof value === 'string' ? value : fallback
}

/**
 * 从 Artifact.data 中安全读取字符串数组字段。
 * Orchestrator 的 steps、Review 的 findings 都会走这里，兼容非数组时返回空数组。
 */
export const getArtifactStringList = (artifact: Artifact, key: string) => {
  const value = artifact.data[key]
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string')
    : []
}

/**
 * 从 Artifact.data 中安全读取数字字段。
 * 当前用于显示 mock Orchestrator 的 estimated_minutes。
 */
export const getArtifactNumber = (
  artifact: Artifact,
  key: string,
): number | null => {
  const value = artifact.data[key]
  return typeof value === 'number' ? value : null
}
