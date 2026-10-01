# -*- coding: utf-8 -*-
"""
USINA - jogo de plataforma + puzzles (pygame)

Estrutura de pastas (tudo na MESMA pasta do jogo.py):
    jogo.py
    assets/
        cenario_destruido.jpg   (cenário 1 - tudo destruído)
        cenario_meio.jpg        (cenário 2 - só o fogo restante; opcional, não usado)
        cenario_consertado.jpg  (cenário 3 - tudo consertado)
        sprites_normal.png      (sprite sheet do protagonista de moletom)
        sprites_equipado.png    (sprite sheet com o equipamento)

Controles:
    A / D ......... andar esquerda / direita
    ESPAÇO ........ pular
    E ............. interagir (armário, iniciar puzzles)
    MOUSE ......... usado dentro dos puzzles
    ESC ........... sair do puzzle (= desistir = morrer) / fechar jogo
    R ............. reiniciar na tela de Game Over (ou clique no botão)
"""
import os
import sys
import math
import random
import pygame

# ----------------------------------------------------------------------------
# CONFIGURAÇÕES
# ----------------------------------------------------------------------------
W, H = 1280, 700
FPS = 60
BASE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(BASE, "assets")

GROUND_Y = int(H * 0.915)         # linha dos pés do personagem (chão do cenário)
PLAYER_SCALE = 1.35               # tamanho do personagem
MOVE_SPEED = 300                  # px/s
JUMP_SPEED = 720                  # px/s
GRAVITY = 2100                    # px/s²
X_MIN, X_MAX = int(W * 0.07), int(W * 0.95)

# Zonas (em fração da largura) -----------------------------------------------
ZONES = {
    "pipe":  (0.03, 0.27),   # puzzle 1 - canos (esquerda)
    "panel": (0.40, 0.66),   # puzzle 2 - painel elétrico (centro)
    "fire":  (0.78, 0.97),   # puzzle 3 - gerador em chamas (direita)
}
LOCKER_X = int(W * 0.335)      # centro do armário

# Regiões do cenário que "ficam consertadas" (frações x0,y0,x1,y1)
PATCH_RECTS = {
    "pipe":  (0.00, 0.33, 0.30, 1.00),
    "panel": (0.36, 0.40, 0.71, 0.93),
    "fire":  (0.755, 0.00, 1.00, 0.86),
}

# Cores
WHITE = (240, 240, 240)
BLACK = (10, 10, 14)
GRAY = (70, 74, 84)
DGRAY = (34, 36, 44)
RED = (220, 60, 50)
GREEN = (70, 210, 110)
YELLOW = (245, 200, 60)
BLUE = (70, 150, 240)
ORANGE = (240, 140, 50)

WIRE_COLORS = [
    ("Vermelho", (220, 50, 50)),
    ("Azul", (60, 110, 240)),
    ("Verde", (50, 200, 90)),
    ("Amarelo", (240, 210, 50)),
    ("Laranja", (245, 140, 40)),
    ("Roxo", (150, 80, 220)),
    ("Rosa", (240, 120, 190)),
    ("Ciano", (60, 220, 230)),
    ("Branco", (235, 235, 235)),
    ("Marrom", (150, 95, 55)),
]


# ----------------------------------------------------------------------------
# UTILIDADES
# ----------------------------------------------------------------------------
def load_img(name, alpha=True):
    path = os.path.join(ASSETS, name)
    img = pygame.image.load(path)
    return img.convert_alpha() if alpha else img.convert()


def spans(flags):
    """Transforma uma lista de booleanos em intervalos [(ini, fim), ...]."""
    out, start = [], None
    for i, v in enumerate(flags):
        if v and start is None:
            start = i
        elif not v and start is not None:
            out.append((start, i))
            start = None
    if start is not None:
        out.append((start, len(flags)))
    return out


def slice_sheet(sheet):
    """
    Fatia o sprite sheet automaticamente usando a transparência.
    Retorna lista de linhas; cada linha é uma lista de Surfaces.
    Linha 0: parado | 1: andar | 2: pular | 3: agachar/interagir
    """
    w, h = sheet.get_size()
    row_occ = [False] * h
    col_occ = [[False] * w for _ in range(h)]  # evita recalcular
    for y in range(h):
        for x in range(w):
            if sheet.get_at((x, y)).a > 20:
                row_occ[y] = True
                col_occ[y][x] = True
    rows = []
    for (y0, y1) in spans(row_occ):
        if y1 - y0 < 8:
            continue
        cols = [any(col_occ[y][x] for y in range(y0, y1)) for x in range(w)]
        frames = []
        for (x0, x1) in spans(cols):
            if x1 - x0 < 8:
                continue
            frame = sheet.subsurface(pygame.Rect(x0, y0, x1 - x0, y1 - y0)).copy()
            nw = int(frame.get_width() * PLAYER_SCALE)
            nh = int(frame.get_height() * PLAYER_SCALE)
            frames.append(pygame.transform.smoothscale(frame, (nw, nh)))
        rows.append(frames)
    return rows


