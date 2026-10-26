import {NextResponse} from 'next/server'

// 1.从环境变量中提取app_id、请求秘钥与地址
const app_id = String(process.env?.LLMOPS_APP_ID)
const base_url = String(process.env?.LLMOPS_API_BASE)
const api_key = String(process.env?.LLMOPS_API_KEY)

// 2.桥接LLMOps开放API，确保API_KEY安全
export async function POST(request: Request) {
  // 2.1 获取请求体数据，并填充应用id和非流式输出标记
  const requestBody = await request.json()
  requestBody.app_id = app_id

  // 2.2 往headers中添加内容，涵盖鉴权信息、内容类型
  const headers = new Headers({
    'Authorization': `Bearer ${api_key}`,
    'Content-Type': 'application/json',
  })

  try {
    // 2.3 设置转发请求选项
    const fetchOptions = {
      method: 'POST',
      headers: headers,
      body: JSON.stringify(requestBody),
    }

    // 2.4 发起请求转发
    const response = await fetch(`${base_url}/chat`, fetchOptions)

    // 2.5 判断响应内容类型并处理
    const contentType = response.headers.get('Content-Type')

    // 2.6 判断不同的类型执行不同的操作
    if (contentType?.includes('application/json')) {
      // 2.7 json响应结构转发json
      const data = await response.json()
      return NextResponse.json(data)
    } else if (contentType?.includes('text/event-stream')) {
      // 2.8 如果是流式事件(SSE)，则转发流数据
      return new Response(response.body, {
        headers: response.headers,
      })
    } else {
      // 2.9 其他类型的响应处理
      const body = await response.text()
      return new Response(body, {
        headers: response.headers,
      })
    }

  } catch (error) {
    console.log('桥接开放API接口失败:', error)
    return new Response('Error forwarding request', {status: 500})
  }
}