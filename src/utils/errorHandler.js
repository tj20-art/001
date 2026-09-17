import { Message } from 'element-ui'

export const handleApiError = (error) => {
  if (!error || !error.response) {
    Message.error('网络异常，请检查服务是否启动或稍后重试')
    return
  }

  const status = error.response.status
  const errorMsg = (error.response.data && error.response.data.message) || '操作失败，请稍后重试'

  switch (status) {
    case 400:
      Message.error(`参数错误：${errorMsg}`)
      break
    case 401:
      Message.warning(errorMsg || '登录状态失效，请重新登录')
      break
    case 403:
      Message.error(errorMsg || '权限不足')
      break
    case 404:
      Message.error(errorMsg || '资源不存在')
      break
    case 409:
      Message.error(errorMsg)
      break
    case 429:
      Message.warning(errorMsg || '请求过于频繁，请稍后再试')
      break
    case 500:
      Message.error(errorMsg || '服务器异常，请联系管理员')
      break
    default:
      Message.error(errorMsg)
  }
}