_FONTS = {}


def get_font(size, bold):
    key = (size, bold)
    if key not in _FONTS:
        _FONTS[key] = pygame.font.SysFont("consolas,couriernew,monospace", size, bold=bold)
    return _FONTS[key]


def draw_text(surf, text, size, color, pos, center=False, bold=True, shadow=True):
    font = get_font(size, bold)
    img = font.render(text, True, color)
    r = img.get_rect()
    if center:
        r.center = pos
    else:
        r.topleft = pos
    if shadow:
        sh = font.render(text, True, BLACK)
        surf.blit(sh, r.move(2, 2))
    surf.blit(img, r)
    return r


def panel(surf, rect, title=None):
    pygame.draw.rect(surf, DGRAY, rect, border_radius=10)
    pygame.draw.rect(surf, (120, 128, 145), rect, 3, border_radius=10)
    if title:
        draw_text(surf, title, 26, YELLOW, (rect.centerx, rect.y + 24), center=True)


# ----------------------------------------------------------------------------
# PERSONAGEM
# ----------------------------------------------------------------------------
class Player:
    def __init__(self, anim_normal, anim_gear):
        self.anims = {False: anim_normal, True: anim_gear}
        self.equipped = False
        self.x = W * 0.36
        self.y = GROUND_Y
        self.vy = 0.0
        self.on_ground = True
        self.facing = 1
        self.state = "idle"
        self.frame_t = 0.0
        self.busy = 0.0            # tempo restante da animação de interação
        self.busy_cb = None

    # --- animação de interação (agachar) -----------------------------------
    def start_interact(self, duration=0.9, callback=None):
        self.busy = duration
        self.busy_total = duration
        self.busy_cb = callback
        self.frame_t = 0

    def update(self, dt, keys, can_move=True):
        a = self.anims[self.equipped]
        # interação em andamento
        if self.busy > 0:
            self.busy -= dt
            self.state = "interact"
            if self.busy <= 0:
                self.busy = 0
                cb, self.busy_cb = self.busy_cb, None
                if cb:
                    cb()
            return

        dx = 0
        if can_move:
            if keys[pygame.K_a]:
                dx -= 1
            if keys[pygame.K_d]:
                dx += 1
        if dx:
            self.facing = dx
        self.x += dx * MOVE_SPEED * dt
        self.x = max(X_MIN, min(X_MAX, self.x))

        # física
        if not self.on_ground:
            self.vy += GRAVITY * dt
            self.y += self.vy * dt
            if self.y >= GROUND_Y:
                self.y = GROUND_Y
                self.vy = 0
                self.on_ground = True

        if not self.on_ground:
            self.state = "jump"
        elif dx:
            self.state = "walk"
        else:
            self.state = "idle"
        self.frame_t += dt

    def jump(self):
        if self.on_ground and self.busy <= 0:
            self.vy = -JUMP_SPEED
            self.on_ground = False
            self.frame_t = 0

    def current_frame(self):
        a = self.anims[self.equipped]
        if self.state == "idle":
            fr = a[0]
            img = fr[int(self.frame_t * 6) % len(fr)]
        elif self.state == "walk":
            fr = a[1]
            img = fr[int(self.frame_t * 12) % len(fr)]
        elif self.state == "jump":
            fr = a[2]  # 4 frames: impulso, subindo, descendo, pouso
            if self.vy < -250:
                idx = 1
            elif self.vy < 150:
                idx = 1 if self.vy < 0 else 2
            else:
                idx = 2
            if self.frame_t < 0.06:
                idx = 0
            img = fr[idx]
        else:  # interact
            fr = a[3]
            prog = 1 - (self.busy / max(self.busy_total, 0.001))
            img = fr[min(len(fr) - 1, int(prog * len(fr)))]
        return img

    def draw(self, surf, dead=False):
        img = self.current_frame()
        if self.facing < 0:
            img = pygame.transform.flip(img, True, False)
        if dead:
            img = img.copy()
            img.fill((255, 60, 60, 255), special_flags=pygame.BLEND_RGBA_MULT)
        r = img.get_rect(midbottom=(int(self.x), int(self.y)))
        # sombra
        sh = pygame.Surface((r.w, 14), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 90), sh.get_rect())
        surf.blit(sh, (r.x, GROUND_Y - 8))
        surf.blit(img, r)

    @property
    def rect(self):
        img = self.current_frame()
        return img.get_rect(midbottom=(int(self.x), int(self.y)))


# ----------------------------------------------------------------------------
# PUZZLE 1 - PIPE PUZZLE (canos)
# ----------------------------------------------------------------------------
# Direções: 0=cima 1=direita 2=baixo 3=esquerda
DIRS = [(0, -1), (1, 0), (0, 1), (-1, 0)]


