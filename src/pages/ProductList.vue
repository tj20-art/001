<template>
  <div class="page-shell seller-page">
    <common-header />

    <main class="dashboard-main page-main">
      <header class="management-heading">
        <h1>{{ isAdmin ? '全部商品管理' : '我的商品中心' }}</h1>
        <el-button type="primary" icon="Plus" @click="handleAddProduct">发布商品</el-button>
      </header>
      <dl class="management-summary section-card">
        <div>
          <dt>商品总数</dt>
          <dd>{{ summary.total ?? 0 }}</dd>
        </div>
        <div>
          <dt>在售</dt>
          <dd>{{ summary.on_sale ?? 0 }}</dd>
        </div>
        <div>
          <dt>已下架</dt>
          <dd>{{ summary.off_shelf ?? 0 }}</dd>
        </div>
        <div>
          <dt>总库存</dt>
          <dd>{{ summary.stock ?? 0 }}</dd>
        </div>
      </dl>
      <section class="section-card management-list" aria-label="商品列表">
        <form class="management-toolbar" @submit.prevent="handleSearch">
          <el-input v-model.trim="searchParams.name" placeholder="商品名称" aria-label="商品名称" clearable />
          <el-input v-model.trim="searchParams.product_id" placeholder="商品 ID" aria-label="商品 ID" clearable />
          <el-select v-model="searchParams.status" clearable placeholder="全部状态" aria-label="商品状态">
            <el-option label="在售" value="on_sale" />
            <el-option label="已下架" value="off_shelf" />
          </el-select>
          <el-button native-type="submit" type="primary">查询</el-button>
          <el-button @click="handleReset">重置</el-button>
        </form>
        <AppLoading v-if="loading" />
        <ListError v-else-if="loadError" :message="loadError" @retry="fetchPage()" />
        <el-empty v-else-if="!productList.length" description="没有符合条件的商品" />
        <template v-else>
          <table class="management-table">
            <thead>
              <tr>
                <th scope="col">商品</th>
                <th v-if="isAdmin" scope="col" class="wide-column">卖家 ID</th>
                <th scope="col" class="wide-column">价格</th>
                <th scope="col" class="wide-column">库存</th>
                <th scope="col">状态</th>
                <th scope="col" class="manage-actions">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="product in productList" :key="product.id">
                <td>
                  <div class="managed-product">
                    <div class="managed-thumbnail"><ProductCover :src="getCoverImage(product)" /></div>
                    <div>
                      <strong>{{ product.name }}</strong>
                      <span
                        >#{{ product.id }}<template v-if="product.category"> · {{ product.category }}</template></span
                      >
                    </div>
                  </div>
                </td>
                <td v-if="isAdmin" class="wide-column">{{ product.seller_id }}</td>
                <td class="wide-column">{{ formatPrice(product.price) }}</td>
                <td class="wide-column">{{ product.stock }}</td>
                <td>
                  <el-tag size="small" :type="product.status === 'on_sale' ? 'success' : 'info'">{{
                    product.status === 'on_sale' ? '在售' : '已下架'
                  }}</el-tag>
                </td>
                <td class="manage-actions">
                  <div>
                    <el-button text type="primary" :disabled="!!rowBusy" @click="handleEditProduct(product)"
                      >编辑</el-button
                    >
                    <el-button text :disabled="!!rowBusy" @click="handleViewProduct(product)">详情</el-button>
                    <el-button
                      text
                      :type="product.status === 'on_sale' ? 'danger' : 'success'"
                      :disabled="!!rowBusy"
                      @click="handleToggleStatus(product)"
                    >
                      {{ product.status === 'on_sale' ? '下架' : '上架' }}
                    </el-button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-if="total > pageSize" class="pagination-bar">
            <el-pagination
              :current-page="page"
              :page-size="pageSize"
              :total="total"
              :pager-count="5"
              layout="prev, pager, next"
              @current-change="fetchPage(appliedFilters, $event)"
            />
          </div>
        </template>
      </section>
    </main>

    <el-dialog :title="isEdit ? '编辑商品' : '发布商品'" v-model="dialogVisible" width="820px" @closed="resetFormState">
      <el-form ref="formRef" :model="formData" :rules="formRules" label-width="90px">
        <el-form-item label="商品名称" prop="name">
          <el-input v-model="formData.name" />
        </el-form-item>
        <el-form-item label="商品分类" prop="category">
          <el-input v-model="formData.category" placeholder="例如：电子产品 / 图书 / 食品" />
        </el-form-item>
        <el-form-item label="商品介绍" prop="description">
          <el-input v-model="formData.description" type="textarea" :rows="4" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="价格" prop="price">
              <el-input v-model.number="formData.price" type="number" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="库存" prop="stock">
              <el-input v-model.number="formData.stock" type="number" min="0" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item v-if="isEdit" label="状态" prop="status">
          <el-radio-group v-model="formData.status">
            <el-radio-button value="on_sale">在售</el-radio-button>
            <el-radio-button value="off_shelf">下架</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="商品图片">
          <input ref="imageInput" type="file" accept="image/*" multiple @change="handleImagesChange" />
          <div class="upload-tip">最多 6 张，支持 jpg / jpeg / png / gif / webp。重新选择会替换原图片组。</div>

          <div v-if="selectedImagePreviews.length" class="preview-grid">
            <div v-for="(src, index) in selectedImagePreviews" :key="`new-${index}`" class="preview-card">
              <img :src="src" alt="preview" />
              <span class="preview-badge">新图片 {{ index + 1 }}</span>
            </div>
          </div>

          <div v-else-if="formData.image_urls.length" class="preview-grid">
            <div v-for="(src, index) in formData.image_urls" :key="`old-${index}`" class="preview-card">
              <img :src="src" alt="old-preview" />
              <span class="preview-badge">原图片 {{ index + 1 }}</span>
            </div>
          </div>

          <el-checkbox
            v-if="isEdit && formData.image_urls.length && !selectedImagePreviews.length"
            v-model="formData.remove_all_images"
          >
            删除原图片组
          </el-checkbox>
        </el-form-item>

        <el-form-item label="商品视频">
          <input ref="videoInput" type="file" accept="video/*" @change="handleVideoChange" />
          <div class="upload-tip">支持 mp4 / webm / ogg / mov。重新选择会替换原视频。</div>
          <div v-if="selectedVideoPreview || formData.video_url" class="video-preview-wrap">
            <video
              :src="selectedVideoPreview || mediaUrl(formData.video_url)"
              class="dialog-video-preview"
              controls
            ></video>
          </div>
          <el-checkbox v-if="isEdit && formData.video_url && !selectedVideoPreview" v-model="formData.remove_video">
            删除原视频
          </el-checkbox>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmitForm">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog title="商品详情" v-model="detailVisible" width="760px">
      <div v-if="selectedProduct" class="detail-panel">
        <div class="detail-preview-grid">
          <el-carousel v-if="(selectedProduct.image_urls || []).length" height="320px" :autoplay="false">
            <el-carousel-item v-for="(img, index) in selectedProduct.image_urls" :key="`detail-img-${index}`">
              <img :src="mediaUrl(img)" class="dialog-image" alt="detail-image" />
            </el-carousel-item>
          </el-carousel>
          <video
            v-if="selectedProduct.video_url"
            :src="mediaUrl(selectedProduct.video_url)"
            class="dialog-video-preview"
            controls
          ></video>
        </div>
        <div class="detail-rows">
          <div>
            <span>商品名称</span><strong>{{ selectedProduct.name }}</strong>
          </div>
          <div>
            <span>卖家 ID</span><strong>{{ selectedProduct.seller_id }}</strong>
          </div>
          <div>
            <span>分类</span><strong>{{ selectedProduct.category || '未分类' }}</strong>
          </div>
          <div>
            <span>价格</span><strong>{{ formatPrice(selectedProduct.price) }}</strong>
          </div>
          <div>
            <span>库存</span><strong>{{ selectedProduct.stock }}</strong>
          </div>
          <div>
            <span>状态</span><strong>{{ selectedProduct.status === 'on_sale' ? '在售' : '已下架' }}</strong>
          </div>
        </div>
        <p class="detail-description">{{ selectedProduct.description || '暂无商品介绍' }}</p>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import CommonHeader from '@/components/CommonHeader.vue'
