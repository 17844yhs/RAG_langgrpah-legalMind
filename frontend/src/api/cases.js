import client from './client'

export async function searchCases(params) {
  // 60s：Reranker 为 CPU 推理（数秒级），且后端冷启动首次检索需加载模型，
  // 沿用默认 30s 会在冷启动场景误报"搜索失败"
  const { data } = await client.get('/cases/search', { params, timeout: 60000 })
  return data
}

export async function getCaseDetail(caseId) {
  const { data } = await client.get(`/cases/${caseId}`)
  return data
}