class PipePuzzle:
    GRID = 5
    TIME_LIMIT = 50.0

    def __init__(self):
        self.n = self.GRID
        self.time_left = self.TIME_LIMIT
        self.done = False
        self.failed = False
        self.cursor = [0, 0]
        self.solved_flash = 0.0
        self._generate()

    # Cada peça é um conjunto de conexões (direções abertas)
    def _generate(self):
        n = self.n
        # caminho aleatório (self-avoiding) de (0, r0) a (n-1, r1)
        while True:
            r0 = random.randrange(n)
            path = [(0, r0)]
            visited = {(0, r0)}
            ok = self._dfs(path, visited, n - 1)
            if ok:
                break
        self.start_row = path[0][1]
        self.end_row = path[-1][1]
        self.solution = {}
        for i, (x, y) in enumerate(path):
            conns = set()
            if i == 0:
                conns.add(3)  # entrada pela esquerda
            else:
                px, py = path[i - 1]
                conns.add(DIRS.index((px - x, py - y)))
            if i == len(path) - 1:
                conns.add(1)  # saída pela direita
            else:
                nx, ny = path[i + 1]
                conns.add(DIRS.index((nx - x, ny - y)))
            self.solution[(x, y)] = conns
        # monta grid: peças do caminho + peças aleatórias
        self.tiles = {}
        for y in range(n):
            for x in range(n):
                if (x, y) in self.solution:
                    conns = self.solution[(x, y)]
                else:
                    conns = random.choice([{0, 2}, {0, 1}, {1, 2}, {0, 1, 2}])
                rot = random.randrange(4)
                base = frozenset(conns)
                self.tiles[(x, y)] = self._rotate(base, rot)
        # garante que não comece já resolvido
        while self.check():
            k = random.choice(list(self.solution.keys()))
            self.tiles[k] = self._rotate(self.tiles[k], 1)

    def _dfs(self, path, visited, target_x):
        x, y = path[-1]
        if x == target_x and len(path) >= self.n + 2:
            return True
        if len(path) > self.n * 3:
            return False
        opts = [(0, -1), (1, 0), (0, 1), (-1, 0)]
        random.shuffle(opts)
        # tendência a ir para a direita
        opts.sort(key=lambda d: random.random() - (0.35 if d == (1, 0) else 0))
        for dx, dy in opts:
            nx, ny = x + dx, y + dy
            if 0 <= nx < self.n and 0 <= ny < self.n and (nx, ny) not in visited:
                visited.add((nx, ny))
                path.append((nx, ny))
                if self._dfs(path, visited, target_x):
                    return True
                path.pop()
                visited.discard((nx, ny))
        return False

    @staticmethod
    def _rotate(conns, times):
        out = set(conns)
        for _ in range(times % 4):
            out = {(d + 1) % 4 for d in out}
        return frozenset(out)

    def rotate(self, cell):
        if self.done:
            return
        self.tiles[cell] = self._rotate(self.tiles[cell], 1)
        if self.check():
            self.done = True
            self.solved_flash = 1.2

    def check(self):
        """Há um caminho de água da entrada (esquerda) até a saída (direita)?"""
        return self.flow() is not None

    def flow(self):
        n = self.n
        sx, sy = 0, self.start_row
        if 3 not in self.tiles[(sx, sy)]:
            return None
        seen = {(sx, sy)}
        stack = [(sx, sy)]
        while stack:
            x, y = stack.pop()
            for d in self.tiles[(x, y)]:
                dx, dy = DIRS[d]
                nx, ny = x + dx, y + dy
                if (x, y) == (n - 1, self.end_row) and d == 1:
                    return seen
                if 0 <= nx < n and 0 <= ny < n:
                    if (d + 2) % 4 in self.tiles[(nx, ny)] and (nx, ny) not in seen:
                        seen.add((nx, ny))
                        stack.append((nx, ny))
        return None

    def update(self, dt):
        if self.done:
            self.solved_flash -= dt
            return
        self.time_left -= dt
        if self.time_left <= 0:
            self.failed = True

    def cell_at(self, pos):
        ox, oy, cs = self._layout()
        x = (pos[0] - ox) // cs
        y = (pos[1] - oy) // cs
        if 0 <= x < self.n and 0 <= y < self.n:
            return (int(x), int(y))
        return None

    def _layout(self):
        cs = 90
        ox = (W - cs * self.n) // 2
        oy = 170
        return ox, oy, cs

    def handle(self, ev):
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button in (1, 3):
            c = self.cell_at(ev.pos)
            if c:
                self.rotate(c)
        elif ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_UP:
                self.cursor[1] = max(0, self.cursor[1] - 1)
            elif ev.key == pygame.K_DOWN:
                self.cursor[1] = min(self.n - 1, self.cursor[1] + 1)
            elif ev.key == pygame.K_LEFT:
                self.cursor[0] = max(0, self.cursor[0] - 1)
            elif ev.key == pygame.K_RIGHT:
                self.cursor[0] = min(self.n - 1, self.cursor[0] + 1)
            elif ev.key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_e):
                self.rotate(tuple(self.cursor))

    def draw(self, surf):
        ox, oy, cs = self._layout()
        box = pygame.Rect(ox - 60, oy - 100, cs * self.n + 120, cs * self.n + 150)
        panel(surf, box, "PUZZLE 1: RESTABELEÇA O FLUXO DE AR")
        draw_text(surf, "Clique nas peças para girar (ou setas + ESPAÇO). Ligue ENTRADA -> SAÍDA.",
                  16, WHITE, (box.centerx, box.y + 55), center=True, bold=False)
        # timer
        frac = max(0, self.time_left / self.TIME_LIMIT)
        bar = pygame.Rect(box.x + 30, box.y + 78, box.w - 60, 14)
        pygame.draw.rect(surf, BLACK, bar, border_radius=6)
        col = GREEN if frac > 0.4 else (YELLOW if frac > 0.2 else RED)
        pygame.draw.rect(surf, col, (bar.x, bar.y, int(bar.w * frac), bar.h), border_radius=6)
        draw_text(surf, "%0.0fs" % max(0, self.time_left), 16, WHITE, (bar.right - 36, bar.y - 18))

        wet = self.flow() or set()
        # entrada/saída
        pygame.draw.rect(surf, ORANGE, (ox - 36, oy + self.start_row * cs + cs // 2 - 14, 36, 28))
        draw_text(surf, "IN", 16, BLACK, (ox - 32, oy + self.start_row * cs + cs // 2 - 9), shadow=False)
        pygame.draw.rect(surf, ORANGE, (ox + cs * self.n, oy + self.end_row * cs + cs // 2 - 14, 36, 28))
        draw_text(surf, "OUT", 14, BLACK, (ox + cs * self.n + 3, oy + self.end_row * cs + cs // 2 - 8), shadow=False)

        for (x, y), conns in self.tiles.items():
            r = pygame.Rect(ox + x * cs, oy + y * cs, cs, cs)
            pygame.draw.rect(surf, (48, 52, 62), r.inflate(-4, -4), border_radius=6)
            c = r.center
            pipe_col = BLUE if (x, y) in wet or self.done else (150, 155, 170)
            for d in conns:
                dx, dy = DIRS[d]
                end = (c[0] + dx * cs // 2, c[1] + dy * cs // 2)
                pygame.draw.line(surf, pipe_col, c, end, 20)
            pygame.draw.circle(surf, pipe_col, c, 10)
            if [x, y] == self.cursor:
                pygame.draw.rect(surf, YELLOW, r.inflate(-4, -4), 3, border_radius=6)
        if self.done:
            draw_text(surf, "FLUXO RESTABELECIDO!", 34, GREEN, (W // 2, box.bottom - 30), center=True)


# ----------------------------------------------------------------------------
# PUZZLE 2 - LIGAR OS 10 FIOS
# ----------------------------------------------------------------------------
class WirePuzzle:
    TIME_LIMIT = 90.0

    def __init__(self):
        self.time_left = self.TIME_LIMIT
        self.done = False
        self.failed = False
        self.fail_reason = ""
        n = len(WIRE_COLORS)
        self.left_order = list(range(n))
        random.shuffle(self.left_order)
        self.right_order = list(range(n))
        random.shuffle(self.right_order)
        self.connected = set()   # índices de cor já ligados
        self.dragging = None     # índice de cor sendo arrastado
        self.mouse = (0, 0)
        self.box = pygame.Rect(150, 70, W - 300, 560)
        self.top = self.box.y + 120
        self.gap = 41

    def left_pos(self, slot):
        return (self.box.x + 90, self.top + slot * self.gap)

    def right_pos(self, slot):
        return (self.box.right - 90, self.top + slot * self.gap)

    def update(self, dt):
        if self.done:
            return
        self.time_left -= dt
        if self.time_left <= 0:
            self.failed = True
            self.fail_reason = "Tempo esgotado!"

    def handle(self, ev):
        if self.done:
            return
        if ev.type == pygame.MOUSEMOTION:
            self.mouse = ev.pos
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            for slot, ci in enumerate(self.left_order):
                p = self.left_pos(slot)
                if math.hypot(ev.pos[0] - p[0], ev.pos[1] - p[1]) < 16 and ci not in self.connected:
                    self.dragging = ci
        elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1 and self.dragging is not None:
            for slot, ci in enumerate(self.right_order):
                p = self.right_pos(slot)
                if math.hypot(ev.pos[0] - p[0], ev.pos[1] - p[1]) < 20:
                    if ci in self.connected:
                        break
                    if ci == self.dragging:
                        self.connected.add(ci)
                        if len(self.connected) == len(WIRE_COLORS):
                            self.done = True
                    else:
                        self.failed = True
                        self.fail_reason = "Fio ligado no terminal errado! CURTO-CIRCUITO!"
                    break
            self.dragging = None

    def draw(self, surf):
        panel(surf, self.box, "PUZZLE 2: LIGUE OS FIOS NAS CORES CORRESPONDENTES")
        draw_text(surf, "Arraste do terminal esquerdo até o terminal da MESMA cor. Errar = curto-circuito.",
                  16, WHITE, (self.box.centerx, self.box.y + 58), center=True, bold=False)
        frac = max(0, self.time_left / self.TIME_LIMIT)
        bar = pygame.Rect(self.box.x + 40, self.box.y + 82, self.box.w - 80, 12)
        pygame.draw.rect(surf, BLACK, bar, border_radius=6)
        col = GREEN if frac > 0.4 else (YELLOW if frac > 0.2 else RED)
        pygame.draw.rect(surf, col, (bar.x, bar.y, int(bar.w * frac), bar.h), border_radius=6)

        # fios já conectados
        for slot_l, ci in enumerate(self.left_order):
            if ci in self.connected:
                slot_r = self.right_order.index(ci)
                a, b = self.left_pos(slot_l), self.right_pos(slot_r)
                self._wire(surf, a, b, WIRE_COLORS[ci][1])
        # fio sendo arrastado
        if self.dragging is not None:
            a = self.left_pos(self.left_order.index(self.dragging))
            self._wire(surf, a, self.mouse, WIRE_COLORS[self.dragging][1])
        # terminais
        for slot, ci in enumerate(self.left_order):
            p = self.left_pos(slot)
            pygame.draw.circle(surf, BLACK, p, 15)
            pygame.draw.circle(surf, WIRE_COLORS[ci][1], p, 11)
        for slot, ci in enumerate(self.right_order):
            p = self.right_pos(slot)
            pygame.draw.circle(surf, BLACK, p, 15)
            pygame.draw.circle(surf, WIRE_COLORS[ci][1], p, 11)
            if ci in self.connected:
                pygame.draw.circle(surf, WHITE, p, 15, 3)
        draw_text(surf, "%d/%d" % (len(self.connected), len(WIRE_COLORS)), 22, WHITE,
                  (self.box.centerx, self.box.bottom - 30), center=True)
        if self.done:
            draw_text(surf, "PAINEL RELIGADO!", 34, GREEN, (self.box.centerx, self.box.bottom - 70), center=True)

    @staticmethod
    def _wire(surf, a, b, color):
        pts = []
        for i in range(21):
            t = i / 20
            # curva suave
            x = a[0] + (b[0] - a[0]) * t
            s = t * t * (3 - 2 * t)
            y = a[1] + (b[1] - a[1]) * s
            pts.append((x, y))
        pygame.draw.lines(surf, BLACK, False, pts, 9)
        pygame.draw.lines(surf, color, False, pts, 5)


# ----------------------------------------------------------------------------
# PUZZLE 3 - QUICK BAR
# ----------------------------------------------------------------------------
class QuickBarPuzzle:
    HITS_NEEDED = 5

    def __init__(self):
        self.hits = 0
        self.done = False
        self.failed = False
        self.fail_reason = ""
        self.bar = pygame.Rect(240, 330, W - 480, 60)
        self.pos = 0.0          # 0..1
        self.dir = 1
        self.flash = 0.0
        self.flash_ok = True
        self.start_delay = 1.0  # tempo de preparo
        self._new_round()

    def _new_round(self):
        # a cada acerto: zona menor e barra mais rápida
        self.speed = 0.55 + self.hits * 0.28
        self.zone_w = max(0.045, 0.20 - self.hits * 0.035)
        self.zone_x = random.uniform(0.12, 0.88 - self.zone_w)

    def update(self, dt):
        if self.flash > 0:
            self.flash -= dt
        if self.done or self.failed:
            return
        if self.start_delay > 0:
            self.start_delay -= dt
            return
        self.pos += self.dir * self.speed * dt
        if self.pos >= 1:
            self.pos, self.dir = 1, -1
        elif self.pos <= 0:
            self.pos, self.dir = 0, 1

    def press(self):
        if self.done or self.failed or self.start_delay > 0:
            return
        if self.zone_x <= self.pos <= self.zone_x + self.zone_w:
            self.hits += 1
            self.flash, self.flash_ok = 0.3, True
            if self.hits >= self.HITS_NEEDED:
                self.done = True
            else:
                self._new_round()
        else:
            self.failed = True
            self.fail_reason = "Errou o tempo! O gerador explodiu!"
            self.flash, self.flash_ok = 0.3, False

    def handle(self, ev):
        if ev.type == pygame.KEYDOWN and ev.key in (pygame.K_SPACE, pygame.K_e, pygame.K_RETURN):
            self.press()
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            self.press()

    def draw(self, surf):
        box = pygame.Rect(180, 150, W - 360, 400)
        panel(surf, box, "PUZZLE 3: ESTABILIZE O GERADOR")
        draw_text(surf, "Pressione ESPAÇO (ou clique) quando o marcador estiver na ZONA VERDE.",
                  16, WHITE, (box.centerx, box.y + 60), center=True, bold=False)
        draw_text(surf, "Acertos: %d/%d   (cada acerto deixa mais difícil)" % (self.hits, self.HITS_NEEDED),
                  22, YELLOW, (box.centerx, box.y + 100), center=True)
        # indicadores
        for i in range(self.HITS_NEEDED):
            c = (box.centerx - 2 * 40 + i * 40, box.y + 140)
            pygame.draw.circle(surf, GREEN if i < self.hits else BLACK, c, 12)
            pygame.draw.circle(surf, WHITE, c, 12, 2)
        # barra
        pygame.draw.rect(surf, BLACK, self.bar.inflate(10, 10), border_radius=8)
        pygame.draw.rect(surf, (90, 40, 40), self.bar, border_radius=6)
        z = pygame.Rect(self.bar.x + int(self.bar.w * self.zone_x), self.bar.y,
                        int(self.bar.w * self.zone_w), self.bar.h)
        pygame.draw.rect(surf, GREEN, z)
        mx = self.bar.x + int(self.bar.w * self.pos)
        pygame.draw.rect(surf, WHITE, (mx - 4, self.bar.y - 14, 8, self.bar.h + 28), border_radius=3)
        if self.start_delay > 0:
            draw_text(surf, "Prepare-se...", 26, WHITE, (box.centerx, box.bottom - 50), center=True)
        if self.flash > 0:
            col = GREEN if self.flash_ok else RED
            ov = pygame.Surface((box.w, box.h), pygame.SRCALPHA)
            ov.fill((*col, int(120 * (self.flash / 0.3))))
            surf.blit(ov, box.topleft)
        if self.done:
            draw_text(surf, "GERADOR ESTABILIZADO!", 34, GREEN, (box.centerx, box.bottom - 50), center=True)


# ----------------------------------------------------------------------------
# JOGO
# ----------------------------------------------------------------------------
class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("USINA - Puzzles de Segurança")
        self.screen = pygame.display.set_mode((W, H))
        self.clock = pygame.time.Clock()
        self.load_assets()
        self.reset()

    def load_assets(self):
        destroyed = pygame.transform.smoothscale(load_img("cenario_destruido.jpg", False), (W, H))
        clean = pygame.transform.smoothscale(load_img("cenario_consertado.jpg", False), (W, H))
        self.bg_destroyed = destroyed
        self.bg_clean = clean
        sheet_n = load_img("sprites_normal.png")
        sheet_g = load_img("sprites_equipado.png")
        self.anim_normal = slice_sheet(sheet_n)
        self.anim_gear = slice_sheet(sheet_g)
        for a in (self.anim_normal, self.anim_gear):
            if len(a) < 4:
                raise RuntimeError("Sprite sheet com menos de 4 linhas de animação!")

    def reset(self):
        self.bg = self.bg_destroyed.copy()
        self.player = Player(self.anim_normal, self.anim_gear)
        self.solved = {"pipe": False, "panel": False, "fire": False}
        self.mode = "play"      # play | puzzle | dead | win | dressing
        self.puzzle = None
        self.puzzle_key = None
        self.msg = "Vá até o ARMÁRIO e vista o equipamento de segurança (E)."
        self.msg_t = 6.0
        self.death_reason = ""
        self.death_t = 0.0
        self.t = 0.0
        self.win_t = 0.0

    # --- helpers -------------------------------------------------------------
    def zone_at_player(self):
        px = self.player.x
        for key, (a, b) in ZONES.items():
            if a * W <= px <= b * W:
                return key
        return None

    def near_locker(self):
        return abs(self.player.x - LOCKER_X) < 70

    def patch_background(self, key):
        a, b, c, d = PATCH_RECTS[key]
        r = pygame.Rect(int(a * W), int(b * H), int((c - a) * W), int((d - b) * H))
        self.bg.blit(self.bg_clean, r.topleft, r)

    def die(self, reason):
        self.mode = "dead"
        self.death_reason = reason
        self.death_t = 0.0
        self.puzzle = None

    def say(self, text, t=3.0):
        self.msg, self.msg_t = text, t

    # --- interação -----------------------------------------------------------
    def interact(self):
        p = self.player
        if not p.on_ground:
            return
        if self.near_locker() and not p.equipped:
            self.mode = "dressing"
            self.say("Vestindo o equipamento...", 2)

            def finish():
                p.equipped = True
                self.mode = "play"
                self.say("Equipamento vestido! Agora vá consertar os pontos danificados.", 4)
            p.start_interact(1.0, finish)
            return
        if self.near_locker() and p.equipped:
            self.say("Você já está com o equipamento de segurança.", 2)
            return
        key = self.zone_at_player()
        if key and not self.solved[key]:
            if not p.equipped:
                self.die("Você mexeu no equipamento SEM proteção e se feriu!")
                return
            self.start_puzzle(key)
        elif key and self.solved[key]:
            self.say("Este ponto já foi consertado.", 2)

    def start_puzzle(self, key):
        self.puzzle_key = key
        self.puzzle = {"pipe": PipePuzzle, "panel": WirePuzzle, "fire": QuickBarPuzzle}[key]()
        self.mode = "puzzle"

    # --- loop ------------------------------------------------------------------
    def run(self):
        while True:
            dt = min(self.clock.tick(FPS) / 1000.0, 0.05)
            self.t += dt
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                self.handle_event(ev)
            self.update(dt)
            self.draw()
            pygame.display.flip()

    def handle_event(self, ev):
        if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
            if self.mode == "puzzle":
                self.die("Você abandonou o reparo e a situação saiu do controle!")
            elif self.mode in ("dead", "win", "play"):
                pygame.quit()
                sys.exit()
            return

        if self.mode == "play":
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_SPACE:
                    self.player.jump()
                elif ev.key == pygame.K_e:
                    self.interact()
        elif self.mode == "puzzle":
            self.puzzle.handle(ev)
        elif self.mode in ("dead", "win"):
            if self.death_t > 0.6 or self.mode == "win":
                if ev.type == pygame.KEYDOWN and ev.key in (pygame.K_r, pygame.K_RETURN):
                    self.reset()
                elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    if self.restart_btn().collidepoint(ev.pos):
                        self.reset()

    def restart_btn(self):
        return pygame.Rect(W // 2 - 140, H // 2 + 70, 280, 60)

    def update(self, dt):
        keys = pygame.key.get_pressed()
        if self.msg_t > 0:
            self.msg_t -= dt
        if self.mode in ("play", "dressing"):
            self.player.update(dt, keys, can_move=(self.mode == "play"))
        elif self.mode == "puzzle":
            self.player.update(dt, keys, can_move=False)
            self.puzzle.update(dt)
            self.check_puzzle_result()
        elif self.mode == "dead":
            self.death_t += dt
        elif self.mode == "win":
            self.win_t += dt
            self.player.update(dt, keys, can_move=False)

    def check_puzzle_result(self):
        pz = self.puzzle
        if pz.failed:
            reason = getattr(pz, "fail_reason", "") or "Tempo esgotado! O sistema falhou!"
            self.die(reason)
            return
        if pz.done:
            # espera um instante mostrando "concluído"
            if not hasattr(pz, "_end_t"):
                pz._end_t = 1.3
            pz._end_t -= 1 / FPS
            if pz._end_t <= 0:
                key = self.puzzle_key
                self.solved[key] = True
                self.patch_background(key)
                self.puzzle = None
                self.mode = "play"
                if all(self.solved.values()):
                    self.mode = "win"
                    self.win_t = 0
                else:
                    left = 3 - sum(self.solved.values())
                    self.say("Reparo concluído! Faltam %d ponto(s)." % left, 3)

    # --- desenho ---------------------------------------------------------------
    def draw_locker(self, surf):
        x = LOCKER_X
        r = pygame.Rect(0, 0, 74, 150)
        r.midbottom = (x, GROUND_Y + 4)
        pygame.draw.rect(surf, (52, 70, 96), r, border_radius=4)
        pygame.draw.rect(surf, (20, 28, 44), r, 3, border_radius=4)
        pygame.draw.line(surf, (20, 28, 44), (r.centerx, r.y), (r.centerx, r.bottom), 3)
        for i in range(4):
            yy = r.y + 14 + i * 7
            pygame.draw.line(surf, (20, 28, 44), (r.x + 8, yy), (r.centerx - 8, yy), 2)
            pygame.draw.line(surf, (20, 28, 44), (r.centerx + 8, yy), (r.right - 8, yy), 2)
        pygame.draw.rect(surf, YELLOW, (r.centerx - 8, r.y + 70, 5, 16))
        pygame.draw.rect(surf, YELLOW, (r.centerx + 3, r.y + 70, 5, 16))
        draw_text(surf, "ARMÁRIO", 14, WHITE, (r.centerx, r.y - 12), center=True)
        # ícone de capacete
        pygame.draw.circle(surf, WHITE, (r.centerx, r.y + 42), 9)
        pygame.draw.rect(surf, WHITE, (r.centerx - 12, r.y + 42, 24, 4))

    def draw_hud(self, surf):
        # Lista de objetivos
        names = [("pipe", "Canos de ar"), ("panel", "Painel elétrico"), ("fire", "Gerador")]
        s = pygame.Surface((270, 120), pygame.SRCALPHA)
        s.fill((0, 0, 0, 150))
        surf.blit(s, (10, 10))
        draw_text(surf, "OBJETIVOS", 16, YELLOW, (22, 16))
        eq = "Equipamento: " + ("OK" if self.player.equipped else "NÃO VESTIDO")
        draw_text(surf, eq, 14, GREEN if self.player.equipped else RED, (22, 38))
        for i, (k, n) in enumerate(names):
            col = GREEN if self.solved[k] else WHITE
            draw_text(surf, ("[x] " if self.solved[k] else "[ ] ") + n, 14, col, (22, 60 + i * 20))
        # mensagem
        if self.msg_t > 0:
            w = max(300, len(self.msg) * 10 + 40)
            r = pygame.Rect(0, 0, w, 40)
            r.midtop = (W // 2, 14)
            s = pygame.Surface(r.size, pygame.SRCALPHA)
            s.fill((0, 0, 0, 170))
            surf.blit(s, r)
            draw_text(surf, self.msg, 16, WHITE, r.center, center=True)

    def draw_prompt(self, surf):
        p = self.player
        text = None
        if self.mode == "play" and p.on_ground:
            if self.near_locker() and not p.equipped:
                text = "[E] Vestir equipamento"
            else:
                key = self.zone_at_player()
                if key and not self.solved[key]:
                    text = "[E] Iniciar puzzle" if p.equipped else "[E] Mexer (sem equipamento: PERIGO!)"
        if text:
            r = p.rect
            col = YELLOW if p.equipped or self.near_locker() else RED
            bob = int(math.sin(self.t * 6) * 3)
            draw_text(surf, text, 18, col, (r.centerx, r.y - 18 + bob), center=True)

    def draw_zone_markers(self, surf):
        # setas piscando sobre os locais danificados
        if self.mode != "play":
            return
        if int(self.t * 2) % 2 == 0:
            for key, (a, b) in ZONES.items():
                if self.solved[key]:
                    continue
                cx = int((a + b) / 2 * W)
                y = int(H * 0.80)
                pygame.draw.polygon(surf, YELLOW, [(cx - 12, y - 16), (cx + 12, y - 16), (cx, y)])

    def draw(self):
        s = self.screen
        s.blit(self.bg, (0, 0))
        self.draw_locker(s)
        self.draw_zone_markers(s)
        self.player.draw(s, dead=(self.mode == "dead"))
        self.draw_prompt(s)
        self.draw_hud(s)

        if self.mode == "puzzle":
            ov = pygame.Surface((W, H), pygame.SRCALPHA)
            ov.fill((0, 0, 0, 170))
            s.blit(ov, (0, 0))
            self.puzzle.draw(s)
            draw_text(s, "ESC = desistir (morrer)", 14, (170, 170, 170), (W - 220, H - 26), bold=False)
        elif self.mode == "dead":
            a = min(210, int(self.death_t * 400))
            ov = pygame.Surface((W, H), pygame.SRCALPHA)
            ov.fill((120, 0, 0, a))
            s.blit(ov, (0, 0))
            if self.death_t > 0.4:
                draw_text(s, "GAME OVER", 80, WHITE, (W // 2, H // 2 - 90), center=True)
                draw_text(s, self.death_reason, 20, WHITE, (W // 2, H // 2 - 20), center=True, bold=False)
                b = self.restart_btn()
                hover = b.collidepoint(pygame.mouse.get_pos())
                pygame.draw.rect(s, (230, 230, 230) if hover else (180, 180, 180), b, border_radius=10)
                pygame.draw.rect(s, BLACK, b, 3, border_radius=10)
                draw_text(s, "RECOMEÇAR (R)", 24, BLACK, b.center, center=True, shadow=False)
        elif self.mode == "win":
            a = min(180, int(self.win_t * 200))
            ov = pygame.Surface((W, H), pygame.SRCALPHA)
            ov.fill((0, 40, 0, a))
            s.blit(ov, (0, 0))
            if self.win_t > 0.5:
                draw_text(s, "USINA SEGURA!", 70, GREEN, (W // 2, H // 2 - 90), center=True)
                draw_text(s, "Você consertou tudo com segurança.", 22, WHITE, (W // 2, H // 2 - 20), center=True, bold=False)
                b = self.restart_btn()
                hover = b.collidepoint(pygame.mouse.get_pos())
                pygame.draw.rect(s, (230, 230, 230) if hover else (180, 180, 180), b, border_radius=10)
                pygame.draw.rect(s, BLACK, b, 3, border_radius=10)
                draw_text(s, "JOGAR DE NOVO (R)", 22, BLACK, b.center, center=True, shadow=False)


if __name__ == "__main__":
    Game().run()