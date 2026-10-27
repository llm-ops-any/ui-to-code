import COS, {PutObjectParams} from 'cos-nodejs-sdk-v5'

const cos = new COS({
  SecretId: process.env?.COS_SECRET_ID,
  SecretKey: process.env?.COS_SECRET_KEY,
})

// 图片MIME与扩展名的映射表(CR-16102700)：按图片真实类型命名并声明ContentType，
// 历史实现把所有图片都存成.jpg并声明image/jpeg，PNG截图会被标错类型
const IMAGE_EXTENSIONS: Record<string, string> = {
  'image/png': 'png',
  'image/jpeg': 'jpg',
  'image/webp': 'webp',
  'image/gif': 'gif',
  'image/bmp': 'bmp',
}

// 将图片上传至腾讯云COS对象存储路由
export async function POST(request: Request) {
  // 1.提取传递给api接口的文件数据(Base64编码)
  const {file} = await request.json()

  // 2.从data URL头部解析真实MIME与base64正文
  const matched = /^data:([^;,]+);base64,([\s\S]*)$/.exec(String(file ?? ''))
  if (!matched) {
    return new Response(JSON.stringify({error: '图片数据格式不正确，需要base64编码的data URL'}), {status: 400})
  }

  // 3.计算真实类型，未识别的类型按jpeg兜底
  const mime = String(matched[1] ?? '').toLowerCase()
  const extension = IMAGE_EXTENSIONS[mime] ?? 'jpg'
  const fileBuffer = Buffer.from(matched[2], 'base64')
  const key = `uploads/${Date.now()}.${extension}`

  // 4.构建上传参数
  const params: PutObjectParams = {
    Bucket: String(process.env?.COS_BUCKET),
    Region: String(process.env?.COS_REGION),
    Key: key,
    Body: fileBuffer,
    ContentType: IMAGE_EXTENSIONS[mime] ? mime : 'image/jpeg',
  }

  // 5.调用客户端上传图片
  const data = await cos.putObject(params)

  // 6.返回附件元信息，供前端组装平台files字段(CR-16102700/FR-03)
  return new Response(JSON.stringify({
    'image_url': `https://${data.Location}`,
    'name': key.replace('uploads/', ''),
    'extension': extension,
    'mime': IMAGE_EXTENSIONS[mime] ? mime : 'image/jpeg',
    'size': fileBuffer.length,
  }))
}