import AppLoading from '@/components/AppLoading.vue'
import { addProduct, deleteProduct, getProductDetail, getProductList, updateProduct } from '@/services/productService'
import { mapGetters, useStore } from 'vuex'
import ProductCover from '@/components/ProductCover.vue'
import ListError from '@/components/ListError.vue'
import { coverOf, mediaUrl, money } from '@/utils/productDisplay'
import { usePagedList } from '@/utils/usePagedList'

const createDefaultForm = () => ({
  id: null,
  name: '',
  category: '',
  description: '',
  price: 0,
  stock: 0,
  status: 'on_sale',
  image_urls: [],
  video_url: '',
  remove_all_images: false,
  remove_video: false
})

export default {
  name: 'ProductList',
  components: { CommonHeader, AppLoading, ListError, ProductCover },
  setup() {
    const store = useStore()
    const { items: productList, ...list } = usePagedList((params, config) => {
      const scope = store.getters['authModule/isAdmin'] ? { include_off_shelf: true } : { mine: true }
      return getProductList({ ...params, ...scope, view: 'summary', overview: true }, config)
    }, 'product_list')
    return { productList, ...list }
  },
  data() {
    return {
      rowBusy: null,
      submitting: false,
      dialogVisible: false,
      detailVisible: false,
      isEdit: false,
      searchParams: {
        product_id: '',
        name: '',
        status: ''
      },
      formData: createDefaultForm(),
      selectedProduct: null,
      selectedImageFiles: [],
      selectedImagePreviews: [],
      selectedVideoFile: null,
      selectedVideoPreview: '',
      formRules: {
        name: [{ required: true, message: '请输入商品名称', trigger: 'blur' }],
        price: [
          { required: true, message: '请输入商品价格', trigger: 'blur' },
          {
            validator: (rule, value, callback) => {
              if (Number(value) <= 0) {
                callback(new Error('价格必须大于0'))
                return
              }
              callback()
            },
            trigger: 'blur'
          }
        ],
        stock: [
          { required: true, message: '请输入库存数量', trigger: 'blur' },
          {
            validator: (rule, value, callback) => {
              if (Number(value) < 0) {
                callback(new Error('库存不能小于0'))
                return
              }
              callback()
            },
            trigger: 'blur'
          }
        ]
      }
    }
  },
  computed: {
    ...mapGetters('authModule', ['isAdmin'])
  },
  mounted() {
    this.fetchPage()
  },
  beforeUnmount() {
    this.resetFormState()
  },
  methods: {
    getCoverImage: coverOf,
    mediaUrl,
    formatPrice: money,
    handleSearch() {
      return this.fetchPage(
        {
          product_id: this.searchParams.product_id || undefined,
          name: this.searchParams.name || undefined,
          status: this.searchParams.status || undefined
        },
        1
      )
    },
    handleReset() {
      this.searchParams = { product_id: '', name: '', status: '' }
      return this.fetchPage({}, 1)
    },
    handleAddProduct() {
      this.isEdit = false
      this.formData = createDefaultForm()
      this.dialogVisible = true
    },
    async readDetails(product) {
      if (this.rowBusy) return null
      this.rowBusy = product.id
      try {
        const response = await getProductDetail(product.id)
        return response.data?.product_info
      } catch {
        return null
      } finally {
        this.rowBusy = null
      }
    },
    async handleEditProduct(product) {
      const detail = await this.readDetails(product)
      if (!detail) return
      this.isEdit = true
      this.formData = {
        id: detail.id,
        name: detail.name,
        category: detail.category || '',
        description: detail.description || '',
        price: Number(detail.price),
        stock: Number(detail.stock),
        status: detail.status,
        image_urls: detail.image_urls || [],
        video_url: detail.video_url || '',
        remove_all_images: false,
        remove_video: false
      }
      this.dialogVisible = true
    },
    async handleViewProduct(product) {
      const detail = await this.readDetails(product)
      if (!detail) return
      this.selectedProduct = detail
      this.detailVisible = true
    },
    clearImagePreviews() {
      this.selectedImagePreviews.forEach((src) => URL.revokeObjectURL(src))
      this.selectedImagePreviews = []
    },
    handleImagesChange(event) {
      const files = Array.from((event.target && event.target.files) || [])
      if (files.length > 6) {
        this.$message.error('最多只能选择 6 张图片')
        event.target.value = ''
        return
      }
      this.clearImagePreviews()
      this.selectedImageFiles = files
      this.formData.remove_all_images = false
      this.selectedImagePreviews = files.map((file) => URL.createObjectURL(file))
    },
    handleVideoChange(event) {
      const file = event.target.files && event.target.files[0]
      this.selectedVideoFile = file || null
      this.formData.remove_video = false
      if (this.selectedVideoPreview) {
        URL.revokeObjectURL(this.selectedVideoPreview)
        this.selectedVideoPreview = ''
      }
      if (file) {
        this.selectedVideoPreview = URL.createObjectURL(file)
      }
    },
    buildFormData() {
      const formData = new FormData()
      formData.append('name', this.formData.name)
      formData.append('category', this.formData.category || '')
      formData.append('description', this.formData.description || '')
      formData.append('price', this.formData.price)
      formData.append('stock', this.formData.stock)
      formData.append('status', this.formData.status || 'on_sale')
      formData.append('remove_all_images', this.formData.remove_all_images ? 'true' : 'false')
      formData.append('remove_video', this.formData.remove_video ? 'true' : 'false')
      this.selectedImageFiles.forEach((file) => {
        formData.append('images', file)
      })
      if (this.selectedVideoFile) {
        formData.append('video', this.selectedVideoFile)
      }
      return formData
    },
    async handleSubmitForm() {
      if (this.submitting) return
      this.submitting = true
      try {
        const valid = await this.$refs.formRef.validate().catch(() => false)
        if (!valid) return
        const payload = this.buildFormData()
        if (this.isEdit) {
          await updateProduct(this.formData.id, payload)
          this.$message.success('商品更新成功')
        } else {
          await addProduct(payload)
          this.$message.success('商品发布成功')
        }
        this.dialogVisible = false
        await this.fetchPage()
      } catch {
        // The API client reports save errors.
      } finally {
        this.submitting = false
      }
    },
    async handleToggleStatus(product) {
      if (this.rowBusy) return
      this.rowBusy = product.id
      try {
        if (product.status === 'on_sale') {
          await this.$confirm('确定要下架该商品吗？', '下架商品', {
            confirmButtonText: '下架',
            cancelButtonText: '取消',
            type: 'warning'
          })
          await deleteProduct(product.id)
          this.$message.success('商品已下架')
        } else {
          const payload = new FormData()
          payload.append('status', 'on_sale')
          await updateProduct(product.id, payload)
          this.$message.success('商品已重新上架')
        }
        await this.fetchPage()
      } catch {
        // Cancellation and request errors are handled by their callers.
      } finally {
        this.rowBusy = null
      }
    },
    resetFormState() {
      this.formData = createDefaultForm()
      this.selectedImageFiles = []
      this.clearImagePreviews()
      this.selectedVideoFile = null
      if (this.selectedVideoPreview) {
        URL.revokeObjectURL(this.selectedVideoPreview)
        this.selectedVideoPreview = ''
      }
      if (this.$refs.imageInput) this.$refs.imageInput.value = ''
      if (this.$refs.videoInput) this.$refs.videoInput.value = ''
    },
    formatTime(timeStr) {
      if (!timeStr) return '--'
      return new Date(timeStr).toLocaleString('zh-CN', { hour12: false })
    }
  }
}
</script>

