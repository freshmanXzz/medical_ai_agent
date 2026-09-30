<template>
  <div class="login-wrapper">
    <el-card class="login-card">
      <h2 class="title">Martin 医学影像工作站</h2>
      <p class="subtitle">请使用医生账号登录</p>
      <el-form :model="form" label-position="top" @keyup.enter="handleLogin">
        <el-form-item label="用户名">
          <el-input v-model="form.username" placeholder="doctor_a" autofocus />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" show-password placeholder="密码" />
        </el-form-item>
        <el-button type="primary" class="submit" :loading="loading" @click="handleLogin">
          登 录
        </el-button>
        <p v-if="errorMsg" class="error">{{ errorMsg }}</p>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { loginDoctor } from '../api'

const router = useRouter()
const form = reactive({ username: '', password: '' })
const loading = ref(false)
const errorMsg = ref('')

async function handleLogin() {
  if (!form.username || !form.password) {
    errorMsg.value = '请输入用户名和密码'
    return
  }
  loading.value = true
  errorMsg.value = ''
  try {
    const { data } = await loginDoctor(form.username, form.password)
    localStorage.setItem('martin_doctor', JSON.stringify(data))
    router.push('/')
  } catch (err: unknown) {
    const resp = (err as { response?: { status?: number } }).response
    errorMsg.value = resp?.status === 401 ? '用户名或密码错误' : '登录失败，请稍后重试'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: var(--el-fill-color-light);
}
.login-card {
  width: 360px;
  padding: 8px 12px;
}
.title {
  text-align: center;
  margin: 4px 0 2px;
}
.subtitle {
  text-align: center;
  color: var(--el-text-color-secondary);
  margin: 0 0 16px;
  font-size: 13px;
}
.submit {
  width: 100%;
}
.error {
  color: var(--el-color-danger);
  font-size: 13px;
  text-align: center;
  margin: 10px 0 0;
}
</style>
