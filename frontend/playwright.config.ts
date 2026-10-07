import { defineConfig, devices } from '@playwright/test';
export default defineConfig({
  testDir:'./tests',timeout:60000,fullyParallel:false,workers:1,
  reporter:[['list'],['html',{open:'never'}]],
  use:{channel:'chromium',baseURL:process.env.APP_URL||'http://localhost:3000',trace:'retain-on-failure',screenshot:'only-on-failure'},
  projects:[{name:'desktop',use:{viewport:{width:1440,height:900}}},{name:'mobile',use:{...devices['iPhone 13'],defaultBrowserType:'chromium'}}],
});
