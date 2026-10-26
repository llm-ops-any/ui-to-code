import COS, {PutObjectParams} from 'cos-nodejs-sdk-v5'

const cos = new COS({
  SecretId: process.env?.COS_SECRET_ID,
  SecretKey: process.env?.COS_SECRET_KEY,
})

// 将图片上传至腾讯云COS对象存储路由
export async function POST(request: Request) {
  // 1.提取传递给api接口的文件数据(Base64编码)
  const {file} = await request.json()

  // 2.将base64数据转换为buffer，并组装文件名字
  const fileBuffer = Buffer.from(file.split(',')[1], 'base64')
  const fileName = `uploads/${Date.now()}.jpg`

  // 3.构建上传参数
  const params: PutObjectParams = {
    Bucket: String(process.env?.COS_BUCKET),
    Region: String(process.env?.COS_REGION),
    Key: fileName,
    Body: fileBuffer,
    ContentType: 'image/jpeg',
  }

  // 4.调用客户端上传图片
  const data = await cos.putObject(params)

  return new Response(JSON.stringify({'image_url': `https://${data.Location}`}))
}