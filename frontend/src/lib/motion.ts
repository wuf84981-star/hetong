/**
 * 动效体系常量：一个动画只承担一种业务语义。
 * 模板中禁止裸写 animate-* / hover 抬升类名，一律引用这里的常量。
 * keyframes 注册见 tailwind.config.js；reduced-motion 全局降级见 index.css。
 */
export const MOTION = {
  /** 落定：结论被采信（能量底扩收敛成稳定色条） */
  settle: 'origin-bottom animate-settle',
  /** 退后：旧结论降饱和淡化 */
  recede: 'animate-recede',
  /** 下坠：驳回条目下沉去饱和 */
  fall: 'animate-fall',
  /** 警示脉冲：降级角标扩散环 */
  alert: 'animate-alert',
  /** 换面：复核三态绕横轴翻转转正（父级需 perspective） */
  flip: 'animate-flip',
  /** 推挤插入：新增记录挤开下方列表 */
  push: 'animate-push',
  /** 光标闪烁：核阅进行中行尾游标 */
  caret: 'animate-caret',
  /** 定位扫描：目录跳转目标条款的青环 */
  scan: 'animate-scan',
  /** 命中闪烁：朱笔圈注处的红环双闪 */
  flash: 'animate-flash',
  /** 表格行横扫：光带沿 background-position 掠过（元素需叠 .sweep-band） */
  sweep: 'hover:animate-sweep',
  /** 悬停抬升：卡片微抬 + 边框提亮 + 柔和外发光 */
  lift: 'transition-[transform,border-color,box-shadow] duration-300 hover:-translate-y-0.5 hover:shadow-glow',
  /** 显影：批注内容由虚焦淡入成形 */
  develop: 'animate-develop',
  /** ── 案头批注遗产（非 12 语义，装饰用途）── */
  /** 押印落章 */
  stamp: 'animate-stamp',
  /** 办案呼吸灯 */
  breathe: 'animate-breathe',
  /** 工作日志逐行浮现 */
  rise: 'animate-rise',
  /** 加载旋转（工具性 affordance，非业务语义动画） */
  spin: 'animate-spin',
} as const
