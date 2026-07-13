import client from './client'

export async function searchCases(params) {
  const { data } = await client.get('/cases/search', { params })
  return data
}

export async function getCaseDetail(caseId) {
  const { data } = await client.get(`/cases/${caseId}`)
  return data
}