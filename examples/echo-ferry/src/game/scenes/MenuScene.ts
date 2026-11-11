import Phaser from 'phaser';
import { COLORS, LAYOUT } from '../config';
import { TEXTURES } from '../art';
import { readSaveWhenReady } from '../util';

/** 菜单：一句话说明玩法，一个按钮开始。首屏到可玩必须 <3 秒。 */
export class MenuScene extends Phaser.Scene {
  constructor() {
    super('Menu');
  }

  create() {
    const { width: W, height: H } = LAYOUT;
    this.cameras.main.setBackgroundColor(COLORS.bg);

    // AI 生成的雾海背景（混合美术：背景用 AI，UI 与地块保持程序化）
    if (this.textures.exists(TEXTURES.bg)) {
      this.add.image(W / 2, H / 2, TEXTURES.bg).setDisplaySize(W, H).setDepth(-10).setAlpha(0.9);
      // 压暗一层，保证文字可读（对比度是硬指标，不能靠背景凑）
      this.add.rectangle(0, 0, W, H, COLORS.bg, 0.55).setOrigin(0).setDepth(-9);
    }

    // 背景：几条缓慢漂移的水纹（environmental 动画，不参与玩法）
    for (let i = 0; i < 5; i++) {
      const y = 140 + i * 220;
      const line = this.add.rectangle(0, y, W, 2, COLORS.waterLine, 0.5).setOrigin(0, 0.5);
      this.tweens.add({
        targets: line,
        x: -40,
        duration: 6000 + i * 900,
        yoyo: true,
        repeat: -1,
        ease: 'Sine.easeInOut',
      });
    }

    this.add
      .text(W / 2, H * 0.24, '回声摆渡', {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '72px',
        color: COLORS.text,
        fontStyle: 'bold',
      })
      .setOrigin(0.5);

    this.add
      .text(W / 2, H * 0.24 + 72, '你发出一声，世界亮一瞬', {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '26px',
        color: COLORS.textDim,
      })
      .setOrigin(0.5);

    this.add
      .text(
        W / 2,
        H * 0.44,
        '雾海上没有方向，只有回声。\n敲钟能看见一瞬，也会被黑暗听见。\n亮过的地方会留下残影 —— 而残影会腐烂。\n\n把灵魂送上岸，别用光最后一格记忆。',
        {
          fontFamily: 'system-ui, sans-serif',
          fontSize: '24px',
          color: COLORS.textDim,
          align: 'center',
          lineSpacing: 12,
        },
      )
      .setOrigin(0.5);

    const bestLabel = this.add
      .text(W / 2, H * 0.62, '最远送到 … 个灵魂', {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '24px',
        color: COLORS.text,
      })
      .setOrigin(0.5);

    const btn = this.add
      .rectangle(W / 2, H * 0.74, 400, 108, COLORS.accent, 0.14)
      .setStrokeStyle(2, COLORS.accent, 0.95);
    const label = this.add
      .text(W / 2, H * 0.74, '划出去', {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '38px',
        color: COLORS.text,
        fontStyle: 'bold',
      })
      .setOrigin(0.5);

    btn.setInteractive({ useHandCursor: true });
    const start = () => this.scene.start('Play', { level: 0 });
    btn.on('pointerdown', start);
    label.setInteractive({ useHandCursor: true }).on('pointerdown', start);
    this.input.keyboard?.once('keydown-SPACE', start);
    this.input.keyboard?.once('keydown-ENTER', start);

    this.tweens.add({
      targets: [btn, label],
      alpha: 0.82,
      duration: 1200,
      yoyo: true,
      repeat: -1,
      ease: 'Sine.easeInOut',
    });

    this.add
      .text(W / 2, H - 56, '方向键 / WASD 划船　空格 敲钟　也可直接点相邻格', {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '18px',
        color: COLORS.textDim,
      })
      .setOrigin(0.5);

    // 进度展示是增强信息，不阻塞开始入口；create() 仍然同步返回。
    readSaveWhenReady(this, (save) => {
      bestLabel.setText(`最远送到 ${save.best} 个灵魂`);
    });
  }
}
