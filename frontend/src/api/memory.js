import client from './client'

// 长期记忆（用户主权模式）：跨会话背景资料 CRUD
export const listMemories = () => client.get('/memory')

export const addMemory = (content, tag) => client.post('/memory', { content, tag })

export const deleteMemory = (key) => client.delete(`/memory/${key}`)
