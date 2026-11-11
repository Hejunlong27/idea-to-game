import Phaser from 'phaser';

/**
 * Fx —— 程序化特效。
 *
 * ## 为什么单独一个模块
 *
 * 「爽感」= 反馈密度。塔防现在的问题不是画面不好看，是**每个事件都只有一种反馈**：
 * 击杀只有缩放+音效，开火只有一条线，金币只有 HUD 数字变。
 *
 * 这个模块把「事件 → 多层反馈」的映射集中起来，PlayScene 只调一行。
 *
 * ## 为什么全部程序化
 *
 * 特效是**即时反馈**，起音/起效时间必须精确到毫秒。AI 生成的序列帧做不到这个精度，
 * 而且 10 个特效就是 10 组图，体积不可控。Graphics + tween 零素材成本、帧级可控。
 *
 * ## 性能约束
 *
 * - 单次爆发粒子数上限 14，全局同时存活上限约 120
 * - 粒子是 Graphics 画的方块/圆，不用粒子系统（省纹理）
 * - `prefers-reduced-motion` 时自动降级为「只有数字，无粒子」
 */

const MAX_BURST = 14;

export class Fx {
  private scene: Phaser.Scene;
  private reduced: boolean;
  /** 当前存活的粒子数，用于限流 */
  private live = 0;
  private comboText: Phaser.GameObjects.Text | null = null;
  private comboTween: Phaser.Tweens.Tween | null = null;
  private comboTimer: Phaser.Time.TimerEvent | null = null;

