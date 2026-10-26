// 开放API聊天Chat请求结构体
export type ChatRequest = {
  conversation_id?: string
  end_user_id?: string
  query: string
  image_urls?: string[]
  stream?: boolean
}