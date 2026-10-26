import {useState} from 'react'
import {chat} from '@/services/chat'
import {ChatRequest} from '@/models/chat'

export const useChat = () => {
  // 1.定义自定义hooks所需数据
  const [loading, setLoading] = useState<boolean>(false)
  const [conversationId, setConversationId] = useState<string>('')
  const [endUserId, setEndUserId] = useState<string>('')
  const [code, setCode] = useState<string>('')

  // 2.定义聊天会话处理器
  const handleChat = async (req: ChatRequest) => {
    try {
      // 2.1 更新loading状态，并重置code代码
      setLoading(true)
      setCode(() => '')
      req.stream = true

      // 2.2 定义其他数据初始化数据
      let isInit = false

      await chat(req, (event_response) => {
        // 2.3 提取event和data
        const event = event_response?.event
        const data = event_response?.data as Record<string, never>

        // 2.4 完成数据的初始化
        if (!isInit && data?.conversation_id && data?.end_user_id) {
          setConversationId(() => data?.conversation_id)
          setEndUserId(() => data?.end_user_id)
          isInit = true
        }

        // 2.5 检测事件类型，如果事件为agent_message则提取消息为code
        if (event === 'agent_message') {
          setCode((prevState) => prevState + data?.answer)
        }
      })
    } finally {
      setLoading(false)
    }
  }

  return {loading, conversationId, endUserId, code, handleChat}
}