<style scoped lang="scss">
.management-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}
.management-heading h1 {
  margin: 0;
  font-size: clamp(22px, 4vw, 32px);
}
.management-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  padding: 12px 4px;
  margin: 0 0 16px;
}
.management-summary div {
  padding: 4px 16px;
}
.management-summary div + div {
  border-left: 1px solid var(--mall-border);
}
.management-summary dt {
  color: var(--mall-muted);
  font-size: 13px;
}
.management-summary dd {
  font-size: 23px;
  font-weight: 700;
  margin: 5px 0 0;
}
.management-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 14px;
}
.management-toolbar :deep(.el-input),
.management-toolbar :deep(.el-select) {
  width: 156px;
}
.management-toolbar :deep(.el-button),
.manage-actions :deep(.el-button) {
  margin: 0;
}
.management-list {
  padding-bottom: 10px;
}
.management-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
  font-size: 14px;
}
.management-table th,
.management-table td {
  padding: 10px 12px;
  border-top: 1px solid var(--mall-border);
}
.management-table th {
  background: #faf8f4;
  color: var(--mall-muted);
  font-size: 13px;
}
.managed-product {
  display: flex;
  align-items: center;
  gap: 10px;
}
.managed-product strong,
.managed-product span {
  display: block;
  overflow-wrap: anywhere;
}
.managed-product span {
  margin-top: 2px;
  color: var(--mall-muted);
  font-size: 12px;
}
.managed-thumbnail {
  overflow: hidden;
  flex: none;
  width: 44px;
  height: 44px;
  border-radius: 6px;
}
.manage-actions {
  width: 1%;
}
.manage-actions > div {
  display: flex;
  flex-wrap: wrap;
  min-width: 155px;
}
.manage-actions :deep(.el-button) {
  padding-inline: 7px;
}
@media (max-width: 680px) {
  .wide-column {
    display: none;
  }
  .management-summary div {
    padding-inline: 8px;
  }
  .management-summary dd {
    font-size: 18px;
  }
  .management-toolbar :deep(.el-input),
  .management-toolbar :deep(.el-select) {
    flex: 1 1 105px;
    min-width: 0;
  }
  .management-table th,
  .management-table td {
    padding: 8px 5px;
  }
  .managed-product {
    gap: 5px;
  }
  .managed-thumbnail {
    width: 32px;
    height: 32px;
  }
  .manage-actions > div {
    min-width: 60px;
  }
  .manage-actions :deep(.el-button) {
    padding: 4px;
    min-height: 28px;
  }
}

