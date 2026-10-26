import React, {useEffect, useRef} from 'react'
import useThrottle from '@/hooks/useThrottle'

// 自定义组件props数据结构
interface Props {
  code: string
}

export default function PreviewComponent({code}: Props) {
  // 1.定义自定义组件所需数据
  const iframeRef = useRef<HTMLIFrameElement | null>(null)
  const throttleCode = useThrottle(code, 200)  // 最多不超过200毫秒更新

  // 2.监听throttleCode变化时更新iframe框数据
  useEffect(() => {
    const iframe = iframeRef.current
    if (iframe) iframe.srcdoc = throttleCode
  }, [throttleCode])

  return (
    <div className="overflow-y-auto overflow-x-hidden w-full">
      <iframe
        ref={iframeRef}
        title="预览"
        className="rounded-[20px] shadow-lg mx-auto w-full h-[600px]"
      />
    </div>
  )
}

