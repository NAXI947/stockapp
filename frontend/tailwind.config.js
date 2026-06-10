/** @type {import('tailwindcss').Config} */
export default {
  content: {
    relative: true,
    files: [
      './index.html',
      './src/**/*.{vue,js,ts}'
    ]
  },
  theme: {
    extend: {
      colors: {
        // 股票主题色
        'up': '#ef4444',      // 涨 - 红色
        'down': '#22c55e',    // 跌 - 绿色
        'neutral': '#6b7280', // 中性
        // 背景色
        'bg-primary': '#ffffff',
        'bg-secondary': '#f3f4f6',
        // 边框
        'border': '#e5e7eb'
      }
    }
  },
  plugins: []
}
