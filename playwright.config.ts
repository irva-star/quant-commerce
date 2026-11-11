import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir:'./e2e',fullyParallel:false,workers:1,timeout:90_000,
  use:{baseURL:'http://127.0.0.1:5173',headless:true,viewport:{width:1512,height:1100},screenshot:'only-on-failure',trace:'retain-on-failure'},
  webServer:[
    {command:'npm run api',url:'http://127.0.0.1:8000/api/health',reuseExistingServer:true,timeout:30_000},
    {command:'npm run dev -- --strictPort',url:'http://127.0.0.1:5173',reuseExistingServer:true,timeout:30_000},
  ],
});
