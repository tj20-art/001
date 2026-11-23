const backend = process.env.VUE_APP_API_BASE_URL || 'https://127.0.0.1:2333'
const currency = new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' })

export function mediaUrl(path) {
  if (path?.startsWith('/static/') && /^https?:\/\//.test(backend)) return new URL(path, backend).href
  return path || ''
}

export function coverOf(item) {
  return mediaUrl(item?.image_urls?.[0] || item?.image_url)
}

export function money(value) {
  return currency.format(Number(value) || 0)
}