  constructor(scene: Phaser.Scene) {
    this.scene = scene;
    this.reduced =
      typeof window !== 'undefined' &&
      !!window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  /** Tween callbacks are the normal cleanup path; scene-clock fallback guarantees a hard lifetime. */
  private destroyAfter(
    object: Phaser.GameObjects.GameObject,
    fallbackMs: number,
    onDestroyed?: () => void,
  ): () => void {
    let timer: Phaser.Time.TimerEvent | null = null;
    let done = false;
    const cleanup = () => {
      if (done) return;
      done = true;
      timer?.remove(false);
      this.scene.tweens.killTweensOf(object);
      if (object.active) object.destroy();
      onDestroyed?.();
    };
    object.once('destroy', () => {
      if (done) return;
      done = true;
      timer?.remove(false);
      onDestroyed?.();
    });
    timer = this.scene.time.delayedCall(fallbackMs, cleanup);
    return cleanup;
  }

  /** 击杀爆裂：碎片向外飞散 + 快速淡出 */
  burst(x: number, y: number, color: number, count = 10): void {
    if (this.reduced) return;
    const n = Math.min(count, MAX_BURST, Math.max(0, 120 - this.live));
    for (let i = 0; i < n; i++) {
      const g = this.scene.add.graphics().setDepth(38);
      g.fillStyle(color, 1);
      const size = 3 + (i % 3) * 2;
      g.fillRect(-size / 2, -size / 2, size, size);
      g.setPosition(x, y);

      const ang = (Math.PI * 2 * i) / n + (i % 5) * 0.3;
      const dist = 26 + (i % 4) * 14;
      this.live += 1;
      const cleanup = this.destroyAfter(g, 520, () => {
        this.live = Math.max(0, this.live - 1);
      });
      this.scene.tweens.add({
        targets: g,
        x: x + Math.cos(ang) * dist,
        y: y + Math.sin(ang) * dist - 8,
        alpha: 0,
        scale: 0.4,
        duration: 260 + (i % 3) * 60,
        ease: 'Quad.easeOut',
        onComplete: cleanup,
      });
    }
  }

  /** 枪口闪光：塔开火时在塔身闪一个短促光圈 */
  muzzle(x: number, y: number, color: number): void {
    if (this.reduced) return;
    const g = this.scene.add.graphics().setDepth(37);
    g.fillStyle(0xffffff, 0.9);
    g.fillCircle(0, 0, 9);
    g.fillStyle(color, 0.6);
    g.fillCircle(0, 0, 15);
    g.setPosition(x, y);
    const cleanup = this.destroyAfter(g, 260);
    this.scene.tweens.add({
      targets: g,
      scale: 1.6,
      alpha: 0,
      duration: 110,
      ease: 'Quad.easeOut',
      onComplete: cleanup,
    });
  }

  /** 命中火花：命中点的小爆点 */
  spark(x: number, y: number, color: number): void {
    if (this.reduced) return;
    const g = this.scene.add.graphics().setDepth(39);
    g.fillStyle(0xffffff, 1);
    g.fillCircle(0, 0, 4);
    g.fillStyle(color, 0.8);
    g.fillCircle(0, 0, 7);
    g.setPosition(x, y);
    const cleanup = this.destroyAfter(g, 300);
    this.scene.tweens.add({
      targets: g,
      scale: 2,
      alpha: 0,
      duration: 140,
      onComplete: cleanup,
    });
  }

  /**
   * 金币飞向 HUD。
   *
   * 这是「击杀有收益」最直观的表达 —— 数字变化玩家注意不到，
   * 一个金色圆点从尸体飞向金币栏，玩家立刻理解「打死 = 有钱」。
   */
  coinFly(x: number, y: number, tx: number, ty: number, onArrive?: () => void): void {
    const g = this.scene.add.graphics().setDepth(41);
    g.fillStyle(0xf0c674, 1);
    g.fillCircle(0, 0, 6);
    g.fillStyle(0xffffff, 0.85);
    g.fillCircle(-2, -2, 2.5);
    g.setPosition(x, y);
    const cleanup = this.destroyAfter(g, 700);

    // 先向上弹一下再飞向目标，比直线更有「掉落物」的感觉
    const midX = (x + tx) / 2;
    const midY = Math.min(y, ty) - 60;
    this.scene.tweens.add({
      targets: g,
      x: midX,
      y: midY,
      duration: 160,
      ease: 'Quad.easeOut',
      onComplete: () => {
        this.scene.tweens.add({
          targets: g,
          x: tx,
          y: ty,
          scale: 0.5,
          duration: 220,
          ease: 'Cubic.easeIn',
          onComplete: () => {
            cleanup();
            onArrive?.();
          },
        });
      },
    });
  }

  /** 全屏闪（漏怪/受击）。用相机 flash，成本极低 */
  flash(color: number, alpha = 0.28, duration = 160): void {
    if (this.reduced) return;
    this.scene.cameras.main.flash(duration, (color >> 16) & 0xff, (color >> 8) & 0xff, color & 0xff, false);
  }

  /** 连杀只保留一个 HUD 提示，连续击杀刷新计数，不在路径上叠字。 */
  combo(n: number): void {
    if (n < 2) return;
    const cam = this.scene.cameras.main;
    const anchorX = cam.width / 2;
    const anchorY = cam.height * 0.16;
    let t = this.comboText;
    if (!t?.active) {
      t = this.scene.add
        .text(anchorX, anchorY, '', {
          fontFamily: 'system-ui, sans-serif',
          fontSize: '28px',
          color: '#ffffff',
          fontStyle: 'bold',
          stroke: '#000000',
          strokeThickness: 3,
        })
        .setOrigin(0.5)
        .setDepth(45);
      this.comboText = t;
    }
    this.comboTween?.stop();
    this.comboTimer?.remove(false);
    t.setPosition(anchorX, anchorY).setText(`${n} 连杀`).setStyle({
      fontSize: `${20 + Math.min(n, 6) * 3}px`,
      color: n >= 5 ? '#ffd166' : '#ffffff',
    }).setAlpha(1).setScale(1);

    const cleanup = () => {
      this.comboTimer?.remove(false);
      this.scene.tweens.killTweensOf(t!);
      if (t!.active) t!.destroy();
      if (this.comboText === t) this.comboText = null;
      this.comboTween = null;
      this.comboTimer = null;
    };
    this.comboTimer = this.scene.time.delayedCall(900, cleanup);
    this.comboTween = this.scene.tweens.add({
      targets: t,
      y: anchorY - 16,
      scale: 1.12,
      alpha: 0,
      duration: 520,
      ease: 'Quad.easeOut',
      onComplete: cleanup,
    });
  }

  /**
   * 波次清空：短暂「停帧感」+ 中心光晕。
   *
   * 不真的暂停（会破坏玩法确定性），只做一个快速缩放脉冲 + 文字，
   * 让玩家感到「喘了口气」。
   */
  waveClear(waveNo: number): void {
    const cam = this.scene.cameras.main;
    if (!this.reduced) {
      cam.zoomTo(1.03, 110, 'Quad.easeOut', true, (_c, p) => {
        if (p === 1) cam.zoomTo(1, 180, 'Quad.easeIn');
      });
    }
    const t = this.scene.add
      .text(cam.width / 2, cam.height * 0.34, `第 ${waveNo} 波清空`, {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '30px',
        color: '#7fe3a8',
        fontStyle: 'bold',
        stroke: '#000000',
        strokeThickness: 4,
      })
      .setOrigin(0.5)
      .setDepth(46)
      .setAlpha(0);

    let timer: Phaser.Time.TimerEvent | null = null;
    const cleanup = () => {
      this.scene.tweens.killTweensOf(t);
      if (t.active) t.destroy();
      timer?.remove(false);
    };
    t.once('destroy', () => timer?.remove(false));
    timer = this.scene.time.delayedCall(1100, cleanup);
    this.scene.tweens.add({
      targets: t,
      alpha: 1,
      scale: 1.1,
      duration: 180,
      yoyo: true,
      hold: 420,
      onComplete: cleanup,
    });
  }

  /** 塔升级：光柱升起 + 扩散环 */
  upgrade(x: number, y: number, color: number): void {
    if (this.reduced) return;
    const ring = this.scene.add.graphics().setDepth(37);
    ring.lineStyle(3, color, 0.9);
    ring.strokeCircle(0, 0, 16);
    ring.setPosition(x, y);
    const cleanupRing = this.destroyAfter(ring, 520);
    this.scene.tweens.add({
      targets: ring,
      scale: 2.4,
      alpha: 0,
      duration: 380,
      ease: 'Quad.easeOut',
      onComplete: cleanupRing,
    });

    const beam = this.scene.add.graphics().setDepth(36);
    beam.fillStyle(color, 0.55);
    beam.fillRect(-5, -70, 10, 70);
    beam.setPosition(x, y);
    const cleanupBeam = this.destroyAfter(beam, 560);
    this.scene.tweens.add({
      targets: beam,
      alpha: 0,
      scaleY: 1.4,
      duration: 420,
      ease: 'Quad.easeOut',
      onComplete: cleanupBeam,
    });
  }

  destroy(): void {
    this.comboTimer?.remove(false);
    this.comboTween?.stop();
    this.comboText?.destroy();
    this.comboTimer = null;
    this.comboTween = null;
    this.comboText = null;
    this.live = 0;
  }
}
