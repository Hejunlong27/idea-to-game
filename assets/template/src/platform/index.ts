/**
 * 平台工厂：按构建模式注入对应适配器。
 *
 * 构建模式由 `vite build --mode <target>` 决定，读取 import.meta.env.MODE。
 * 新增平台 = 新增一个 adapter 文件 + 在这里注册 + 加 build:<name> 脚本，不改玩法代码。
 *
 * 支持的构建目标（与 SKILL.md 的「支持的平台」表保持一致）：
 *   crazygames / poki / gamedistribution / playgama / taptap
 * 未匹配任何目标时使用 mock（仅用于本地开发）。
 */
import type { PlatformBridge } from '../types';
import { createMockPlatform } from './mock';
import { createCrazyGamesPlatform } from './crazygames';
import { createPokiPlatform } from './poki';
import { createPlaygamaPlatform } from './playgama';
import { createGameDistributionPlatform } from './gamedistribution';
import { createTapTapPlatform } from './taptap';

/** 已实现的平台构建目标。新增平台时必须同步更新此列表。 */
export const PLATFORM_TARGETS = [
  'crazygames',
  'poki',
  'gamedistribution',
  'playgama',
  'taptap',
] as const;

export type PlatformTarget = (typeof PLATFORM_TARGETS)[number];

export function createPlatform(): PlatformBridge {
  // ⚠️ 必须用 if 链 + 字面量比较，不要用 switch，也不要对 import.meta.env.MODE 做运算。
  //
  // Vite 会把 import.meta.env.MODE 替换成字符串字面量；Rollup 能折叠 if 的不可达分支，
  // 但**不会**折叠 switch 的不可达 case —— 实测用 switch 会把全部 6 个适配器都打进包体
  // （体积多约 3KB，且产物里同时出现 6 个 i2g-platform:* 标识，污染 precheck 校验）。
  const mode = import.meta.env.MODE as string;
  if (mode === 'crazygames') return createCrazyGamesPlatform();
  if (mode === 'poki') return createPokiPlatform();
  if (mode === 'gamedistribution') return createGameDistributionPlatform();
  if (mode === 'playgama') return createPlaygamaPlatform();
  if (mode === 'taptap') return createTapTapPlatform();
  return createMockPlatform();
}
