/**
 * 平台工厂：按构建模式注入对应适配器。
 *
 * 构建模式由 `vite build --mode <target>` 决定，读取 import.meta.env.MODE。
 * 新增平台 = 新增一个 adapter 文件 + 在这里注册，不改玩法代码。
 */
import type { PlatformBridge } from '../types';
import { createMockPlatform } from './mock';
import { createCrazyGamesPlatform } from './crazygames';
import { createPokiPlatform } from './poki';
import { createPlaygamaPlatform } from './playgama';
import { createGameDistributionPlatform } from './gamedistribution';

export function createPlatform(): PlatformBridge {
  const mode = (import.meta.env.MODE || 'development').toLowerCase();

  switch (mode) {
    case 'crazygames':
      return createCrazyGamesPlatform();
    case 'poki':
      return createPokiPlatform();
    case 'playgama':
      return createPlaygamaPlatform();
    case 'gamedistribution':
      return createGameDistributionPlatform();
    default:
      return createMockPlatform();
  }
}
