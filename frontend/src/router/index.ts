import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
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

export default router
