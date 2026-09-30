import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: () => import('../views/Login.vue'),
    },
    {
      path: '/',
      name: 'Dashboard',
      component: () => import('../views/Dashboard.vue'),
    },
    {
      path: '/workspace',
      name: 'CaseWorkspace',
      component: () => import('../views/CaseWorkspace.vue'),
    },
    {
      path: '/report',
      name: 'Report',
      component: () => import('../views/Report.vue'),
    },
    {
      path: '/sessions',
      name: 'Sessions',
      component: () => import('../views/Sessions.vue'),
    },
    {
      path: '/knowledge',
      name: 'KnowledgeBase',
      component: () => import('../views/KnowledgeBase.vue'),
    },
  ],
})

// 未登录一律先到登录页；是否真的已登录由后端 Cookie 决定（401 拦截器兜底踢回）
router.beforeEach((to) => {
  if (to.name === 'Login') return true
  if (!localStorage.getItem('martin_doctor')) return { name: 'Login' }
  return true
})

export default router
