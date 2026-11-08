"""Fuzzy Weibull quantities, independent of HTTP and the user interface."""
from functools import lru_cache
from bisect import bisect_left
import math

EPS = 1e-6
LEVELS = [EPS if i == 0 else .5 * (i / 50) ** 3 if i <= 50
          else 1 - .5 * ((100 - i) / 50) ** 3 for i in range(101)]


def check(condition, message):
    if not condition:
        raise ValueError(message)


@lru_cache(maxsize=2048)
def _cuts(shape, scale, shift):
    mode = 0 if shape == 1 else ((shape - 1) / shape) ** (1 / shape)

    def log_mu(z):
        if z <= 0:
            return 0 if shape == 1 and z == 0 else -math.inf
        if shape == 1:
            return -z
        return (shape - 1) * (math.log(z) - math.log(mode)) - (z ** shape - mode ** shape)

    cuts = []
    for alpha in LEVELS:
        if alpha == 1:
            cuts.append((shift + scale * mode,) * 2)
            continue
        target, left = math.log(alpha), 0
        if shape > 1:
            mk = mode ** shape
            lo, hi = (target - mk) / (shape - 1) - 1, 0
            for _ in range(80):
                t = (lo + hi) / 2
                value = (shape - 1) * t - mk * math.expm1(shape * t)
                if value < target:
                    lo = t
                else:
                    hi = t
            left = mode * math.exp((lo + hi) / 2)
        lo, hi = mode, max(1, mode * 2)
        while log_mu(hi) > target:
            hi *= 2
        for _ in range(80):
            mid = (lo + hi) / 2
            if log_mu(mid) > target:
                lo = mid
            else:
                hi = mid
        cuts.append((shift + scale * left, shift + scale * (lo + hi) / 2))
    return tuple(cuts)


def centroid(value):
    area = moment = 0
    for i in range(1, 101):
        h = LEVELS[i] - LEVELS[i - 1]
        a, b = value['cuts'][i - 1:i + 1]
        area += h * ((a[1] - a[0]) + (b[1] - b[0])) / 2
        moment += h * ((a[1] ** 2 - a[0] ** 2) + (b[1] ** 2 - b[0] ** 2)) / 4
    return moment / area if area > 1e-15 else sum(value['cuts'][100]) / 2


def enrich(value):
    value['centroid'] = centroid(value)
    return value


def weibull(name, shape, scale, shift=0):
    check(isinstance(name, str) and 0 < len(name.strip()) <= 80, 'Название: от 1 до 80 символов.')
    check(all(isinstance(v, (int, float)) and math.isfinite(v) for v in (shape, scale, shift)), 'Параметры должны быть конечными числами.')
    check(1 <= shape <= 20, 'Форма γ должна быть от 1 до 20: при γ < 1 нормировка на максимум невозможна.')
    check(.05 <= scale <= 1000 and abs(shift) <= 10000, 'Масштаб σ: 0,05–1000; |сдвиг| ≤ 10000.')
    return enrich(dict(name=name.strip(), type='weibull', shape=shape, scale=scale,
                       shift=shift, cuts=[list(c) for c in _cuts(shape, scale, shift)]))


def membership(value, x):
    z, k = (x - value['shift']) / value['scale'], value['shape']
    if z < 0:
        return 0
    if k == 1:
        return math.exp(-z)
    if z == 0:
        return 0
    m = ((k - 1) / k) ** (1 / k)
    return math.exp((k - 1) * (math.log(z) - math.log(m)) - z ** k + m ** k)


