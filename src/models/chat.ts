// 聊天附件结构体，与LLMOps开放API的files字段对齐(CR-16102700/FR-03)
// 说明：平台只认files，历史字段image_urls不是接口字段，会被静默丢弃；每项至少需要name+url，否则返回校验错误
export type ChatFile = {
  // 附件显示名称，平台用它拼附件清单，缺失会被参数校验拦下
  name: string
  // 公网可访问的文件地址，视觉模型直接按该地址拉取图片
  url: string
  // 附件类型，图片固定为image，平台据此决定是否作为图片输入
  kind: 'image' | 'file'
  // 真实MIME，例如image/png，与对象存储上的ContentType保持一致
  mime?: string
  // 扩展名，不带点，例如png
  extension?: string
  // 文件字节数
  size?: number
  // 服务端已解析出的文本内容，图片为空
  text?: string
  // 文本是否被截断
  truncated?: boolean
  // 附件说明，平台仅作展示，不参与提示词拼接
  note?: string
}

// 开放API聊天Chat请求结构体
export type ChatRequest = {
  conversation_id?: string
  end_user_id?: string
  query: string
  // 上传的附件列表，图片以kind=image传入(CR-16102700/FR-03)
  files?: ChatFile[]
  stream?: boolean
}
