import Phaser from 'phaser';
import { createPlatform } from './platform';
import { gameConfig } from './game';

/**
 * 入口。
 * 1. 创建平台适配器并初始化（失败自动降级，不阻塞启动）
 * 2. 启动 Phaser
 * 3. 把适配器注入 registry，供各场景通过 src/game/util.ts 读取
 * 4. 处理 iOS 音频恢复与切后台
 */
async function bootstrap() {
  const platform = createPlatform();

  // 平台初始化失败不得阻塞游戏启动
  await platform.init().catch((e) => {
    console.warn('[main] 平台初始化失败，以本地模式继续', e);
  });

  const game = new Phaser.Game(gameConfig());

  // 场景通过 registry 取平台实例，避免 src/game/ 依赖 src/platform/
  game.registry.set('platform', platform);

  installAudioRecovery(game);
  installVisibilityHandling(game, platform);
}

/**
 * iOS 会把 AudioContext 置为 interrupted/suspended。
 * 必须在用户手势回调内 resume —— 只监听 visibilitychange 无效。
 * 参考: https://docs.crazygames.com/requirements/technical/
 */
function installAudioRecovery(game: Phaser.Game) {
  const resume = () => {
    const ctx = (game.sound as unknown as { context?: AudioContext }).context;
    if (ctx && ctx.state === 'suspended') {
      void ctx.resume();
    }
  };
  document.addEventListener('touchend', resume, { passive: true });
  document.addEventListener('click', resume);
  document.addEventListener('keydown', resume);
}

/** 切后台时暂停音频并上报 gameplayStop，回来时恢复。 */
function installVisibilityHandling(game: Phaser.Game, platform: { gameplayStop(): void; gameplayStart(): void }) {
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      try {
        game.sound.pauseAll();
      } catch {
        /* 静默降级 */
      }
      try {
        platform.gameplayStop();
      } catch {
        /* 静默降级 */
      }
    } else {
      try {
        game.sound.resumeAll();
      } catch {
        /* 静默降级 */
      }
    }
  });
}

void bootstrap();
