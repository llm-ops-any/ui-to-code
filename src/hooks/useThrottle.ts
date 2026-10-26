import {useEffect, useRef, useState} from 'react'

export function useThrottle(value: string, interval = 500) {
  // 1.定义自定义组件所需数据
  const [throttledValue, setThrottledValue] = useState(value)
  const lastUpdated = useRef<number | null>(null)

  useEffect(() => {
    const now = performance.now()

    if (!lastUpdated.current || now >= lastUpdated.current + interval) {
      lastUpdated.current = now
      setThrottledValue(value)
    } else {
      const id = window.setTimeout(() => {
        lastUpdated.current = now
        setThrottledValue(value)
      }, interval)

      return () => window.clearTimeout(id)
    }
  }, [value, interval])

  return throttledValue
}

export default useThrottle