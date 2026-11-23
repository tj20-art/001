import { ElMessage as Message } from 'element-plus'
import 'element-plus/es/components/message/style/css'

const withCloseButton = (options) => ({
  showClose: true,
  ...(typeof options === 'string' ? { message: options } : options)
})

const message = (options) => Message(withCloseButton(options))

for (const type of ['success', 'warning', 'info', 'error']) {
  message[type] = (options) => Message[type](withCloseButton(options))
}

message.closeAll = Message.closeAll

export default message
