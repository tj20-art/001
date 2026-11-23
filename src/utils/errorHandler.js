import message from '@/utils/message'

export const handleApiError = (error) => {
  if (!error || !error.response) {
    message.error('网络异常，请检查服务是否启动或稍后重试')
    return
  }

  const status = error.response.status
  const errorMsg = error.response.data?.message

  switch (status) {
    case 400:
      message.error(errorMsg ? `参数错误：${errorMsg}` : '请求参数错误')
      break
    case 401:
      message.warning(errorMsg || '登录状态已失效，请重新登录')
      break
    case 403:
      message.error(errorMsg || '权限不足')
      break
    case 404:
      message.error(errorMsg || '资源不存在')
      break
    case 429:
      message.warning(errorMsg || '请求过于频繁，请稍后再试')
      break
    case 500:
      message.error(errorMsg || '服务器异常，请联系管理员')
      break
    default:
      message.error(errorMsg || '操作失败，请稍后重试')
  }
}
