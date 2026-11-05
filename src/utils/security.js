export const sanitizeInput = (input) => {
  if (typeof input !== 'string') return input
  // Vue's text interpolation already performs contextual HTML escaping.
  // Mutating credentials here used to turn characters such as "&" into
  // entities and made valid passwords impossible to authenticate with.
  return input.split(String.fromCharCode(0)).join('')
}

export const validateField = (value, fieldType) => {
  switch (fieldType) {
    case 'username':
      return {
        valid: /^[a-zA-Z0-9_]{5,20}$/.test(value),
        msg: '用户名需为5-20位字母、数字或下划线'
      }
    case 'password':
      return {
        valid: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()+=-]).{8,20}$/.test(value),
        msg: '密码需含大小写字母、数字、特殊符号，8-20位'
      }
    case 'phone':
      return {
        valid: /^1[3-9]\d{9}$/.test(value),
        msg: '手机号需为11位合法格式（如13800138000）'
      }
    case 'role': {
      const validRoles = ['user', 'merchant', 'admin', 'auditor']
      return {
        valid: validRoles.includes(value),
        msg: `角色仅支持${validRoles.join('/')}`
      }
    }
    default:
      return { valid: true, msg: '' }
  }
}
