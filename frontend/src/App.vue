<template>
  <el-container class="app-shell">
    <el-aside class="desktop-nav" width="216px">
      <div class="brand-block">
        <strong>Martin</strong>
        <span>临床影像工作站</span>
      </div>
      <el-menu
        :default-active="$route.path"
        router
        background-color="#17212b"
        text-color="#d7dee6"
        active-text-color="#41c58a"
      >
        <el-menu-item index="/">工作台</el-menu-item>
        <el-menu-item index="/workspace">影像分析</el-menu-item>
        <el-menu-item index="/report">报告</el-menu-item>
        <el-menu-item index="/sessions">病例记录</el-menu-item>
        <el-menu-item index="/knowledge">知识库</el-menu-item>
      </el-menu>
    </el-aside>

    <el-container class="content-shell">
      <header class="mobile-header">
        <button class="menu-button" type="button" aria-label="打开导航" @click="mobileNavOpen = true">
          &#9776;
        </button>
        <div>
          <strong>Martin</strong>
          <span>临床影像工作站</span>
        </div>
      </header>
      <el-main class="app-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>

  <el-drawer v-model="mobileNavOpen" direction="ltr" size="min(82vw, 280px)" :with-header="false">
    <div class="drawer-brand">Martin 临床影像工作站</div>
    <el-menu :default-active="$route.path" @select="handleMobileNavigate">
      <el-menu-item index="/">工作台</el-menu-item>
      <el-menu-item index="/workspace">影像分析</el-menu-item>
      <el-menu-item index="/report">报告</el-menu-item>
      <el-menu-item index="/sessions">病例记录</el-menu-item>
      <el-menu-item index="/knowledge">知识库</el-menu-item>
    </el-menu>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const mobileNavOpen = ref(false)

function handleMobileNavigate(path: string) {
  mobileNavOpen.value = false
  router.push(path)
}
</script>

<style>
:root {
  color: #17212b;
  background: #edf1f4;
  font-family: Inter, "Microsoft YaHei", Arial, sans-serif;
}

* {
  box-sizing: border-box;
}

html,
body,
#app {
  width: 100%;
  min-width: 320px;
  height: 100%;
  margin: 0;
}

body {
  overflow: hidden;
}

.app-shell {
  height: 100vh;
  background: #edf1f4;
}

.desktop-nav {
  background: #101b27;
  border-right: 1px solid #0b131d;
}

.brand-block {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 28px 22px 24px;
  color: #ffffff;
}

.brand-block strong {
  letter-spacing: -0.02em;
  font-size: 23px;
}

.brand-block span {
  color: #9fb0bf;
  font-size: 12px;
}

.desktop-nav .el-menu {
  border-right: 0;
}

.content-shell {
  min-width: 0;
  flex-direction: column;
}

.app-main {
  min-width: 0;
  padding: 18px 22px 22px;
  overflow: auto;
}

.mobile-header {
  display: none;
}

.drawer-brand {
  padding: 12px 20px 20px;
  font-size: 18px;
  font-weight: 700;
}

@media (max-width: 820px) {
  body {
    overflow: auto;
  }

  .desktop-nav {
    display: none;
  }

  .mobile-header {
    display: flex;
    align-items: center;
    gap: 12px;
    min-height: 58px;
    padding: 8px 14px;
    color: #ffffff;
    background: #101b27;
  }

  .mobile-header > div {
    display: flex;
    flex-direction: column;
  }

  .mobile-header span {
    color: #b8c4cf;
    font-size: 11px;
  }

  .menu-button {
    width: 38px;
    height: 38px;
    padding: 0;
    color: #ffffff;
    font-size: 22px;
    line-height: 1;
    background: transparent;
    border: 1px solid #52616f;
    border-radius: 6px;
    cursor: pointer;
  }

  .app-main {
    padding: 14px;
  }
}
</style>
