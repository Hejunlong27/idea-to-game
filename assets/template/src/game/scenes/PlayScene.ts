import Phaser from 'phaser';
import { COLORS, DIFFICULTY, GAME, JUICE, LAYOUT } from '../config';
import { bridge } from '../util';

type Target = Phaser.GameObjects.Image & { bornAt: number; lifetime: number; hit: boolean };

/** 主玩法场景（占位玩法：点击靶子）。执行 modules/04-core-loop.md 时按 GDD 替换。 */
export class PlayScene extends Phaser.Scene {
  private score = 0;
  private combo = 0;
  private targets: Target[] = [];
  private startedAt = 0;
  private spawnAcc = 0;
  private scoreText!: Phaser.GameObjects.Text;
  private timeText!: Phaser.GameObjects.Text;
  private ended = false;

  constructor() {
    super('Play');
  }

  create() {
    const { width: W, height: H } = LAYOUT;
    this.cameras.main.setBackgroundColor(COLORS.bg);
    this.score = 0;
    this.combo = 0;
    this.targets = [];
    this.ended = false;

    this.scoreText = this.add.text(32, 32, '0', {
      fontFamily: 'system-ui, sans-serif',
      fontSize: '64px',
      color: COLORS.text,
      fontStyle: 'bold',
    });

    this.timeText = this.add
      .text(W - 32, 44, '', {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '40px',
        color: COLORS.textDim,
      })
      .setOrigin(1, 0);

    this.startedAt = this.time.now;

    // 平台生命周期：进入可玩状态
    try {
      bridge(this).gameplayStart();
    } catch {
      /* 静默降级 */
    }
  }

  update(time: number, delta: number) {
    if (this.ended) return;

    const elapsed = time - this.startedAt;
    const remain = Math.max(0, GAME.roundMs - elapsed);
    this.timeText.setText(`${(remain / 1000).toFixed(1)}s`);

    if (remain <= 0) {
      this.finish();
      return;
    }

    const step = Math.floor(elapsed / DIFFICULTY.stepMs);
    const lifetime = Math.max(
      DIFFICULTY.minLifetimeMs,
      GAME.targetLifetimeMs * Math.pow(1 - DIFFICULTY.lifetimeDecay, step),
    );
    const interval = Math.max(
      DIFFICULTY.minSpawnMs,
      GAME.spawnIntervalMs * Math.pow(1 - DIFFICULTY.spawnDecay, step),
    );

    this.spawnAcc += delta;
    if (this.spawnAcc >= interval && this.targets.length < GAME.maxTargets) {
      this.spawnAcc = 0;
      this.spawnTarget(lifetime);
    }

    for (const t of [...this.targets]) {
      if (!t.hit && time - t.bornAt > t.lifetime) {
        this.expireTarget(t);
      }
    }
  }

  private spawnTarget(lifetime: number) {
    const { width: W, height: H } = LAYOUT;
    const r = GAME.targetRadius;
    const pad = r + 40;
    const x = Phaser.Math.Between(pad, W - pad);
    const y = Phaser.Math.Between(H * 0.28, H - pad);

    const key = 'ph_target';
    const t = this.add.image(x, y, key) as Target;
    t.setInteractive({ useHandCursor: true });
    t.bornAt = this.time.now;
    t.lifetime = lifetime;
    t.hit = false;
    t.setScale(0.6);
    t.setAlpha(0.98);

    this.tweens.add({ targets: t, scale: 1, duration: JUICE.tweenDurationMs, ease: 'Back.easeOut' });
    t.on('pointerdown', () => this.hitTarget(t));
    this.targets.push(t);
  }

  private hitTarget(t: Target) {
    if (t.hit || this.ended) return;
    t.hit = true;
    this.combo += 1;
    this.score += GAME.scorePerHit + (this.combo - 1) * GAME.comboBonus;
    this.scoreText.setText(String(this.score));

    t.disableInteractive();
    t.setTexture('ph_target_hit');
    this.tweens.add({
      targets: t,
      scale: GAME.hitScalePunch,
      alpha: 0,
      duration: JUICE.tweenDurationMs,
      ease: 'Quad.easeOut',
      onComplete: () => this.removeTarget(t),
    });

    this.cameras.main.shake(JUICE.shakeOnHit.duration, JUICE.shakeOnHit.intensity);
  }

  private expireTarget(t: Target) {
    this.combo = 0;
    t.disableInteractive();
    this.tweens.add({
      targets: t,
      alpha: 0,
      scale: 0.8,
      duration: JUICE.tweenDurationMs,
      onComplete: () => this.removeTarget(t),
    });
    this.cameras.main.shake(JUICE.shakeOnMiss.duration, JUICE.shakeOnMiss.intensity);
  }

  private removeTarget(t: Target) {
    const i = this.targets.indexOf(t);
    if (i >= 0) this.targets.splice(i, 1);
    t.destroy();
  }

  private finish() {
    if (this.ended) return;
    this.ended = true;
    for (const t of [...this.targets]) this.removeTarget(t);

    try {
      bridge(this).gameplayStop();
    } catch {
      /* 静默降级 */
    }

    this.scene.start('GameOver', { score: this.score });
  }
}
