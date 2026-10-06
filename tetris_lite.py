"""tetris-lite: 迷你俄罗斯方块引擎 + 自动游玩演示。

纯标准库，无实时输入：核心是可测试的游戏引擎，
`--auto` 用简单启发式自动放置方块做无头演示。
"""

from __future__ import annotations

import argparse
import random
import sys

W, H = 10, 20  # 场地宽高

# 七种四联方块，用格子坐标定义（相对原点）
BASE_SHAPES = {
    "I": [(0, 0), (0, 1), (0, 2), (0, 3)],
    "O": [(0, 0), (0, 1), (1, 0), (1, 1)],
    "T": [(0, 0), (0, 1), (0, 2), (1, 1)],
    "S": [(0, 1), (0, 2), (1, 0), (1, 1)],
    "Z": [(0, 0), (0, 1), (1, 1), (1, 2)],
    "J": [(0, 0), (1, 0), (1, 1), (1, 2)],
    "L": [(0, 2), (1, 0), (1, 1), (1, 2)],
}

SCORES = {1: 100, 2: 300, 3: 500, 4: 800}


def rotate_cells(cells):
    """顺时针旋转 90°，并归一化到原点。返回排序后的格子列表。"""
    rotated = [(c, -r) for r, c in cells]
    min_r = min(r for r, _ in rotated)
    min_c = min(c for _, c in rotated)
    return sorted((r - min_r, c - min_c) for r, c in rotated)


def rotation_states(shape):
    """返回一个方块去重后的全部旋转状态（O 只有 1 个，I/S/Z 有 2 个）。"""
    states, seen = [], set()
    cells = list(shape)
    for _ in range(4):
        cells = rotate_cells(cells)
        key = tuple(cells)
        if key in seen:
            break
        seen.add(key)
        states.append(list(cells))
    return states


# 预计算全部旋转状态
SHAPES = {name: rotation_states(shape) for name, shape in BASE_SHAPES.items()}
PIECES = list(SHAPES)  # ["I","O","T","S","Z","J","L"]


