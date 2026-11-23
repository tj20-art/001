import { createApp } from 'vue'
import { ElMessageBox } from 'element-plus'
import 'element-plus/es/components/message-box/style/css'
import {
  ArrowRight,
  Box,
  Check,
  CircleCheck,
  DocumentChecked,
  Download,
  Edit,
  House,
  Key,
  Lock,
  Plus,
  Refresh,
  Search,
  ShoppingCart,
  Shop,
  Tickets,
  Upload,
  UserFilled,
  View,
  Warning
} from '@element-plus/icons-vue'
import App from './App.vue'
import router from './router'
import store from './store'
import message from './utils/message'
import './assets/styles/global.scss'

const app = createApp(App)
const icons = {
  ArrowRight,
  Box,
  Check,
  CircleCheck,
  DocumentChecked,
  Download,
  Edit,
  House,
  Key,
  Lock,
  Plus,
  Refresh,
  Search,
  ShoppingCart,
  Shop,
  Tickets,
  Upload,
  UserFilled,
  View,
  Warning
}
Object.entries(icons).forEach(([name, icon]) => app.component(name, icon))
app.config.globalProperties.$message = message
app.config.globalProperties.$confirm = ElMessageBox.confirm

app.use(store).use(router).mount('#app')
