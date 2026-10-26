// 1.定义基础Fetch请求数据
const baseFetchOptions = {
  method: 'GET',
  mode: 'cors',
  credentials: 'include',
  headers: new Headers({
    'Content-Type': 'application/json',
  }),
  redirect: 'follow',
}

// 2.定义fetch参数类型
type FetchOptionType = Omit<RequestInit, 'body'> & {
  params?: Record<string, unknown>
  body?: BodyInit | Record<string, unknown> | null
}

// 3.封装基于post的sse(流式事件响应)请求
export const ssePost = async (
  url: string,
  fetchOptions: FetchOptionType,
  onData: (data: { [key: string]: unknown }) => void,
) => {
  // 5.1 组装基础的fetch请求配置
  const options = Object.assign({}, baseFetchOptions, {method: 'POST'}, fetchOptions)

  // 5.3 结构body参数，并处理body对应的数据
  const {body} = fetchOptions
  if (body) options.body = JSON.stringify(body)

  // 5.4 发起fetch请求并处理流式事件响应
  const response = await fetch(url, options as RequestInit)

  // 5.5 获取响应内容类型并判断类型
  const contentType = response.headers.get('Content-Type')
  if (contentType?.includes('application/json')) {
    // 5.6 接口为json输出，意味着出错，直接返回json数据
    return await response.json()
  }

  // 5.7 否则获取流式输出数据
  return await handleStream(response, onData)
}


const handleStream = (
  response: Response,
  onData: (data: Record<string, unknown>) => void,
): Promise<void> => {
  return new Promise((resolve, reject) => {
    // 1.检测网络请求是否正常
    if (!response.ok) {
      reject(new Error('网络请求失败'))
      return
    }

    // 2.构建reader以及decoder
    const reader = response.body?.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    let event = ''
    let data = ''

    // 3.构建read函数用于去读取数据
    const read = () => {
      reader?.read().then((result) => {
        if (result.done) {
          resolve()
          return
        }

        buffer += decoder.decode(result.value, {stream: true})
        const lines = buffer.split('\n')

        try {
          lines.forEach((line) => {
            line = line.trim()
            if (line.startsWith('event:')) {
              event = line.slice(6).trim()
            } else if (line.startsWith('data:')) {
              data = line.slice(5).trim()
            }

            // 每个事件以空行结束，只有event和data同时存在，才表示一次流式事件的数据完整获取到了
            if (line === '') {
              if (event !== '' && data !== '') {
                onData({
                  event: event,
                  data: JSON.parse(data),
                })
                event = ''
                data = ''
              }
            }
          })
          buffer = lines.pop() || ''
        } catch (e) {
          reject(e)
        }

        read()
      })
    }

    // 4.调用read函数去执行获取对应的数据
    read()
  })
}
