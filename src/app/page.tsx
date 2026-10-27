'use client'

import Image from 'next/image'
import React, {useRef, useState} from 'react'
import {useChat} from '@/hooks/useChat'
import {ChatFile} from '@/models/chat'
import PreviewComponent from '@/app/components/PreviewComponent'

export default function Home() {
  // 1.定义组件所需基础数据
  const [activePanel, setActivePanel] = useState('preview')
  const [isUploading, setIsUploading] = useState<boolean>(false)
  const fileInputRef = useRef<HTMLInputElement | null>(null) // 文件输入框的 ref
  const [imageUrl, setImageUrl] = useState<string>('')
  // 已上传截图的附件信息，用于组装平台files字段(CR-16102700/FR-03)
  const [imageFile, setImageFile] = useState<ChatFile | null>(null)
  const [suggestedContent, setSuggestedContent] = useState<string>('')
  const {loading: chatLoading, conversationId, endUserId, code, handleChat} = useChat()

  // 2.根据传递的建议问题和代码生成提问query
  const generateQuery = (suggestedContent?: string, code?: string): string => {
    // 2.1 判断是否传递了代码，如果传递了则为更新代码
    if (code) {
      return `请帮我优化这张UI图对应的代码，您可以任意修改、删除不符合需求的代码并新增对应的逻辑，建议是: ${suggestedContent ?? '-'}。\n\n原始代码如下: ${code}`
    }

    // 2.2 如果没有传递则为初次生成
    return '请帮我生成这张UI图对应的代码，谢谢'
  }

  // 3.定义生成代码处理器
  const handleGenerateCode = async (
    endUserId: string,
    conversationId: string,
    suggestedContent: string,
    code: string,
    files: ChatFile[],
  ) => {
    // 3.1 判断是否存在原始UI图，并且不在加载中
    if (files.length === 0 || chatLoading) {
      alert('请确保原始图片已上传，并且当前无在生成代码')
      return
    }

    // 3.2 计算对应的query信息
    const query = generateQuery(suggestedContent, code)

    // 3.3 清空建议问题
    setSuggestedContent('')

    // 3.4 调用hooks处理器获取数据，附件以平台files字段传入(CR-16102700/FR-03)
    await handleChat({
      end_user_id: endUserId,
      conversation_id: conversationId,
      query: query,
      files: files,
    })
  }

  // 5.定义文件输入框图片变化监听函数
  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      const reader = new FileReader()
      reader.onloadend = async () => {
        await handleUpload(String(reader.result)) // 自动上传
      }
      reader.readAsDataURL(file) // 将文件读取为 Base64
    }
  }

  // 6.定义图片上传处理函数
  const handleUpload = async (fileBase64: string) => {
    setIsUploading(true)

    try {
      // 上传文件获取图片公网URL链接
      const resp = await fetch('/api/upload/image', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({file: fileBase64}),
      })
      const data = await resp.json()
      setIsUploading(() => false)
      setImageUrl(data?.image_url)
      // 组装平台附件信息(CR-16102700/FR-03)：上传接口已按图片真实类型返回name/mime/extension
      const file: ChatFile = {
        name: data?.name ?? 'screenshot.jpg',
        url: data?.image_url,
        kind: 'image',
        mime: data?.mime ?? 'image/jpeg',
        extension: data?.extension ?? 'jpg',
        size: data?.size ?? 0,
      }
      setImageFile(() => file)
      await handleGenerateCode(
        endUserId,
        conversationId,
        '',
        '',
        [file],
      )
    } catch (error) {
      alert('上传错误')
      console.error('错误: ', error)
    }
  }

  // 7.定义出发文件上传选择框
  const triggerFileInput = () => {
    if (isUploading) return
    fileInputRef.current?.click()
  }


  return <div className="flex">
    {/* 左侧操作菜单 */}
    <div className="fixed inset-y-0 w-96 flex flex-col z-40">
      <div className="flex grow flex-col gap-y-2 overflow-y-auto border-r border-gray-200 bg-white px-6">
        {/* 应用标题与描述 */}
        <h1 className="mt-10 mb-2 text-2xl text-gray-700">截图转HTML智能体</h1>
        <p className="text-gray-500 text-[14px] mb-4">拖拽或者点击上传图片快速开始</p>
        {/* 修改建议输入框 */}
        <textarea
          rows={3}
          value={suggestedContent}
          onChange={(event) => setSuggestedContent(event.target.value)}
          className="min-h-[100px] border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-700 p-2 text-[14px]"
          placeholder="请输入修改建议..."
        />
        {/* 操作按钮 */}
        <div className="flex flex-col gap-3 mb-4">
          <button
            className="bg-gray-700 text-white h-8 text-[14px] rounded-lg cursor-pointer hover:bg-gray-800"
            onClick={() => handleGenerateCode(endUserId, conversationId, suggestedContent, code, imageFile ? [imageFile] : [])}
          >
            更新代码
          </button>
          <button
            className="bg-gray-700 text-white h-8 text-[14px] rounded-lg cursor-pointer hover:bg-gray-800"
            onClick={() => handleGenerateCode(endUserId, conversationId, '', '', imageFile ? [imageFile] : [])}
          >
            重新生成代码
          </button>
        </div>
        {/* 加载动画 */}
        {
          chatLoading && (
            <div className="flex items-center gap-2 mb-4">
              <svg className="w-4 h-4 animate-spin text-gray-500" xmlns="http://www.w3.org/2000/svg" fill="none"
                   viewBox="0 0 24 24" stroke="currentColor">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V4a10 10 0 00-10 10h2z"></path>
              </svg>
              <div className="">代码生成中...</div>
            </div>
          )
        }
        {/* 上传图片预览图 */}
        {
          imageUrl && (
            <div className="flex flex-col gap-2">
              <Image
                src={imageUrl}
                alt="Screenshot"
                width={500}
                height={500}
                className="border border-gray-200 rounded-lg overflow-hidden"
              />
              <div className="text-center text-[14px] text-gray-500">原始截图</div>
            </div>
          )
        }
        {/* 上传按钮&区域 */}
        <div
          className="border-2 border-dashed cursor-pointer w-full h-[150px] text-center leading-[150px] text-[14px] text-gray-500 bg-gray-100 rounded-lg"
          onClick={triggerFileInput}
        >
          {isUploading ? '图片上传中...' : '拖拽或点击上传图片'}
        </div>
        <input
          hidden
          ref={fileInputRef}
          type="file"
          accept="image/*"
          onChange={handleImageChange}
        />
      </div>
    </div>
    {/* 右侧预览窗口与代码下载 */}
    <div className="pl-96 w-full">
      <div className="p-4">
        {/* 切换菜单 */}
        <div className="flex items-center gap-4 mb-4">
          <button
            className={`${activePanel === 'preview' ? 'bg-gray-700 text-white' : 'bg-white text-gray-700'} h-8 border border-gray-200 px-2.5 text-[14px] rounded-lg cursor-pointer hover:bg-gray-700 hover:text-white`}
            onClick={() => setActivePanel('preview')}
          >
            效果预览
          </button>
          <button
            className={`${activePanel === 'code' ? 'bg-gray-700 text-white' : 'bg-white text-gray-700'} h-8 border border-gray-200 px-2.5 text-[14px] rounded-lg cursor-pointer hover:bg-gray-700 hover:text-white`}
            onClick={() => setActivePanel('code')}
          >
            截图代码
          </button>
        </div>
        {/* 不同面板 */}
        <div className="break-all overflow-hidden">
          {
            activePanel === 'preview' ? (
              <div
                className="border-2 border-gray-200 h-[600px] rounded-[20px] bg-gray-100 flex items-center justify-center text-gray-500 text-[14px]"
              >
                {code ? <PreviewComponent code={code}/> : '代码预览效果'}
              </div>
            ) : (
              <div
                className="p-4 border border-gray-200 min-h-[500px] rounded-lg bg-gray-700 text-white flex text-[14px]"
              >
                {code}
              </div>
            )
          }
        </div>
      </div>
    </div>
  </div>
}
