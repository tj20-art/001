<template>
  <div class="form-input">
    <label class="input-label">{{ label }}</label>
    <input
      :type="type || 'text'"
      :value="value"
      @input="$emit('input', $event.target.value)"
      :placeholder="placeholder"
      class="input-control"
    />
    <p class="error-message" v-if="error">{{ error }}</p>
  </div>
</template>

<script>
export default {
  name: 'FormInput',
  props: {
    label: { type: String, required: true },
    value: { type: String, default: '' },
    type: { type: String, default: 'text' },
    placeholder: { type: String, default: '' },
    error: { type: String, default: '' },
    validate: { type: Function, default: () => true }
  }
}
</script>

<style scoped lang="scss">
.form-input {
  margin-bottom: 15px;

  .input-label {
    display: block;
    margin-bottom: 5px;
    color: #666;
  }

  .input-control {
    width: 100%;
    padding: 10px;
    border: 1px solid #ddd;
    border-radius: 4px;
    font-size: 16px;

    &:focus {
      outline: none;
      border-color: #409eff;
    }
  }

  .error-message {
    margin: 5px 0 0;
    color: #ff4444;
    font-size: 14px;
  }
}
</style>