.upload-tip {
  margin-top: 6px;
  color: #6b7280;
}

.preview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
  gap: 10px;
  margin-top: 14px;
}

.preview-card {
  position: relative;
  border-radius: 16px;
  overflow: hidden;
  height: 96px;
}

.preview-card img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.preview-badge {
  position: absolute;
  left: 8px;
  bottom: 8px;
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(17, 24, 39, 0.76);
  color: #fff;
  font-size: 12px;
}

.video-preview-wrap,
.detail-preview-grid {
  margin-top: 12px;
}

.dialog-video-preview,
.dialog-image {
  width: 100%;
  border-radius: 16px;
  object-fit: cover;
}

.detail-panel {
  display: grid;
  gap: 18px;
}

.detail-preview-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.detail-rows {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.detail-rows div {
  background: #f8fbff;
  border-radius: 16px;
  padding: 14px;
}

.detail-rows span {
  display: block;
  color: #6b7280;
  font-size: 12px;
  margin-bottom: 6px;
}

.detail-rows strong {
  color: #111827;
}

.detail-description {
  margin: 0;
  color: #6b7280;
  line-height: 1.8;
}

@media (max-width: 768px) {
  .detail-preview-grid,
  .detail-rows {
    grid-template-columns: 1fr;
  }
}
</style>