def validate(value):
    check(isinstance(value, dict), 'Ожидается объект нечёткой величины.')
    name = value.get('name')
    check(isinstance(name, str) and 0 < len(name.strip()) <= 80, 'Некорректное название.')
    if value.get('type') == 'weibull':
        return weibull(name, value.get('shape'), value.get('scale'), value.get('shift', 0))
    cuts = value.get('cuts')
    check(value.get('type') == 'cuts' and isinstance(cuts, list) and len(cuts) == 101, 'Некорректный формат α-срезов.')
    for i, c in enumerate(cuts):
        check(isinstance(c, (list, tuple)) and len(c) == 2 and
              all(isinstance(x, (int, float)) and math.isfinite(x) and abs(x) <= 1e100 for x in c)
              and c[0] <= c[1], 'Некорректные границы интервала; |x| ≤ 10¹⁰⁰.')
        if i:
            check(c[0] >= cuts[i - 1][0] - 1e-8 and c[1] <= cuts[i - 1][1] + 1e-8, 'α-срезы должны быть вложенными.')
    return enrich(dict(name=name.strip(), type='cuts', cuts=[list(c) for c in cuts]))


def arithmetic(a, b, op, name=None):
    check(op in ('+', '-', '*', '/'), 'Неизвестная операция.')
    if op == '/':
        check(not any(l <= 0 <= r for l, r in b['cuts']), 'Деление запрещено: α-срез делителя содержит ноль.')
    cuts = []
    for (l, r), (s, t) in zip(a['cuts'], b['cuts']):
        if op == '+':
            result = [l + s, r + t]
        elif op == '-':
            result = [l - t, r - s]
        else:
            values = [l * s, l * t, r * s, r * t] if op == '*' else [l / s, l / t, r / s, r / t]
            result = [min(values), max(values)]
        cuts.append(result)
    return validate(dict(name=name or f"({a['name']} {op} {b['name']})"[:80], type='cuts', cuts=cuts))


def alpha_cut(value, alpha):
    """Cut of the stored piecewise-linear model, including off-grid levels."""
    check(type(alpha) in (int, float) and math.isfinite(alpha) and EPS <= alpha <= 1,
          'Уровень α должен быть от 0,000001 до 1.')
    i = bisect_left(LEVELS, alpha)
    if LEVELS[i] == alpha:
        return list(value['cuts'][i])
    weight = (alpha - LEVELS[i - 1]) / (LEVELS[i] - LEVELS[i - 1])
    return [a + weight * (b - a) for a, b in zip(value['cuts'][i - 1], value['cuts'][i])]


def feature(value, metric='cuts', alpha=.5):
    if metric == 'alpha':
        return alpha_cut(value, alpha)
    if metric == 'center':
        return [centroid(value)]
    check(metric == 'cuts', 'Неизвестная метрика.')
    return [x for c in value['cuts'][1:] for x in c]


def distance(a, b, metric='cuts'):
    x, y = feature(a, metric), feature(b, metric)
    return math.sqrt(sum((s - t) ** 2 for s, t in zip(x, y)) / len(x))


def compare(a, b):
    ca, cb = centroid(a), centroid(b)
    relation = '≈' if abs(ca - cb) <= 1e-8 * max(1, abs(ca), abs(cb)) else '<' if ca < cb else '>'
    return dict(a=ca, b=cb, relation=relation, distance=distance(a, b))


def rng(seed):
    """Mulberry32, bit-for-bit compatible with previously saved JS examples."""
    state = seed
    mask = 0xffffffff
    while True:
        state = (state + 0x6D2B79F5) & mask
        t = ((state ^ (state >> 15)) * (1 | state)) & mask
        t ^= (t + (((t ^ (t >> 7)) * (61 | t)) & mask)) & mask
        yield ((t ^ (t >> 14)) & mask) / 4294967296


def generate(n, seed=42):
    check(type(n) is int and 100 <= n <= 300, 'Количество должно быть целым от 100 до 300.')
    check(type(seed) is int and 0 <= seed <= 4294967295, 'Seed: целое от 0 до 4294967295.')
    random = rng(seed)
    # Independent uniform parameters; no groups tied to the object's index.
    return [weibull(f'W{i + 1:03}', 1 + next(random) * 5,
                    .5 + next(random) * 9.5) for i in range(n)]
