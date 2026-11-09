import { GRID } from './config';

/**
 * 塔防纯逻辑 —— 不碰 Phaser，不碰渲染，也不持有任何全局关卡数据。
 *
 * 为什么全部参数化（path 由调用方传进来）：
 *   1. 多关卡时同一套函数要服务不同地图，不能读全局 PATH；
 *   2. 纯函数可以被单测（不需要浏览器），也能被测试 adapter 直接复用；
 *   3. 换地图只改 config.ts 的 LEVELS，本文件不动。
 */

export interface Pt {
  c: number;
  r: number;
}

/** 格子键，用于 Set/Map 去重 */
export function cellKey(c: number, r: number): string {
  return `${c},${r}`;
}

/** 格子是否在网格内 */
export function inGrid(c: number, r: number): boolean {
  return c >= 0 && r >= 0 && c < GRID.cols && r < GRID.rows;
}

/**
 * 路径经过的所有格子。
 *
 * path 是折线顶点，相邻顶点必须共线（只能横或竖），这里逐格展开。
 * 用 Set 而不是数组：查询「这一格是不是路」是每帧都要做的事。
 */
export function buildPathCells(path: Array<[number, number]>): Set<string> {
  const cells = new Set<string>();
  for (let i = 0; i < path.length - 1; i++) {
    const [c0, r0] = path[i];
    const [c1, r1] = path[i + 1];
    const dc = Math.sign(c1 - c0);
    const dr = Math.sign(r1 - r0);
    if (dc !== 0 && dr !== 0) {
      throw new Error(`path 第 ${i} 段不是横竖直线：(${c0},${r0}) → (${c1},${r1})`);
    }
    let c = c0;
    let r = r0;
    cells.add(cellKey(c, r));
    while (c !== c1 || r !== r1) {
      c += dc;
      r += dr;
      cells.add(cellKey(c, r));
    }
  }
  return cells;
}

/** 可建造判定：网格内、不是路径格、不是基地 */
export function isBuildable(
  pathCells: Set<string>,
  base: [number, number],
  c: number,
  r: number,
): boolean {
  if (!inGrid(c, r)) return false;
  if (pathCells.has(cellKey(c, r))) return false;
  if (c === base[0] && r === base[1]) return false;
  return true;
}

/** 格子中心像素坐标 */
export function cellCenter(c: number, r: number): { x: number; y: number } {
  return {
    x: GRID.originX + c * GRID.cell + GRID.cell / 2,
    y: GRID.originY + r * GRID.cell + GRID.cell / 2,
  };
}

/** 像素坐标 → 格子。落在网格外返回 null。 */
export function cellAt(x: number, y: number): Pt | null {
  const c = Math.floor((x - GRID.originX) / GRID.cell);
  const r = Math.floor((y - GRID.originY) / GRID.cell);
  return inGrid(c, r) ? { c, r } : null;
}

/** 路径总长度（单位：格）。用于判断敌人是否到达基地。 */
export function totalPathDist(path: Array<[number, number]>): number {
  let total = 0;
  for (let i = 0; i < path.length - 1; i++) {
    total += Math.abs(path[i + 1][0] - path[i][0]) + Math.abs(path[i + 1][1] - path[i][1]);
  }
  return total;
}

/**
 * 走了 `dist` 格之后的**朝向**（单位向量）。
 *
 * 用途：同一位置有多个敌人时，按朝向的垂直方向错开渲染，
 * 否则它们会完全重合，玩家数不清有几个。纯视觉，不影响玩法（碰撞用 dist）。
 */
export function pathDirAt(path: Array<[number, number]>, dist: number): { x: number; y: number } {
  let remain = Math.max(0, dist);
  for (let i = 0; i < path.length - 1; i++) {
    const [c0, r0] = path[i];
    const [c1, r1] = path[i + 1];
    const segLen = Math.abs(c1 - c0) + Math.abs(r1 - r0);
    if (segLen === 0) continue;
    if (remain <= segLen) {
      const dx = Math.sign(c1 - c0);
      const dy = Math.sign(r1 - r0);
      return { x: dx, y: dy };
    }
    remain -= segLen;
  }
  const a = path[path.length - 2];
  const b = path[path.length - 1];
  return { x: Math.sign(b[0] - a[0]), y: Math.sign(b[1] - a[1]) };
}

/**
 * 走了 `dist` 格之后的世界坐标。
 *
 * 敌人位置用「已走格数」而不是像素存：像素依赖 cell 尺寸，
 * 换分辨率就失效；格数是玩法量纲，断言和存档都用它。
 */
export function pathPointAt(path: Array<[number, number]>, dist: number): { x: number; y: number } {
  let remain = Math.max(0, dist);
  for (let i = 0; i < path.length - 1; i++) {
    const [c0, r0] = path[i];
    const [c1, r1] = path[i + 1];
    const segLen = Math.abs(c1 - c0) + Math.abs(r1 - r0);
    if (segLen === 0) continue;
    if (remain <= segLen) {
      const t = remain / segLen;
      return cellCenter(c0 + (c1 - c0) * t, r0 + (r1 - r0) * t);
    }
    remain -= segLen;
  }
  const last = path[path.length - 1];
  return cellCenter(last[0], last[1]);
}
