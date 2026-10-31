/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // 色值以 "R G B" 三元组存于 CSS 变量，支持 bg-accent-red/10 这类透明度写法
        surface: {
          1: 'rgb(var(--surface-1) / <alpha-value>)',
          2: 'rgb(var(--surface-2) / <alpha-value>)',
          3: 'rgb(var(--surface-3) / <alpha-value>)',
          4: 'rgb(var(--surface-4) / <alpha-value>)',
        },
        text: 'rgb(var(--text) / <alpha-value>)',
        muted: 'rgb(var(--muted) / <alpha-value>)',
        accent: {
          cyan: 'rgb(var(--accent-cyan) / <alpha-value>)',
          green: 'rgb(var(--accent-green) / <alpha-value>)',
          amber: 'rgb(var(--accent-amber) / <alpha-value>)',
          red: 'rgb(var(--accent-red) / <alpha-value>)',
          purple: 'rgb(var(--accent-purple) / <alpha-value>)',
        },
        // 「熟宣纸」自成一组：纸面 / 纸上的墨色 / 纸纹
        paper: {
          DEFAULT: 'rgb(var(--paper) / <alpha-value>)',
          ink: 'rgb(var(--paper-ink) / <alpha-value>)',
          rule: 'rgb(var(--paper-rule) / <alpha-value>)',
        },
      },
      fontFamily: {
        sans: ['"PingFang SC"', '"Microsoft YaHei"', 'system-ui', 'sans-serif'],
        // 标题与条款序号：宋体系，取公文题签的笔意
        display: ['"STZhongsong"', '"FZXiaoBiaoSong-B05S"', '"SimSun"', '"Noto Serif SC"', 'serif'],
        // 批注与幕僚人设：楷体，像审阅卷上的手笔
        kai: ['"KaiTi"', '"STKaiti"', '"DFKai-SB"', 'serif'],
        mono: ['"JetBrains Mono"', '"Cascadia Mono"', 'Consolas', 'ui-monospace', 'monospace'],
      },
      keyframes: {
        // 押印落下的那一下
        stamp: {
          '0%': { opacity: '0', transform: 'scale(1.8) rotate(8deg)' },
          '60%': { opacity: '1', transform: 'scale(0.94) rotate(-2deg)' },
          '100%': { opacity: '1', transform: 'scale(1) rotate(-2deg)' },
        },
        // 幕僚正在办案时的呼吸灯
        breathe: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.55' },
        },
        // 工作日志逐行浮现
        rise: {
          from: { opacity: '0', transform: 'translateY(6px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        // ── 动效体系：一个动画只承担一种业务语义（模板经 MOTION 常量引用）──
        // 落定：结论被采信，能量底扩收敛成稳定色条
        settle: {
          '0%': { transform: 'scaleY(3)', opacity: '0.7' },
          '100%': { transform: 'scaleY(1)', opacity: '1' },
        },
        // 退后：旧结论降饱和淡化
        recede: {
          '0%': { opacity: '1', filter: 'saturate(1)' },
          '100%': { opacity: '0.55', filter: 'saturate(0.35)' },
        },
        // 下坠：驳回条目下沉去饱和
        fall: {
          '0%': { transform: 'translateY(0)', opacity: '1', filter: 'saturate(1)' },
          '100%': { transform: 'translateY(6px)', opacity: '0.6', filter: 'saturate(0.5)' },
        },
        // 警示脉冲：降级角标的扩散环
        alert: {
          '0%': { boxShadow: '0 0 0 0 rgb(var(--accent-amber) / 0.55)' },
          '100%': { boxShadow: '0 0 0 10px rgb(var(--accent-amber) / 0)' },
        },
        // 换面：复核三态绕横轴翻转转正
        flip: {
          '0%': { transform: 'rotateX(-90deg)', opacity: '0' },
          '100%': { transform: 'rotateX(0deg)', opacity: '1' },
        },
        // 推挤插入：新增记录挤开下方列表
        push: {
          '0%': { transform: 'translateY(-8px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        // 光标闪烁：核阅进行中行尾游标
        caret: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0' },
        },
        // 定位扫描：目录跳转时在目标条款上罩一圈青环
        scan: {
          '0%, 100%': { boxShadow: '0 0 0 0 rgb(var(--accent-cyan) / 0)' },
          '30%': { boxShadow: '0 0 0 4px rgb(var(--accent-cyan) / 0.6)' },
          '70%': { boxShadow: '0 0 0 4px rgb(var(--accent-cyan) / 0.25)' },
        },
        // 命中闪烁：朱笔圈注处红环双闪
        flash: {
          '0%, 100%': { boxShadow: '0 0 0 0 rgb(var(--accent-red) / 0)' },
          '20%, 60%': { boxShadow: '0 0 0 4px rgb(var(--accent-red) / 0.55)' },
          '40%': { boxShadow: '0 0 0 4px rgb(var(--accent-red) / 0.2)' },
        },
        // 表格行横扫：渐变光带沿 background-position 从左掠到右（配 .sweep-band）
        sweep: {
          '0%': { backgroundPosition: '-60% 0' },
          '100%': { backgroundPosition: '260% 0' },
        },
        // 显影：批注内容由虚焦淡入成形
        develop: {
          '0%': { opacity: '0', filter: 'blur(6px)' },
          '100%': { opacity: '1', filter: 'blur(0)' },
        },
      },
      animation: {
        stamp: 'stamp 0.5s cubic-bezier(0.22, 1, 0.36, 1) both',
        breathe: 'breathe 2.2s ease-in-out infinite',
        rise: 'rise 0.4s ease-out both',
        settle: 'settle 0.6s cubic-bezier(0.22, 1, 0.36, 1) both',
        recede: 'recede 0.7s ease-out forwards',
        fall: 'fall 0.5s ease-out forwards',
        alert: 'alert 1.2s ease-out 2',
        flip: 'flip 0.35s ease-out both',
        push: 'push 0.45s cubic-bezier(0.22, 1, 0.36, 1) both',
        caret: 'caret 1s steps(1) infinite',
        scan: 'scan 1.2s ease-out 1',
        flash: 'flash 0.8s ease-out 1',
        sweep: 'sweep 0.6s ease-out 1',
        develop: 'develop 0.5s ease-out both',
      },
      boxShadow: {
        // 能量青外发光：深色面板 hover / 拓扑节点用（lift 抬升时提亮）
        glow: '0 0 24px rgb(var(--accent-cyan) / 0.25)',
        'glow-sm': '0 0 12px rgb(var(--accent-cyan) / 0.2)',
      },
    },
  },
  plugins: [],
}
