import {ssePost} from '@/utils/request'
import {ChatRequest} from '@/models/chat'

// 向开放API发起聊天请求
export const chat = (req: ChatRequest, onData: (event_response: Record<string, unknown>) => void) => {
  return ssePost('/api/chat', {body: req}, onData)
}