class Game:
    def __init__(self, seed=None):
        self.rng = random.Random(seed)
        self.board = [[0] * W for _ in range(H)]
        self.bag = []
        self.piece = None      # (name, rot_idx, row, col)
        self.score = 0
        self.lines = 0
        self.pieces_placed = 0
        self.over = False

    # ---------- 内部 ----------
    def _next_piece(self):
        if not self.bag:
            self.bag = PIECES[:]
            self.rng.shuffle(self.bag)
        return self.bag.pop()

    def _collides(self, cells, row, col):
        for r, c in cells:
            rr, cc = row + r, col + c
            if cc < 0 or cc >= W or rr >= H:
                return True
            if rr >= 0 and self.board[rr][cc]:
                return True
        return False

    # ---------- 对外 ----------
    def spawn(self):
        name = self._next_piece()
        cells = SHAPES[name][0]
        width = max(c for _, c in cells) + 1
        row, col = 0, (W - width) // 2
        if self._collides(cells, row, col):
            self.over = True
            self.piece = None
            return False
        self.piece = [name, 0, row, col]
        return True

    def move(self, dr, dc):
        """尝试移动当前方块，成功返回 True。"""
        name, rot, row, col = self.piece
        cells = SHAPES[name][rot]
        if not self._collides(cells, row + dr, col + dc):
            self.piece[2] += dr
            self.piece[3] += dc
            return True
        return False

    def rotate(self):
        name, rot, row, col = self.piece
        nrot = (rot + 1) % len(SHAPES[name])
        cells = SHAPES[name][nrot]
        if not self._collides(cells, row, col):
            self.piece[1] = nrot
            return True
        # 简单踢墙：左右各试一格
        for dc in (-1, 1, -2, 2):
            if not self._collides(cells, row, col + dc):
                self.piece[1] = nrot
                self.piece[3] += dc
                return True
        return False

    def lock(self):
        """把当前方块固定到场地，消行计分。返回消除的行数。"""
        name, rot, row, col = self.piece
        for r, c in SHAPES[name][rot]:
            rr, cc = row + r, col + c
            if rr >= 0:
                self.board[rr][cc] = 1
        self.piece = None
        self.pieces_placed += 1
        cleared = 0
        kept = []
        for line in self.board:
            if all(line):
                cleared += 1
            else:
                kept.append(line)
        while len(kept) < H:
            kept.insert(0, [0] * W)
        self.board = kept
        if cleared:
            self.lines += cleared
            self.score += SCORES[cleared]
        return cleared

    def step(self):
        """重力走一步：能下就下，否则锁定并生成新块。"""
        if self.over:
            return
        if self.piece is None:
            self.spawn()
            return
        if not self.move(1, 0):
            self.lock()
            if not self.over:
                self.spawn()

    def hard_drop(self):
        while self.piece and self.move(1, 0):
            pass
        if self.piece:
            self.lock()
            if not self.over:
                self.spawn()

    # ---------- 启发式自动游玩 ----------
    def _simulate(self, name, rot, col):
        """在拷贝场地上试放，返回 (board_after, lines_cleared)。"""
        cells = SHAPES[name][rot]
        width = max(c for _, c in cells) + 1
        if col < 0 or col + width > W:
            return None
        board = [row[:] for row in self.board]
        row = 0
        while not self._collides_on(board, cells, row + 1, col):
            row += 1
        for r, c in cells:
            rr = row + r
            if rr < 0:
                return None  # 冒顶
            board[rr][col + c] = 1
        cleared = sum(1 for line in board if all(line))
        board = [line for line in board if not all(line)]
        while len(board) < H:
            board.insert(0, [0] * W)
        return board, cleared

    def _collides_on(self, board, cells, row, col):
        for r, c in cells:
            rr, cc = row + r, col + c
            if cc < 0 or cc >= W or rr >= H:
                return True
            if rr >= 0 and board[rr][cc]:
                return True
        return False

    @staticmethod
    def _evaluate(board, cleared):
        heights = []
        holes = 0
        for c in range(W):
            h = 0
            seen_block = False
            for r in range(H):
                if board[r][c]:
                    if not seen_block:
                        h = H - r
                        seen_block = True
                elif seen_block:
                    holes += 1
            heights.append(h)
        agg = sum(heights)
        bump = sum(abs(heights[i] - heights[i + 1]) for i in range(W - 1))
        # 权重：尽量矮、少洞、平坦，多消行大奖励
        return -0.51 * agg - 0.36 * holes - 0.18 * bump + 8.0 * cleared

    def auto_move(self):
        """为当前方块选最优 (旋转, 列)，硬降。返回是否成功放置。"""
        if self.over or self.piece is None:
            return False
        name = self.piece[0]
        best, best_key = None, None
        for rot in range(len(SHAPES[name])):
            cells = SHAPES[name][rot]
            width = max(c for _, c in cells) + 1
            for col in range(W - width + 1):
                sim = self._simulate(name, rot, col)
                if sim is None:
                    continue
                board_after, cleared = sim
                key = self._evaluate(board_after, cleared)
                if best_key is None or key > best_key:
                    best_key = key
                    best = (rot, col)
        if best is None:
            self.over = True
            return False
        rot, col = best
        self.piece[1] = rot
        self.piece[3] = col
        self.hard_drop()
        return True

    def auto_play(self, n_pieces):
        self.spawn()
        for _ in range(n_pieces):
            if self.over:
                break
            if not self.auto_move():
                break
        return self


def render(game, show_piece=True):
    """文本渲染场地。"""
    grid = [row[:] for row in game.board]
    if show_piece and game.piece:
        name, rot, row, col = game.piece
        for r, c in SHAPES[name][rot]:
            rr, cc = row + r, col + c
            if 0 <= rr < H and 0 <= cc < W:
                grid[rr][cc] = 2
    out = ["+" + "-" * (W * 2) + "+"]
    for line in grid:
        out.append("|" + "".join("##" if v == 1 else "@@" if v == 2 else "  " for v in line) + "|")
    out.append("+" + "-" * (W * 2) + "+")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tetris-lite", description="迷你俄罗斯方块引擎 + 自动演示")
    ap.add_argument("--auto", action="store_true", help="自动游玩演示")
    ap.add_argument("--pieces", type=int, default=50, help="自动游玩的方块数（默认 50）")
    ap.add_argument("--seed", type=int, default=None, help="随机种子")
    args = ap.parse_args(argv)

    if not args.auto:
        ap.print_help()
        print("\n提示：目前只有 --auto 无头演示模式（无实时键盘输入）。")
        return 0

    game = Game(seed=args.seed).auto_play(args.pieces)
    print(render(game))
    print(f"\n方块数：{game.pieces_placed}  消除行：{game.lines}  得分：{game.score}")
    print("游戏结束（堆满）" if game.over else "演示完成（未堆满）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
